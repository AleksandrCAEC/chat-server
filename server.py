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

# Импортируем pymorphy2 для лемматизации
import pymorphy2
morph = pymorphy2.MorphAnalyzer()

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

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"
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
    Функция нормализует входящий текст, приводя каждое слово к его начальной (лемматизированной) форме.
    """
    words = text.split()
    lemmatized_words = [morph.parse(word)[0].normal_form for word in words]
    return " ".join(lemmatized_words)

def get_vehicle_type(client_text):
    """
    Определяет тип транспортного средства на основе входящего текста.
    Использует морфологическую обработку для нормализации терминов.
    Если в нормализованном тексте обнаружено слово "фура" или "еврофура", 
    возвращается 'standard truck with trailer (up to 17m)' в соответствии с правилом из Bible.xlsx.
    """
    # Приводим исходный текст к нижнему регистру и лемматизируем его
    normalized_text = lemmatize_text(client_text.lower())
    logger.info(f"Normalized text: {normalized_text}")
    
    # Применяем правило из Bible.xlsx: все формы слова "фура" или "еврофура" нормализуются
    if "фура" in normalized_text or "еврофура" in normalized_text:
        logger.info("Detected lemma 'фура' or 'еврофура' in input. Mapping to 'standard truck with trailer (up to 17m)'.")
        return "standard truck with trailer (up to 17m)"
    
    # Проверяем алиасы для конкретных вариантов
    aliases = {
        "грузовик 17 м": "standard truck with trailer (up to 17m)",
        "грузовик 17м": "standard truck with trailer (up to 17m)"
    }
    if client_text.lower() in aliases:
        mapped = aliases[client_text.lower()]
        logger.info(f"Alias mapping applied: '{client_text.lower()}' -> '{mapped}'")
        return mapped
    
    # Используем данные с сайта
    from price import get_ferry_prices
    data = get_ferry_prices()
    vehicle_types = list(data.keys())
    matches = difflib.get_close_matches(client_text.lower(), [vt.lower() for vt in vehicle_types], n=1, cutoff=0.3)
    if matches:
        for vt in vehicle_types:
            if vt.lower() == matches[0]:
                logger.info(f"Vehicle type identified: {vt}")
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
                send_msg = get_rule("openai_timeout_message")
                return None
            time.sleep(2)

def prepare_chat_context(client_code):
    messages = []
    bible_df = load_bible_data()
    # Если данные из Bible недоступны или пусты, используем пустой DataFrame
    if bible_df is None or bible_df.empty:
        logger.warning(get_rule("bible_not_available"))
        import pandas as pd
        bible_df = pd.DataFrame(columns=["FAQ", "Answers", "Verification", "rule"])
    # Фильтруем строки, где Verification == "Rule"
    rules_df = bible_df[bible_df["Verification"].str.strip().str.upper() == "RULE"]
    system_rules = rules_df["Answers"].dropna().tolist()
    system_rule_text = "\n".join(system_rules)
    # Это внутреннее правило для агента, которое не передается клиенту
    system_message = {"role": "system", "content": system_rule_text}
    messages.append(system_message)
    
    # Поиск истории переписки клиента
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
        logger.info(f"Client registration request: {data}")
        result = register_or_update_client(data)
        if result.get("isNewClient", True):
            send_msg = get_rule("new_client_message").format(**result)
        else:
            send_msg = get_rule("returning_client_message").format(**result)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error in /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        logger.info(f"Verification request: {data}")
        code = data.get('code', '')
        client_data = verify_client_code(code)
        if client_data:
            send_msg = get_rule("verified_client_message").format(code=code, **client_data)
            return jsonify({'status': 'success', 'clientData': client_data}), 200
        return jsonify({'status': 'error', 'message': get_rule("invalid_code_message")}), 404
    except Exception as e:
        logger.error(f"Error in /verify-code: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        logger.info(f"Chat request: {data}")
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
            # Определяем направление доставки на основе порядка упоминания слов "поти" и "констанц" в сообщении
            msg_lower = user_message.lower()
            if "поти" in msg_lower and "констанц" in msg_lower:
                if msg_lower.index("поти") < msg_lower.index("констанц"):
                    direction = "Ge_Ro"  # Из Поти в Констанцу
                else:
                    direction = "Ro_Ge"  # Из Констанцы в Поти
            else:
                direction = "Ro_Ge"  # Значение по умолчанию

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
            openai_response = get_openai_response(messages)
            if openai_response is None:
                response_message = get_rule("service_unavailable")
            else:
                response_message = openai_response['choices'][0]['message']['content'].strip()
        
        add_message_to_client_file(client_code, user_message, is_assistant=False)
        add_message_to_client_file(client_code, response_message, is_assistant=True)
        
        logger.info(f"Response: {response_message}")
        return jsonify({'reply': response_message}), 200
    except Exception as e:
        logger.error(f"Error in /chat: {e}")
        return jsonify({'error': str(e)}), 500

# Новый эндпоинт для обработки запроса цены (/get-price)
@app.route('/get-price', methods=['POST'])
def get_price():
    try:
        data = request.json
        # Поддержка ключей "vehicle" и "vehicle_description"
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
        logger.error(f"Error in /get-price: {e}")
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
    logger.info(f"Saving pair: {question} | {answer}")
    try:
        save_bible_pair(question, answer)
    except Exception as e:
        logger.error(f"Error saving pair in Bible: {e}")
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
        logger.error(f"Telegram update error: {e}")
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
    logger.info(f"Webhook set to {WEBHOOK_URL}")
    logger.info(f"Server running on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
