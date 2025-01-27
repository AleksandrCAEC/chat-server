from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import string
import os
import openai
import requests
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# Настройка API-ключа OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Инициализация приложения Flask
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

    if not telegram_bot_token or not telegram_chat_id:
        print("Переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID не настроены.")
        return

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

# Настройка Google API
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'service_account.json'

credentials = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        name = data.get('name', 'Неизвестный пользователь')
        email = data.get('email', '')
        phone = data.get('phone', '')

        if not email or not phone:
            return jsonify({'error': 'Email и телефон обязательны.'}), 400

        # Проверка на существующего пользователя
        for code, client_data in clients.items():
            if client_data['email'] == email or client_data['phone'] == phone:
                send_telegram_notification(f"Пользователь {name} повторно вошел. Код: {code}.")
                return jsonify({
                    'uniqueCode': code,
                    'message': f'Добро пожаловать обратно, {name}! Ваш код: {code}.',
                    'telegramSuggestion': 'Вы можете продолжить общение в Telegram: @ВашБот'
                }), 200

        # Регистрация нового клиента
        unique_code = generate_unique_code()
        clients[unique_code] = {
            'name': name,
            'phone': phone,
            'email': email
        }

        # Отправка уведомления в Telegram
        send_telegram_notification(
            f"Новый пользователь зарегистрирован:\nИмя: {name}\nEmail: {email}\nТелефон: {phone}\nКод: {unique_code}"
        )

        return jsonify({
            'uniqueCode': unique_code,
            'message': f'Добро пожаловать, {name}! Ваш код: {unique_code}.',
            'telegramSuggestion': 'Вы можете продолжить общение в Telegram: @ВашБот'
        }), 200
    except Exception as e:
        print(f"Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data.get('code', '')
        if code in clients:
            name = clients[code]['name']
            return jsonify({'status': 'success', 'clientData': clients[code], 'message': f'Добро пожаловать обратно, {name}!'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        print(f"Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')

        if not user_message:
            return jsonify({'error': 'Сообщение не может быть пустым'}), 400

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
        print(f"Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/create-sheet', methods=['POST'])
def create_sheet():
    try:
        data = request.json
        client_code = data.get("client_code", "UnknownClient")

        # Настройка метаданных для нового файла
        file_metadata = {
            'name': f'Client_{client_code}',
            'mimeType': 'application/vnd.google-apps.spreadsheet',
            'parents': ['1g1OtN7ID1lM01d0bLswGqLF0m2gQIcqo']  # ID папки
        }
        # Создание таблицы
        file = drive_service.files().create(body=file_metadata, fields='id').execute()
        spreadsheet_id = file.get('id')

        # Возвращение ссылки на созданную таблицу
        return jsonify({
            'message': 'Google Sheet успешно создан!',
            'spreadsheet_id': spreadsheet_id,
            'spreadsheet_url': f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}'
        }), 200
    except Exception as e:
        print(f"Ошибка в /create-sheet: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Порт из переменной окружения
    app.run(host='0.0.0.0', port=port)
