import inspect
# Monkey-patch: определяем getargspec, возвращающую ровно 4 значения.
def getargspec(func):
    fas = inspect.getfullargspec(func)
    return fas.args, fas.varargs, fas.varkw, fas.defaults
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = getargspec

import os
import re
import difflib
import logging
import asyncio
import pprint
import time
from flask import Flask, request, jsonify
import openai
import requests
from datetime import datetime
from clientdata import register_or_update_client, verify_client_code, update_last_visit, update_activity_status
from client_caec import add_message_to_client_file, find_client_file_id, get_sheets_service, CLIENT_FILES_DIR
from bible import load_bible_data, save_bible_pair, get_rule
from price_handler import check_ferry_price, parse_price, remove_timestamp, get_guiding_question, get_openai_response
from flask_cors import CORS
import openpyxl

# Обработка импорта nltk с fallback, если модуль отсутствует
try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer, SnowballStemmer
    from nltk.tokenize import word_tokenize
    nltk.download('punkt')
    nltk.download('stopwords')
    nltk.download('wordnet')
    stop_words = set(stopwords.words('russian'))
    USE_NLTK = True
except ImportError as e:
    logging.error("NLTK не установлен. Используется fallback-токенизация без стоп-слов.")
    USE_NLTK = False
    stop_words = set()
    # Определим простую функцию-токенайзер
    def word_tokenize(text):
        return text.split()

# Импортируем pymorphy2 для лемматизации
try:
    import pymorphy2
    morph = pymorphy2.MorphAnalyzer()
except Exception as e:
    logging.error(f"Ошибка инициализации pymorphy2: {e}")
    morph = None

from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Файл price.xlsx временно отключён – ассистент получает данные непосредственно с сайта.
USE_PRICE_FILE = False

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "./service_account.json")
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("server.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logger.info("Environment variables:")
pprint.pprint(dict(os.environ))

pending_guiding = {}

PRICE_KEYWORDS = ["цена", "прайс"]

def lemmatize_text(text):
    """
    Приводит каждое слово входящего текста к его базовой (лемматизированной) форме.
    Если nltk установлен, используется nltk и pymorphy2; иначе – простое разделение по пробелам.
    """
    text = text.lower()
    if USE_NLTK and morph:
        tokens = word_tokenize(text)
        # Убираем стоп-слова
        tokens = [token for token in tokens if token not in stop_words]
        lemmas = [morph.parse(token)[0].normal_form for token in tokens]
        return " ".join(lemmas)
    else:
        # fallback: просто разделяем по пробелам
        return " ".join(text.split())

def get_alias_mapping_and_instructions():
    """
    Загружает строки с Verification == "Rule" из Bible.xlsx и разбивает содержимое столбца Answers.
    Если строка содержит знак '=', она считается правилом алиасов и парсится в формате:
        alias1, alias2, ... = normalized_value
    Если строка не содержит '=', она считается общей инструкцией для агента.
    Возвращает два значения:
        - alias_mapping: словарь, где ключи – варианты (алиасы), а значения – нормализованное наименование.
        - instructions: список строк общей инструкции.
    """
    df = load_bible_data()
    alias_mapping = {}
    instructions = []
    if df is not None and not df.empty:
        rule_df = df[df["Verification"].str.strip().str.upper() == "RULE"]
        for idx, row in rule_df.iterrows():
            answer_text = row.get("Answers", "")
            if answer_text:
                lines = answer_text.split("\n")
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if "=" in line:
                        parts = line.split("=", 1)
                        aliases_part = parts[0].strip().lower()
                        normalized_value = parts[1].strip().lower()
                        variants = [v.strip() for v in aliases_part.split(",")]
                        for variant in variants:
                            alias_mapping[variant] = normalized_value
                    else:
                        instructions.append(line)
    return alias_mapping, instructions

def get_vehicle_type(client_text):
    """
    Определяет тип транспортного средства на основе входящего текста.
    Применяет лемматизацию и использует правила нормализации (алиасы), загруженные из Bible.xlsx.
    Если найдено совпадение, возвращается нормализованное значение; иначе производится поиск по данным с сайта.
    """
    normalized_text = lemmatize_text(client_text)
    logger.info(f"Normalized text: {normalized_text}")
    
    alias_mapping, _ = get_alias_mapping_and_instructions()
    for variant, normalized_value in alias_mapping.items():
        if variant in normalized_text:
            logger.info(f"Alias mapping applied: найден '{variant}'; результат: '{normalized_value}'")
            return normalized_value
    # Если alias-правило не сработало, пробуем нечёткое сопоставление с данными с сайта
    from price import get_ferry_prices
    data = get_ferry_prices()
    vehicle_types = list(data.keys())
    matches = difflib.get_close_matches(client_text.lower(), [vt.lower() for vt in vehicle_types], n=1, cutoff=0.3)
    if matches:
        for vt in vehicle_types:
            if vt.lower() == matches[0]:
                logger.info(f"Тип транспортного средства найден по данным сайта: {vt}")
                return vt.lower()
    logger.info(get_rule("vehicle_type_not_identified"))
    return None

def get_price_response(vehicle_type, direction="Ro_Ge"):
    return check_ferry_price(vehicle_type, direction)

def get_openai_response(messages):
    start_time = time.time()
    attempt = 0
    while True:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=150,
                timeout=40
            )
            return response
        except Exception as e:
            logger.error(f"OpenAI error attempt {attempt+1}: {e}")
            attempt += 1
            if time.time() - start_time > 180:
                return get_rule("openai_timeout_message")
            time.sleep(2)

