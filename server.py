from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import string
import os
import openai
import requests
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# Указание пути к файлу service_account_json
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"

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
    payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
    
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
        name = data.get('name', 'Неизвестный пользователь')
        email = data.get('email', '')
        phone = data.get('phone', '')

        if not email or not phone:
            return jsonify({'error': 'Email и телефон обязательны.'}), 400

        for code, client_data in clients.items():
            if client_data['email'] == email or client_data['phone'] == phone:
                send_telegram_notification(f"Пользователь {name} повторно вошел. Код: {code}.")
                return jsonify({'uniqueCode': code, 'message': f'Добро пожаловать обратно, {name}! Ваш код: {code}.'}), 200

        unique_code = generate_unique_code()
        clients[unique_code] = {'name': name, 'phone': phone, 'email': email}

        send_telegram_notification(f"Новый пользователь зарегистрирован: {name}, {email}, {phone}, Код: {unique_code}")

        return jsonify({'uniqueCode': unique_code, 'message': f'Добро пожаловать, {name}! Ваш код: {unique_code}.'}), 200
    except Exception as e:
        print(f"Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data.get('code', '')
        if code in clients:
            return jsonify({'status': 'success', 'clientData': clients[code]}), 200
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

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "assistant", "content": "Здравствуйте! Чем могу помочь?"}, {"role": "user", "content": user_message}],
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
        title = data.get('title', 'Новая таблица')
        notes = data.get('notes', '')

        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        sheets_service = build('sheets', 'v4', credentials=credentials)
        drive_service = build('drive', 'v3', credentials=credentials)

        spreadsheet = sheets_service.spreadsheets().create(body={'properties': {'title': title}}, fields='spreadsheetId').execute()
        spreadsheet_id = spreadsheet.get('spreadsheetId')

        folder_id = '1g1OtN7ID1lM01d0bLswGqLF0m2gQIcqo'
        drive_service.files().update(fileId=spreadsheet_id, addParents=folder_id, removeParents='root', fields='id, parents').execute()

        if notes:
            requests_body = {'requests': [{'updateCells': {'range': {'sheetId': 0, 'startRowIndex': 0, 'startColumnIndex': 0}, 'rows': [{'values': [{'userEnteredValue': {'stringValue': notes}}]}], 'fields': 'userEnteredValue'}}]}
            sheets_service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=requests_body).execute()

        return jsonify({'status': 'success', 'spreadsheetId': spreadsheet_id, 'spreadsheetLink': f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}", 'message': f'Таблица "{title}" успешно создана.'}), 200
    except Exception as e:
        print(f"Ошибка в /create-sheet: {e}")
        return jsonify({'error': str(e)}), 500

# Добавляем логирование перед запуском сервера
@app.route('/')
def home():
    return jsonify({"status": "Server is running!"}), 200

import logging
logging.basicConfig(level=logging.INFO)
logging.info("Server is starting...")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Используем порт из окружения
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
