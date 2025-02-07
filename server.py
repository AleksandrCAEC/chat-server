# server.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import openai
import requests
import logging
from datetime import datetime
from clientdata import register_or_update_client, verify_client_code, update_last_visit, update_activity_status
from client_caec import add_message_to_client_file  # Функция для работы с историей переписки
from bible import load_bible_data  # Модуль для работы с Bible.xlsx

# Telegram импорты
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext

# Установка пути к файлу service_account_json
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"

# Инициализация OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Инициализация приложения Flask
app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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

def prepare_chat_context(client_code):
    """
    Формирует список сообщений для запроса к OpenAI:
      1. Загружает данные из Bible.xlsx и создает системное сообщение с информацией о компании.
      2. Если существует файл истории переписки клиента, считывает его и добавляет предыдущие сообщения.
    """
    messages = []
    bible_df = load_bible_data()
    if bible_df is None:
        raise Exception("Bible.xlsx не найден или недоступен.")
    bible_context = "Информация о компании (FAQ):\n"
    for index, row in bible_df.iterrows():
        faq = row.get("FAQ", "")
        answer = row.get("Answers", "")
        if faq and answer:
            bible_context += f"Вопрос: {faq}\nОтвет: {answer}\n\n"
    system_message = {
        "role": "system",
        "content": f"Вы – умный ассистент компании CAEC. Используйте следующую информацию для ответов:\n{bible_context}"
    }
    messages.append(system_message)
    import openpyxl
    from client_caec import CLIENT_FILES_DIR
    client_file_path = os.path.join(CLIENT_FILES_DIR, f"Client_{client_code}.xlsx")
    if os.path.exists(client_file_path):
        try:
            wb = openpyxl.load_workbook(client_file_path, data_only=True)
            ws = wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                client_msg = row[0]
                assistant_msg = row[1]
                if client_msg and isinstance(client_msg, str):
                    messages.append({"role": "user", "content": client_msg})
                if assistant_msg and isinstance(assistant_msg, str):
                    messages.append({"role": "assistant", "content": assistant_msg})
        except Exception as e:
            logger.error(f"Ошибка при чтении файла клиента {client_file_path}: {e}")
    return messages

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

@app.route('/')
def home():
    return jsonify({"status": "Server is running!"}), 200

# ---------------------------------------------------------------------
# Интеграция Telegram-бота для команды /bible через вебхук

# Определяем состояния для обработки диалога /bible
ASK_ACTION, ASK_QUESTION, ASK_ANSWER = range(3)

def bible_start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Введите 'add' для добавления новой пары вопрос-ответ, или 'cancel' для отмены.")
    return ASK_ACTION

def ask_action(update: Update, context: CallbackContext) -> int:
    action = update.message.text.strip().lower()
    if action == "add":
        context.user_data['action'] = 'add'
        update.message.reply_text("Введите новый вопрос:")
        return ASK_QUESTION
    else:
        update.message.reply_text("Неверное значение. Введите 'add' или 'cancel'.")
        return ASK_ACTION

def ask_question(update: Update, context: CallbackContext) -> int:
    question = update.message.text.strip()
    context.user_data['question'] = question
    update.message.reply_text("Введите ответ для этого вопроса:")
    return ASK_ANSWER

def ask_answer(update: Update, context: CallbackContext) -> int:
    answer = update.message.text.strip()
    question = context.user_data.get('question')
    logger.info(f"Сохраняем пару: Вопрос: {question} | Ответ: {answer}")
    update.message.reply_text("Пара вопрос-ответ сохранена с отметкой 'Check'.")
    return ConversationHandler.END

def cancel_bible(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[CommandHandler('bible', bible_start)],
    states={
        ASK_ACTION: [MessageHandler(Filters.text & ~Filters.command, ask_action)],
        ASK_QUESTION: [MessageHandler(Filters.text & ~Filters.command, ask_question)],
        ASK_ANSWER: [MessageHandler(Filters.text & ~Filters.command, ask_answer)],
    },
    fallbacks=[CommandHandler('cancel', cancel_bible)]
)
# Регистрируем обработчик команды /bible в диспетчере Telegram
dispatcher.add_handler(conv_handler)

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'OK', 200

@app.route('/webhook_test', methods=['GET'])
def telegram_webhook_test():
    return "Webhook endpoint is active", 200

# ---------------------------------------------------------------------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error("Переменная окружения WEBHOOK_URL не задана!")
        exit(1)
    bot.setWebhook(WEBHOOK_URL)
    logger.info(f"Webhook установлен на {WEBHOOK_URL}")
    logger.info(f"✅ Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
