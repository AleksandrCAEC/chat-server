import os
import re
import logging
import asyncio
import pprint
from flask import Flask, request, jsonify
import openai
import requests
from datetime import datetime
from clientdata import register_or_update_client, verify_client_code, update_last_visit, update_activity_status
from client_caec import add_message_to_client_file, CLIENT_FILES_DIR
from bible import load_bible_data
from price_handler import check_ferry_price
from flask_cors import CORS
import openpyxl

# Импорты для Telegram Bot (python-telegram-bot v20+)
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Установка пути к файлу service_account_json
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
logger.info("Текущие переменные окружения:")
pprint.pprint(dict(os.environ))

# Функция подготовки контекста для диалога: читает Bible.xlsx и историю переписки клиента.
def prepare_chat_context(client_code):
    messages = []
    bible_df = load_bible_data()
    if bible_df is None:
        raise Exception("Bible.xlsx не найден или недоступен.")
    bible_context = "Информация о компании (FAQ):\n"
    for index, row in bible_df.iterrows():
        faq = row.get("FAQ", "")
        answer = row.get("Answers", "")
        verification = str(row.get("Verification", "")).strip().upper()
        # Если в Verification НЕ стоит "CHECK", пара считается подтвержденной.
        if faq and answer and verification != "CHECK":
            bible_context += f"Вопрос: {faq}\nОтвет: {answer}\n\n"
    system_message = {
        "role": "system",
        "content": f"Вы – умный ассистент компании CAEC. Используйте следующую информацию для ответов:\n{bible_context}"
    }
    messages.append(system_message)
    
    client_file_path = os.path.join(CLIENT_FILES_DIR, f"Client_{client_code}.xlsx")
    if os.path.exists(client_file_path):
        try:
            wb = openpyxl.load_workbook(client_file_path, data_only=True)
            ws = wb.active
            # Предполагается, что первые две строки содержат заголовок и базовые данные клиента,
            # а переписка начинается с 3-й строки.
            for row in ws.iter_rows(min_row=3, values_only=True):
                client_msg = row[0]
                assistant_msg = row[1]
                if client_msg and isinstance(client_msg, str):
                    messages.append({"role": "user", "content": client_msg})
                if assistant_msg and isinstance(assistant_msg, str):
                    messages.append({"role": "assistant", "content": assistant_msg})
        except Exception as e:
            logger.error(f"Ошибка при чтении файла клиента {client_file_path}: {e}")
    return messages

# Ключевые слова для распознавания запроса о цене.
PRICE_KEYWORDS = ["цена", "прайс", "сколько стоит", "во сколько обойдется"]

def is_price_query(text):
    lower_text = text.lower()
    return any(keyword in lower_text for keyword in PRICE_KEYWORDS)

def get_vehicle_type(text):
    known_types = {"truck": "Truck", "грузовик": "Truck", "fura": "Fura", "фура": "Fura"}
    for key, standard in known_types.items():
        if key in text.lower():
            return standard
    return None

def get_price_response(vehicle_type, direction="Ro_Ge"):
    try:
        response = check_ferry_price(vehicle_type, direction)
        return response
    except Exception as e:
        logger.error(f"Ошибка при получении цены для {vehicle_type}: {e}")
        return "Произошла ошибка при получении актуальной цены. Пожалуйста, попробуйте позже."

@app.route('/test', methods=['GET'])
def test():
    return "Test route works", 200

@app.route('/webhook_test', methods=['GET'])
def telegram_webhook_test():
    return "Webhook endpoint is active", 200

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        logger.info(f"Получен запрос на регистрацию клиента: {data}")
        result = register_or_update_client(data)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        logger.info(f"Получен запрос на верификацию кода: {data}")
        code = data.get('code', '')
        client_data = verify_client_code(code)
        if client_data:
            return jsonify({'status': 'success', 'clientData': client_data}), 200
        return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        logger.error(f"Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        logger.info(f"Получен запрос на чат: {data}")
        user_message = data.get("message", "")
        client_code = data.get("client_code", "")
        
        # Обновляем данные клиента (Last Visit и активность)
        update_last_visit(client_code)
        update_activity_status()
        
        # Если запрос содержит ключевые слова о цене и в Bible.xlsx найден маркер PRICE_QUERY,
        # то используем специальную обработку для цены.
        if is_price_query(user_message):
            bible_df = load_bible_data()
            price_marker_found = False
            # Ищем среди FAQ ответы, в которых указан маркер PRICE_QUERY (без кавычек)
            for idx, row in bible_df.iterrows():
                faq = row.get("FAQ", "").lower()
                answer = row.get("Answers", "").lower()
                if is_price_query(user_message) and "price_query" in answer:
                    price_marker_found = True
                    break
            if price_marker_found:
                vehicle_type = get_vehicle_type(user_message)
                if not vehicle_type:
                    response_message = ("Для определения цены, пожалуйста, уточните тип транспортного средства "
                                        "(например, грузовик или фура).")
                else:
                    response_message = get_price_response(vehicle_type, direction="Ro_Ge")
            else:
                # Если маркер не найден, продолжаем стандартную обработку через OpenAI
                context_messages = prepare_chat_context(client_code)
                context_messages.append({"role": "user", "content": user_message})
                openai_response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=context_messages,
                    max_tokens=150
                )
                response_message = openai_response['choices'][0]['message']['content'].strip()
        else:
            # Стандартная обработка: собираем весь контекст (Bible.xlsx + история переписки)
            context_messages = prepare_chat_context(client_code)
            context_messages.append({"role": "user", "content": user_message})
            openai_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=context_messages,
                max_tokens=150
            )
            response_message = openai_response['choices'][0]['message']['content'].strip()
        
        # Сохраняем переписку (сначала запрос клиента, затем ответ ассистента)
        add_message_to_client_file(client_code, user_message, is_assistant=False)
        add_message_to_client_file(client_code, response_message, is_assistant=True)
        
        logger.info(f"Ответ от сервера: {response_message}")
        return jsonify({"reply": response_message}), 200
    except Exception as e:
        logger.error(f"Ошибка в /chat: {e}")
        return jsonify({"error": str(e)}), 500

# Telegram Bot Integration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("Переменная окружения TELEGRAM_BOT_TOKEN не задана!")
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
    logger.info(f"Сохраняем пару: Вопрос: {question} | Ответ: {answer}")
    try:
        from bible import save_bible_pair
        save_bible_pair(question, answer)
    except Exception as e:
        logger.error(f"Ошибка сохранения пары в Bible.xlsx: {e}")
    await update.message.reply_text("Пара вопрос-ответ сохранена с отметкой 'Check'.")
    return ConversationHandler.END

async def cancel_bible(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

from telegram.ext import ConversationHandler
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
        logger.error(f"Ошибка обработки Telegram update: {e}")
        return jsonify({'error': str(e)}), 500

global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error("Переменная окружения WEBHOOK_URL не задана!")
        exit(1)
    global_loop.run_until_complete(application.initialize())
    global_loop.run_until_complete(bot.set_webhook(WEBHOOK_URL))
    logger.info(f"Webhook установлен на {WEBHOOK_URL}")
    logger.info(f"✅ Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
