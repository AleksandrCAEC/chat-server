# server.py
import os
import logging
import asyncio
from flask import Flask, request, jsonify
import openai
import requests
from datetime import datetime
from clientdata import register_or_update_client, verify_client_code, update_last_visit, update_activity_status
from client_caec import add_message_to_client_file
from bible import load_bible_data

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

# Инициализация Flask-приложения
app = Flask(__name__)

# Настройка CORS и логирования
# (оставляем ваш текущий CORS и конфигурацию логирования)
from flask_cors import CORS
CORS(app)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

##############################
# Telegram Bot Setup (async)
##############################

# Получаем токен бота из переменной окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("Переменная окружения TELEGRAM_BOT_TOKEN не задана!")
    exit(1)

# Создаем приложение Telegram
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
bot = application.bot  # Получаем объект Bot

# Состояния для ConversationHandler команды /bible
ASK_ACTION, ASK_QUESTION, ASK_ANSWER = range(3)

# Асинхронные обработчики для команды /bible

async def bible_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите 'add' для добавления новой пары вопрос-ответ, или 'cancel' для отмены.")
    return ASK_ACTION

async def ask_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    action = update.message.text.strip().lower()
    if action == "add":
        context.user_data['action'] = 'add'
        await update.message.reply_text("Введите новый вопрос:")
        return ASK_QUESTION
    else:
        await update.message.reply_text("Неверное значение. Введите 'add' или 'cancel'.")
        return ASK_ACTION

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    question = update.message.text.strip()
    context.user_data['question'] = question
    await update.message.reply_text("Введите ответ для этого вопроса:")
    return ASK_ANSWER

async def ask_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip()
    question = context.user_data.get('question')
    logger.info(f"Сохраняем пару: Вопрос: {question} | Ответ: {answer}")
    # Здесь можно вызвать функцию сохранения пары (например, save_bible_pair(question, answer))
    await update.message.reply_text("Пара вопрос-ответ сохранена с отметкой 'Check'.")
    return ConversationHandler.END

async def cancel_bible(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# Создаем ConversationHandler для команды /bible
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("bible", bible_start)],
    states={
        ASK_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_action)],
        ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_question)],
        ASK_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_answer)],
    },
    fallbacks=[CommandHandler("cancel", cancel_bible)]
)

# Добавляем обработчик в приложение Telegram
application.add_handler(conv_handler)

#####################################
# Остальные маршруты вашего сервера
#####################################

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

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        logger.info(f"Получен запрос на чат: {data}")
        user_message = data.get('message', '')
        client_code = data.get('client_code', '')
        if not user_message or not client_code:
            logger.error("Ошибка: Сообщение и код клиента не могут быть пустыми")
            return jsonify({'error': 'Сообщение и код клиента не могут быть пустыми'}), 400
        update_last_visit(client_code)
        update_activity_status()
        try:
            messages = prepare_chat_context(client_code)
        except Exception as e:
            error_msg = f"Ошибка подготовки контекста: {e}"
            logger.error(error_msg)
            send_telegram_notification(f"Ошибка базы данных: {error_msg}")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
        messages.append({"role": "user", "content": user_message})
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=150
        )
        reply = response['choices'][0]['message']['content'].strip()
        add_message_to_client_file(client_code, user_message, is_assistant=False)
        add_message_to_client_file(client_code, reply, is_assistant=True)
        logger.info(f"Ответ от OpenAI: {reply}")
        return jsonify({'reply': reply}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "Server is running!"}), 200

##############################
# Маршруты для Telegram Webhook
##############################

# Обработка вебхука для Telegram-бота (POST)
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, bot)
    # Запускаем асинхронную обработку обновления
    asyncio.run(application.process_update(update))
    return 'OK', 200

# Тестовый маршрут для проверки работы вебхука (GET)
@app.route('/webhook_test', methods=['GET'])
def telegram_webhook_test():
    return "Webhook endpoint is active", 200

####################################
# Функция для отправки уведомлений в Telegram
####################################
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

####################################
# Основной блок запуска
####################################
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error("Переменная окружения WEBHOOK_URL не задана!")
        exit(1)
    # Устанавливаем вебхук (асинхронно)
    asyncio.run(bot.set_webhook(WEBHOOK_URL))
    logger.info(f"Webhook установлен на {WEBHOOK_URL}")
    logger.info(f"✅ Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
