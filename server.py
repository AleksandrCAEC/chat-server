from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import openai
import requests
from clientdata import register_or_update_client, verify_client_code
from client_caec import add_message_to_client_file  # Импорт функции для добавления сообщения
import logging

# Указание пути к файлу service_account_json
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"

# Инициализация клиента OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Инициализация приложения Flask
app = Flask(__name__)
CORS(app)

# Отправка уведомлений в Telegram
def send_telegram_notification(message):
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not telegram_bot_token or not telegram_chat_id:
        print("Переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID не настроены.")
        return

    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"✅ Telegram уведомление отправлено: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при отправке Telegram уведомления: {e}")

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        result = register_or_update_client(data)

        # Отправляем уведомление в Telegram в зависимости от того, новый клиент или нет
        if result.get("isNewClient", True):
            send_telegram_notification(f"🆕 Новый пользователь зарегистрирован: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}")
        else:
            send_telegram_notification(f"🔙 Пользователь вернулся: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}")

        return jsonify(result), 200
    except Exception as e:
        print(f"❌ Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data.get('code', '')
        client_data = verify_client_code(code)
        if client_data:
            # Отправляем уведомление в Telegram о возвращении клиента
            send_telegram_notification(f"🔙 Пользователь вернулся: {client_data['Name']}, {client_data['Email']}, {client_data['Phone']}, Код: {code}")
            return jsonify({'status': 'success', 'clientData': client_data}), 200
        return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        print(f"❌ Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')
        client_code = data.get('client_code', '')  # Получаем код клиента из запроса

        if not user_message or not client_code:
            return jsonify({'error': 'Сообщение и код клиента не могут быть пустыми'}), 400

        # Используем метод ChatCompletion.create, который принимает параметр messages
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Вы - помощник компании CAEC."},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150
        )

        # Извлекаем ответ
        reply = response['choices'][0]['message']['content'].strip()

        # Добавляем сообщение пользователя в файл клиента
        add_message_to_client_file(client_code, user_message, is_assistant=False)

        # Добавляем ответ ассистента в файл клиента
        add_message_to_client_file(client_code, reply, is_assistant=True)

        return jsonify({'reply': reply}), 200
    except Exception as e:
        print(f"❌ Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def home():
    return jsonify({"status": "Server is running!"}), 200

logging.basicConfig(level=logging.INFO)
logging.info("✅ Server is starting...")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
