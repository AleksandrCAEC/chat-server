from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import string
import os
import openai
import requests

# Настройка API-ключа OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Инициализация Flask
app = Flask(__name__)
CORS(app)

# Хранилище пользователей
clients = {}

def generate_unique_code():
    """Генерация уникального кода для клиента."""
    random_digits = ''.join(random.choices(string.digits, k=7))
    return f"CAEC{random_digits}"

def send_message_to_telegram(chat_id, message):
    """Отправка сообщения пользователю через Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Ошибка отправки в Telegram: {response.text}")
    except Exception as e:
        print(f"Ошибка при отправке сообщения в Telegram: {e}")

@app.route('/register-client', methods=['POST'])
def register_client():
    """Регистрация клиента через веб-форму."""
    try:
        data = request.json
        email = data['email']
        phone = data['phone']

        # Проверка, существует ли пользователь
        for code, client_data in clients.items():
            if client_data['email'] == email or client_data['phone'] == phone:
                return jsonify({
                    'uniqueCode': code,
                    'message': f'Добро пожаловать обратно, {client_data["name"]}! Ваш код: {code}.\nДля общения с ассистентом перейдите: https://t.me/<ваш_бот_username>'
                }), 200

        unique_code = generate_unique_code()
        clients[unique_code] = {
            'name': data['name'],
            'phone': phone,
            'email': email
        }

        # Отправка инструкции в Telegram
        send_message_to_telegram(
            chat_id="8074527842",
            message=(
                f"📢 Новый зарегистрированный пользователь:\n"
                f"Имя: {data['name']}\nТелефон: {phone}\nEmail: {email}\nКод: {unique_code}\n"
                f"Попросите пользователя перейти к вашему боту: https://t.me/<ваш_бот_username>"
            )
        )

        return jsonify({
            'uniqueCode': unique_code,
            'message': f'Добро пожаловать, {data["name"]}! Ваш код: {unique_code}.\nДля общения с ассистентом перейдите: https://t.me/<ваш_бот_username>'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Обработка сообщений, поступающих от Telegram."""
    try:
        data = request.json
        message = data.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text')

        if not chat_id or not text:
            return jsonify({'status': 'ignored'}), 200

        # Если пользователь новый, запросить код
        if chat_id not in clients:
            send_message_to_telegram(chat_id, "Добро пожаловать! Пожалуйста, отправьте ваш уникальный код для идентификации.")
            return jsonify({'status': 'ok'}), 200

        # Получение уникального кода
        if text.startswith("CAEC"):
            if text in clients:
                send_message_to_telegram(chat_id, f"Спасибо! Мы вас узнали: {clients[text]['name']}. Чем могу помочь?")
            else:
                send_message_to_telegram(chat_id, "Извините, код не найден. Пожалуйста, проверьте его и попробуйте снова.")
            return jsonify({'status': 'ok'}), 200

        # Общение через OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "assistant", "content": "Здравствуйте! Чем могу помочь?"},
                {"role": "user", "content": text}
            ],
            max_tokens=150
        )
        reply = response['choices'][0]['message']['content'].strip()
        send_message_to_telegram(chat_id, reply)
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Ошибка обработки вебхука: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
