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
import pymorphy2  # Для лемматизации русского текста

from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

USE_PRICE_FILE = False

# Используем переменную окружения или путь по умолчанию для учетных данных
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
logger.info("Текущие переменные окружения:")
pprint.pprint(dict(os.environ))

pending_guiding = {}

PRICE_KEYWORDS = ["цена", "прайс", "сколько стоит", "во сколько обойдется"]

def get_vehicle_type(client_text):
    # Инициализируем лемматизатор
    morph = pymorphy2.MorphAnalyzer()
    normalized_words = [morph.parse(word)[0].normal_form for word in client_text.split()]
    
    # Определяем тип транспортного средства через лемматизацию
    known_types = {"truck": "truck", "фура": "фура"}
    for word in normalized_words:
        if word in known_types:
            logger.info(f"Определен тип транспортного средства (лемматизация): {known_types[word]}")
            return known_types[word]
    
    # Если лемматизация не сработала, используем fuzzy matching по исходному тексту
    text_lower = client_text.lower()
    matches = difflib.get_close_matches(text_lower, list(known_types.keys()), n=1, cutoff=0.3)
    if matches:
        logger.info(f"Определен тип транспортного средства (fuzzy matching): {known_types[matches[0]]}")
        return known_types[matches[0]]
    
    logger.info("Тип транспортного средства не определен из сообщения клиента.")
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
            logger.error(f"Попытка {attempt+1} ошибки в OpenAI: {e}")
            attempt += 1
            if time.time() - start_time > 180:
                return None
            time.sleep(2)

def prepare_chat_context(client_code):
    messages = []
    bible_df = load_bible_data()
    if bible_df is None:
        raise Exception(get_rule())
    logger.info(f"Bible.xlsx содержит {len(bible_df)} записей.")

    # Собираем все внутренние инструкции (правила) из строк, где FAQ = "-" и Verification = "RULE"
    rules_df = bible_df[(bible_df["FAQ"].str.strip() == "-") & (bible_df["Verification"].str.upper() == "RULE")]
    rules_text = "\n".join(rules_df["Answers"].tolist())
    
    strict_instructions = (
        "ВНИМАНИЕ: Ниже приведены обязательные правила, которым вы должны строго следовать. "
        "1. Все инструкции, полученные из документа Bible.xlsx, имеют высший приоритет и обязательны к исполнению. "
        "2. Вы не должны отклоняться от этих правил ни при каких обстоятельствах. "
        "3. При формировании ответов используйте исключительно данные, предоставленные в этих инструкциях. "
        "4. Любые дополнительные предположения или информация, противоречащие указанным правилам, должны игнорироваться."
    )
    
    system_message = {
        "role": "system",
        "content": f"{strict_instructions}\n\n{rules_text}"
    }
    messages.append(system_message)
    
    # Вторая часть контекста: история переписки, хранящаяся в уникальном файле клиента (Client_CAECxxxxxxx.xlsx)
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
            logger.info(f"Найдено {len(conversation_rows)} строк переписки для клиента {client_code}.")
            for row in conversation_rows:
                if len(row) >= 1 and row[0].strip():
                    messages.append({"role": "user", "content": row[0].strip()})
                if len(row) >= 2 and row[1].strip():
                    messages.append({"role": "assistant", "content": row[1].strip()})
    else:
        logger.info(f"Файл клиента с кодом {client_code} не найден.")
    return messages

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        logger.info(f"Получен запрос на регистрацию клиента: {data}")
        result = register_or_update_client(data)
        if result.get("isNewClient", True):
            send_telegram_notification(
                f"🆕 Новый пользователь зарегистрирован: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}"
            )
        else:
            send_telegram_notification(
                f"🔙 Пользователь вернулся: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}"
            )
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        logger.info(f"Получен запрос на верификацию кода: {data}")
        code = data.get('code', '')
        client_data = verify_client_code(code)
        if client_data:
            send_telegram_notification(
                f"🔙 Пользователь вернулся: {client_data['Name']}, {client_data['Email']}, {client_data['Phone']}, Код: {code}"
            )
            return jsonify({'status': 'success', 'clientData': client_data}), 200
        return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        logger.error(f"❌ Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        logger.info(f"Получен запрос на чат: {data}")
        user_message = data.get("message", "")
        client_code = data.get("client_code", "")
        if not user_message or not client_code:
            logger.error("Ошибка: Сообщение и код клиента не могут быть пустыми")
            return jsonify({'error': 'Сообщение и код клиента не могут быть пустыми'}), 400

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
                        if "без водителя" in ans.lower():
                            driver_info = "without"
                        elif "с водителем" in ans.lower():
                            driver_info = "with"
                        if "adr" in ans.lower():
                            multiplier = 1.2
                    if driver_info == "without":
                        fee = 100
                    final_cost = (base_price + fee) * multiplier
                    final_price = f"Базовая цена: {base_price} евро. Итоговая стоимость с учетом ваших ответов: {final_cost} евро."
                except Exception as ex:
                    final_price = f"Базовая цена: {base_price_str}. Ваши ответы: {', '.join(pending['answers'])}."
                response_message = f"Спасибо, ваши ответы приняты. {final_price}"
                del pending_guiding[client_code]
        elif is_price_query(user_message):
            vehicle_type = get_vehicle_type(user_message)
            if not vehicle_type:
                response_message = "Укажите, пожалуйста, тип транспортного средства (например, фура)."
            else:
                response_message = get_price_response(vehicle_type)
        else:
            messages = prepare_chat_context(client_code)
            messages.append({"role": "user", "content": user_message})
            openai_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=150
            )
            response_message = openai_response['choices'][0]['message']['content'].strip()
        
        add_message_to_client_file(client_code, user_message, is_assistant=False)
        add_message_to_client_file(client_code, response_message, is_assistant=True)
        
        logger.info(f"Ответ от АСС: {response_message}")
        return jsonify({'reply': response_message}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "Server is running!"}), 200