def prepare_chat_context(client_code):
    messages = []
    alias_mapping, instructions = get_alias_mapping_and_instructions()
    bible_df = load_bible_data()
    if bible_df is None or bible_df.empty:
        logger.warning(get_rule("bible_not_available"))
        import pandas as pd
        bible_df = pd.DataFrame(columns=["FAQ", "Answers", "Verification", "rule"])
    # Используем общие инструкции (без '=') для формирования системного контекста
    system_rule_text = "\n".join(instructions)
    system_message = {"role": "system", "content": system_rule_text}
    messages.append(system_message)
    
    spreadsheet_id = find_client_file_id(client_code)
    if spreadsheet_id:
        sheets_service = get_sheets_service()
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A:B"
        ).execute()
        values = result.get("values", [])
        if len(values) >= 2:
            conversation_rows = values[2:]
            logger.info(get_rule("client_conversation_found").format(count=len(conversation_rows), client=client_code))
            for row in conversation_rows:
                if len(row) >= 1 and row[0].strip():
                    messages.append({"role": "user", "content": row[0].strip()})
                if len(row) >= 2 and row[1].strip():
                    messages.append({"role": "assistant", "content": row[1].strip()})
    else:
        logger.info(get_rule("client_file_not_found"))
    return messages

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        logger.info(f"Запрос на регистрацию клиента: {data}")
        result = register_or_update_client(data)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        logger.info(f"Запрос на верификацию кода: {data}")
        code = data.get('code', '')
        client_data = verify_client_code(code)
        if client_data:
            return jsonify({'status': 'success', 'clientData': client_data}), 200
        return jsonify({'status': 'error', 'message': get_rule("invalid_code_message")}), 404
    except Exception as e:
        logger.error(f"Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        logger.info(f"Запрос на чат: {data}")
        user_message = data.get("message", "")
        client_code = data.get("client_code", "")
        if not user_message or not client_code:
            logger.error(get_rule("empty_message_error"))
            return jsonify({'error': get_rule("empty_message_error")}), 400

        update_last_visit(client_code)
        update_activity_status()
        
        if client_code in pending_guiding:
            pending = pending_guiding[client_code]
            pending.setdefault("answers", []).append(user_message)
            pending["current_index"] += 1
            if pending["current_index"] < len(pending["guiding_questions"]):
                response_message = pending["guiding_questions"][pending["current_index"]]
            else:
                base_price_str = pending.get("base_price", get_price_response(pending["vehicle_type"], direction="Ro_Ge"))
                try:
                    base_price = parse_price(base_price_str)
                    multiplier = 1.0
                    fee = 0
                    driver_info = None
                    for ans in pending["answers"]:
                        if get_rule("driver_without").lower() in ans.lower():
                            driver_info = "without"
                        elif get_rule("driver_with").lower() in ans.lower():
                            driver_info = "with"
                        if get_rule("adr_condition").lower() in ans.lower():
                            multiplier = 1.2
                    if driver_info == "without":
                        fee = 100
                    final_cost = (base_price + fee) * multiplier
                    final_price = get_rule("tariff_response_template").format(base_price=base_price, final_cost=final_cost)
                except Exception as ex:
                    final_price = get_rule("fallback_price_message").format(base_price=base_price_str, answers=", ".join(pending['answers']))
                response_message = f"{get_rule('thank_you_message')} {final_price}"
                del pending_guiding[client_code]
        elif any(keyword in user_message.lower() for keyword in PRICE_KEYWORDS):
            msg_lower = user_message.lower()
            if "поти" in msg_lower and "констанц" in msg_lower:
                if msg_lower.index("поти") < msg_lower.index("констанц"):
                    direction = "Ge_Ro"
                else:
                    direction = "Ro_Ge"
            else:
                direction = "Ro_Ge"

            vehicle_type = get_vehicle_type(user_message)
            if not vehicle_type:
                response_message = get_rule("vehicle_type_not_found")
            else:
                base_price_str = get_price_response(vehicle_type, direction)
                if base_price_str:
                    response_message = base_price_str
                else:
                    response_message = get_rule("tariff_info_missing").format(vehicle_type=vehicle_type)
        else:
            messages = prepare_chat_context(client_code)
            messages.append({"role": "user", "content": user_message})
            try:
                openai_resp = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=150,
                    timeout=30
                )
                assistant_reply = openai_resp['choices'][0]['message']['content']
            except Exception as e:
                logger.error(f"Ошибка OpenAI: {e}")
                assistant_reply = "Извините, произошла ошибка при обработке запроса."
            response_message = assistant_reply

        add_message_to_client_file(client_code, user_message, is_assistant=False)
        add_message_to_client_file(client_code, response_message, is_assistant=True)
        logger.info(f"Ответ: {response_message}")
        return jsonify({'reply': response_message}), 200
    except Exception as e:
        logger.error(f"Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get-price', methods=['POST'])
def get_price():
    try:
        data = request.json
        vehicle_text = data.get("vehicle", data.get("vehicle_description", ""))
        direction = data.get("direction", "Ro_Ge")
        if not vehicle_text:
            logger.error(get_rule("empty_vehicle_text"))
            return jsonify({"error": get_rule("empty_vehicle_text")}), 400
        vehicle_type = get_vehicle_type(vehicle_text)
        if not vehicle_type:
            return jsonify({"error": get_rule("vehicle_type_not_found")}), 404
        price_response = get_price_response(vehicle_type, direction)
        return jsonify({"price": price_response}), 200
    except Exception as e:
        logger.error(f"Ошибка в /get-price: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": get_rule("server_running")}), 200

