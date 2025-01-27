from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import string
import os
import openai
import requests
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager

# Функция для получения секрета из Google Secret Manager
def get_secret(secret_name):
    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        print(f"Ошибка при доступе к секрету {secret_name}: {e}")
        return None

# Получение service_account.json из Secret Manager
service_account_content = get_secret("service_account")
if service_account_content:
    # Сохраняем временный файл для использования учетных данных
    with open("/tmp/service_account.json", "w") as f:
        f.write(service_account_content)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/tmp/service_account.json"
else:
    print("Не удалось получить service_account.json. Проверьте настройки Secret Manager.")

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

# Новый маршрут для создания таблицы Google Sheets
@app.route('/create-spreadsheet', methods=['POST'])
def create_spreadsheet():
    try:
        data = request.json
        title = data.get('title', 'Новая таблица')

        credentials = Credentials.from_service_account_file('/etc/secrets/service_account')
        service = build('sheets', 'v4', credentials=credentials)

        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        spreadsheet = service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId').execute()
        spreadsheet_id = spreadsheet.get('spreadsheetId')

        return jsonify({'status': 'success', 'spreadsheetId': spreadsheet_id, 'message': f'Таблица "{title}" успешно создана.'}), 200
    except Exception as e:
        print(f"Ошибка в /create-spreadsheet: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/check-env', methods=['GET'])
def check_env():
    try:
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path:
            return jsonify({"GOOGLE_APPLICATION_CREDENTIALS": credentials_path}), 200
        else:
            return jsonify({"error": "Переменная GOOGLE_APPLICATION_CREDENTIALS не установлена"}), 500
    except Exception as e:
        print(f"Ошибка в /check-env: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Порт из переменной окружения
    app.run(host='0.0.0.0', port=port)