##############################################
# Интеграция Telegram Bot для команды /bible
##############################################
from telegram.ext import ConversationHandler

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("Переменная окружения TELEGRAM_BOT_TOKEN не настроена!")
    exit(1)

BIBLE_ASK_ACTION, BIBLE_ASK_QUESTION, BIBLE_ASK_ANSWER = range(3)

async def bible_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите 'add' для добавления новой пары вопрос-ответ, или 'cancel' для отмены.")
    return BIBLE_ASK_ACTION

async def ask_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    action = update.message.text.strip().lower()
    if action == "add":
        context.user_data['action'] = 'add'
        await update.message.reply_text("Введите новый вопрос:")
        return BIBLE_ASK_QUESTION
    elif action == "cancel":
        return await cancel_bible(update, context)
    else:
        await update.message.reply_text("Неверное значение. Введите 'add' или 'cancel'.")
        return BIBLE_ASK_ACTION

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    question = update.message.text.strip()
    context.user_data['question'] = question
    await update.message.reply_text("Введите ответ для этого вопроса:")
    return BIBLE_ASK_ANSWER

async def ask_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip()
    question = context.user_data.get('question')
    logger.info(f"Сохраняем пару: Вопрос='{question}', Ответ='{answer}'")
    try:
        save_bible_pair(question, answer)
    except Exception as e:
        logger.error(f"Ошибка сохранения пары в Bible.xlsx: {e}")
    await update.message.reply_text("Пара вопрос-ответ сохранена. Статус: 'Check'.")
    return ConversationHandler.END

async def cancel_bible(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

bible_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("bible", bible_start)],
    states={
        BIBLE_ASK_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_action)],
        BIBLE_ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_question)],
        BIBLE_ASK_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_answer)]
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
        logger.error(f"Ошибка обработки Telegram update: {e}")
        return jsonify({'error': str(e)}), 500

global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)
if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error("Не задана переменная окружения WEBHOOK_URL!")
        exit(1)
    global_loop.run_until_complete(application.initialize())
    global_loop.run_until_complete(bot.set_webhook(WEBHOOK_URL))
    logger.info(f"Webhook установлен: {WEBHOOK_URL}")
    logger.info(f"Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
