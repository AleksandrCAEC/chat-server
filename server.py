from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import openai
import requests
from clientdata import register_or_update_client, verify_client_code
from client_caec import add_message_to_client_file
import logging
from logging.handlers import RotatingFileHandler
from functools import lru_cache
from datetime import datetime

# Настройка логирования
def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = RotatingFileHandler("server.log", maxBytes=1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

logger = setup_logging()

# Указание пути к файлу service_account_json
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"

# Инициализация клиента OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Инициализация приложения Flask
app = Flask(__name__)
CORS(app)

# Кэширование запросов к OpenAI
@lru_cache(maxsize=100)
def get_openai_response(user_message):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Вы - помощник компании CAEC."},
            {"role": "user", "content": user_message}
        ],
        max_tokens=150
    )
    return response['choices'][0]['message']['content'].strip()

# Отправка уведомлений в Telegram
def send_telegram_notification(message):
    try:
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not telegram_bot_token or not telegram_chat_id:
            raise ValueError("Переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID не настроены.")

        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"✅ Telegram уведомление отправлено: {response.json()}")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке Telegram уведомления: {e}")

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

        try:
            reply = get_openai_response(user_message)
        except openai.error.OpenAIError as e:
            logger.error(f"Ошибка OpenAI: {e}")
            return jsonify({'error': 'Ошибка при обработке запроса OpenAI'}), 500

        try:
            add_message_to_client_file(client_code, user_message, is_assistant=False)
            add_message_to_client_file(client_code, reply, is_assistant=True)
        except Exception as e:
            logger.error(f"Ошибка при записи в файл: {e}")
            return jsonify({'error': 'Ошибка при сохранении сообщения'}), 500

        logger.info(f"Ответ от OpenAI: {reply}")
        return jsonify({'reply': reply}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def home():
    return jsonify({"status": "Server is running!"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"✅ Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
