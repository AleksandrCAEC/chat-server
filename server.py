from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from openai import OpenAI
import requests
from clientdata import register_or_update_client, verify_client_code  # Импортируем функции из clientdata.py
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),  # Логи записываются в файл app.log
        logging.StreamHandler()  # Логи выводятся в консоль
    ]
)
logger = logging.getLogger(__name__)

# Указание пути к файлу service_account_json
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"

# Инициализация клиента OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Инициализация приложения Flask
app = Flask(__name__)
CORS(app)

# Отправка уведомлений в Telegram
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

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        logger.info(f"Данные, полученные от клиента: {data}")  # Логируем данные
        name = data.get('name', 'Неизвестный пользователь')
        email = data.get('email', '')
        phone = data.get('phone', '')

        if not email or not phone:
            logger.error("Отсутствует email или телефон.")
            return jsonify({'error': 'Email и телефон обязательны.'}), 400

        # Регистрация или обновление клиента через clientdata.py
        result = register_or_update_client(data)
        send_telegram_notification(f"🆕 Новый пользователь зарегистрирован: {name}, {email}, {phone}, Код: {result['uniqueCode']}")

        return jsonify(result), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        logger.info(f"Данные, полученные от клиента: {data}")  # Логируем данные
        code = data.get('code', '')

        if not code:
            logger.error("Код клиента не был передан.")
            return jsonify({'error': 'Код клиента обязателен.'}), 400

        # Проверка кода клиента через clientdata.py
        client_data = verify_client_code(code)
        if client_data is not None:
            send_telegram_notification(f"🔁 Пользователь вернулся: {client_data['Name']}, {client_data['Phone']}, {client_data['Email']}, Код: {code}")
            return jsonify({'status': 'success', 'clientData': client_data}), 200
        logger.error(f"Код клиента не найден: {code}")
        return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        logger.error(f"❌ Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')

        if not user_message:
            return jsonify({'error': 'Сообщение не может быть пустым'}), 400

        # Используем новый метод для взаимодействия с OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "assistant", "content": "Здравствуйте! Чем могу помочь?"},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150
        )

        # Получаем ответ от модели
        reply = response.choices[0].message.content.strip()
        return jsonify({'reply': reply}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

# Добавляем логирование перед запуском сервера
@app.route('/')
def home():
    return jsonify({"status": "Server is running!"}), 200

logging.basicConfig(level=logging.INFO)
logging.info("✅ Server is starting...")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Используем порт из окружения
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
