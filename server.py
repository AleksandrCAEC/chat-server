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

# Генерация уникального кода клиента
def generate_unique_code():
    random_digits = ''.join(random.choices(string.digits, k=7))
    return f"CAEC{random_digits}"

# Отправка уведомлений в Telegram
def send_telegram_notification(message):
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": telegram_chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"Telegram уведомление отправлено: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при отправке Telegram уведомления: {e}")

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        email = data['email']
        phone = data['phone']

        # Проверка на существующего пользователя
        for code, client_data in clients.items():
            if client_data['email'] == email or client_data['phone'] == phone:
                name = client_data['name']
                send_telegram_notification(f"Пользователь {name} повторно вошел. Код: {code}.")
                return jsonify({
                    'uniqueCode': code,
                    'message': f'Добро пожаловать обратно, {name}! Ваш код: {code}.',
                    'telegramSuggestion': 'Вы можете продолжить общение в Telegram: @ВашБот'
                }), 200

        # Регистрация нового клиента
        unique_code = generate_unique_code()
        clients[unique_code] = {
            'name': data['name'],
            'phone': phone,
            'email': email
        }

        # Отправка уведомления в Telegram
        send_telegram_notification(
            f"Новый пользователь зарегистрирован:\nИмя: {data['name']}\nEmail: {email}\nТелефон: {phone}\nКод: {unique_code}"
        )

        return jsonify({
            'uniqueCode': unique_code,
            'message': f'Добро пожаловать, {data["name"]}! Ваш код: {unique_code}.',
            'telegramSuggestion': 'Вы можете продолжить общение в Telegram: @ВашБот'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
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
    # Получаем порт из переменной окружения (Cloud Run передаёт порт через $PORT)
    port = int(os.environ.get('PORT', 8080))  # 8080 — стандартный порт по умолчанию
    app.run(host='0.0.0.0', port=port)
