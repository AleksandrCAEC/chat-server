from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import string
import os
import openai
import requests

# Настройка API-ключа OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app)

# Словарь для хранения данных клиентов
clients = {}

# Telegram Bot Token и Chat ID
TELEGRAM_BOT_TOKEN = "7516690787:AAEemBmimlmIqp37wr4ct10MlkqRMIjQLEw"
TELEGRAM_CHAT_ID = "8074527842"

def generate_unique_code():
    """Генерация уникального кода для клиента."""
    random_digits = ''.join(random.choices(string.digits, k=7))
    return f"CAEC{random_digits}"

def send_telegram_notification(message):
    """Отправка уведомления в Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Ошибка отправки в Telegram: {response.text}")
    except Exception as e:
        print(f"Ошибка при отправке уведомления в Telegram: {e}")

@app.route('/register-client', methods=['POST'])
def register_client():
    """Маршрут для регистрации клиента."""
    try:
        data = request.json
        email = data['email']
        phone = data['phone']

        # Проверка, существует ли клиент с таким email или телефоном
        for code, client_data in clients.items():
            if client_data['email'] == email or client_data['phone'] == phone:
                name = client_data['name']
                return jsonify({'uniqueCode': code, 'message': f'Добро пожаловать обратно, {name}! Ваш код: {code}.'}), 200

        unique_code = generate_unique_code()
        clients[unique_code] = {
            'name': data['name'],
            'phone': phone,
            'email': email
        }

        # Уведомление в Telegram
        send_telegram_notification(
            f"📢 Новый зарегистрированный пользователь:\n"
            f"Имя: {data['name']}\n"
            f"Телефон: {phone}\n"
            f"Email: {email}\n"
            f"Код: {unique_code}"
        )

        return jsonify({'uniqueCode': unique_code, 'message': f'Добро пожаловать, {data["name"]}! Ваш код: {unique_code}.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Маршрут для проверки уникального кода клиента."""
    try:
        data = request.json
        code = data['code']
        if code in clients:
            name = clients[code]['name']
            return jsonify({'status': 'success', 'clientData': clients[code], 'message': f'Добро пожаловать обратно, {name}!'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    """Маршрут для общения с OpenAI."""
    try:
        data = request.json
        user_message = data.get('message', '')

        # Вызов OpenAI API через v1/chat/completions
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "assistant", "content": "Здравствуйте! Чем могу помочь?"},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150
        )

        reply = response['choices'][0]['message']['content'].strip()
        return jsonify({'reply': reply}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
