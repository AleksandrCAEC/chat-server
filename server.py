import os
import re
import logging
import asyncio
import pprint
from flask import Flask, request, jsonify
import openai
import requests
from datetime import datetime
from clientdata import register_or_update_client, verify_client_code, update_last_visit
from client_caec import add_message_to_client_file, find_client_file_id, get_sheets_service, CLIENT_FILES_DIR
from bible import load_bible_data, save_bible_pair
from price_handler import check_ferry_price, load_price_data  # load_price_data для получения данных из Price.xlsx
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

# Инициализация OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Инициализация Flask-приложения и CORS
app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("server.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logger.info("Текущие переменные окружения:")
pprint.pprint(dict(os.environ))

# Глобальный словарь для хранения состояния последовательного уточнения (guiding questions)
pending_guiding = {}

###############################################
# ФУНКЦИЯ ОТПРАВКИ УВЕДОМЛЕНИЙ ЧЕРЕЗ TELEGRAM
###############################################
def send_telegram_notification(message):
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not telegram_bot_token or not telegram_chat_id:
        logger.error("Переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID не настроены.")
        return
    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"✅ Telegram уведомление отправлено: {response.json()}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка при отправке Telegram уведомления: {e}")

###############################################
# ЭНДПОИНТ /register-client
###############################################
@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        logger.info(f"Получен запрос на регистрацию клиента: {data}")
        result = register_or_update_client(data)
        if result.get("isNewClient", True):
            send_telegram_notification(f"🆕 Новый пользователь зарегистрирован: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}")
        else:
            send_telegram_notification(f"🔙 Пользователь вернулся: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}")
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

###############################################
# ЭНДПОИНТ /verify-code
###############################################
@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        logger.info(f"Получен запрос на верификацию кода: {data}")
        code = data.get('code', '')
        client_data = verify_client_code(code)
        if client_data:
            send_telegram_notification(f"🔙 Пользователь вернулся: {client_data['Name']}, {client_data['Email']}, {client_data['Phone']}, Код: {code}")
            return jsonify({'status': 'success', 'clientData': client_data}), 200
        return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        logger.error(f"❌ Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 400

###############################################
# ЭНДПОИНТ /get-price - для тестирования тарифа через Postman
###############################################
@app.route('/get-price', methods=['POST'])
def get_price():
    """
    Эндпоинт ожидает POST-запрос с JSON-телом:
    {
       "vehicle_description": "Фура 17 метров, Констанца-Поти, без ADR, без водителя",
       "direction": "Ro_Ge" // этот параметр не обязателен, по умолчанию используется "Ro_Ge"
    }
    """
    data = request.get_json()
    if not data or "vehicle_description" not in data:
        return jsonify({"error": "Не передано описание транспортного средства"}), 400

    vehicle_description = data["vehicle_description"]
    direction = data.get("direction", "Ro_Ge")
    
    # Вызов функции для получения тарифа (логика из price_handler.py)
    result = check_ferry_price(vehicle_description, direction=direction)
    return jsonify({"price": result}), 200

###############################################
# ЭНДПОИНТ /chat
###############################################
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
        
        # Если клиент уже находится в режиме уточнения (pending guiding questions)
        if client_code in pending_guiding:
            pending = pending_guiding[client_code]
            pending.setdefault("answers", []).append(user_message)
            pending["current_index"] += 1
            if pending["current_index"] < len(pending["conditions"]):
                response_message = pending["conditions"][pending["current_index"]]
            else:
                final_price = check_ferry_price(pending["vehicle_type"], direction="Ro_Ge")
                response_message = f"Спасибо, ваши ответы приняты. {final_price}"
                del pending_guiding[client_code]
        elif "цена" in user_message.lower() or "прайс" in user_message.lower():
            # Здесь используется вызов, если клиент спрашивает о цене
            # Обратите внимание, что эта ветка может требовать доработки в будущем
            response_message = check_ferry_price(vehicle_description=user_message, direction="Ro_Ge")
        else:
            # Стандартная обработка: формируем контекст из Bible.xlsx и истории переписки, затем вызываем OpenAI
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
        
        logger.info(f"Ответ от OpenAI/price_handler: {response_message}")
        return jsonify({'reply': response_message}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

###############################################
# ЭНДПОИНТ домашней страницы (/)
###############################################
@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "Server is running!"}), 200

###############################################
# Интеграция Telegram Bot для команды /bible
###############################################
from telegram.ext import ConversationHandler

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
        save_bible_pair(question, answer)
    except Exception as e:
        logger.error(f"Ошибка сохранения пары в Bible.xlsx: {e}")
    await update.message.reply_text("Пара вопрос-ответ сохранена с отметкой 'Check'.")
    return ConversationHandler.END

async def cancel_bible(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена.")
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
        logger.error(f"Ошибка обработки Telegram update: {e}")
        return jsonify({'error': str(e)}), 500

###############################################
# Основной блок запуска
###############################################
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