from telegram.ext import ConversationHandler

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error(get_rule("telegram_token_missing"))
    exit(1)

BIBLE_ASK_ACTION, BIBLE_ASK_QUESTION, BIBLE_ASK_ANSWER = range(3)

async def bible_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(get_rule("telegram_bible_start"))
    return BIBLE_ASK_ACTION

async def ask_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    action = update.message.text.strip().lower()
    if action == "add":
        context.user_data['action'] = 'add'
        await update.message.reply_text(get_rule("telegram_ask_question"))
        return BIBLE_ASK_QUESTION
    elif action == "cancel":
        return await cancel_bible(update, context)
    else:
        await update.message.reply_text(get_rule("telegram_invalid_value"))
        return BIBLE_ASK_ACTION

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    question = update.message.text.strip()
    context.user_data['question'] = question
    await update.message.reply_text(get_rule("telegram_ask_answer"))
    return BIBLE_ASK_ANSWER

async def ask_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip()
    question = context.user_data.get('question')
    logger.info(f"Сохранение пары: {question} | {answer}")
    try:
        save_bible_pair(question, answer)
    except Exception as e:
        logger.error(f"Ошибка при сохранении пары в Bible: {e}")
    await update.message.reply_text(get_rule("telegram_pair_saved"))
    return ConversationHandler.END

async def cancel_bible(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(get_rule("telegram_cancel"))
    return ConversationHandler.END

bible_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("bible", bible_start)],
    states={
        BIBLE_ASK_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_action)],
        BIBLE_ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_question)],
        BIBLE_ASK_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_answer)],
    },
    fallbacks=[CommandHandler("cancel", cancel_bible)]
)

application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
bot = application.bot
application.add_handler(bible_conv_handler)

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        global_loop.run_until_complete(application.process_update(update))
        return 'OK', 200
    except Exception as e:
        logger.error(f"Ошибка обновления Telegram: {e}")
        return jsonify({'error': str(e)}), 500

global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error(get_rule("webhook_url_missing"))
        exit(1)
    global_loop.run_until_complete(application.initialize())
    global_loop.run_until_complete(bot.set_webhook(WEBHOOK_URL))
    logger.info(f"Webhook установлен: {WEBHOOK_URL}")
    logger.info(f"Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
