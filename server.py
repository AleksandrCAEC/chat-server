from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import json
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Настройки приложения Flask
app = Flask(__name__)
CORS(app)

# Настройки OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Файл для хранения данных клиентов
CLIENTS_FILE = "clients.json"

# Функции для работы с клиентской базой
def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE, "r") as file:
            return json.load(file)
    return {}

def save_clients(clients):
    with open(CLIENTS_FILE, "w") as file:
        json.dump(clients, file, indent=4)

clients = load_clients()

# Генерация уникального кода
def generate_unique_code():
    return f"CAEC{''.join(random.choices(string.digits, k=7))}"

# Отправка email
def send_email(to_email, subject, body):
    try:
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
    except Exception as e:
        print(f"Ошибка отправки email: {e}")

# Маршрут для регистрации клиента
@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()

        if not name or not phone or not email:
            return jsonify({'error': 'Все поля обязательны для заполнения.'}), 400

        # Проверяем, существует ли клиент с таким email или телефоном
        for client_code, client_data in clients.items():
            if client_data["email"] == email or client_data["phone"] == phone:
                existing_code = client_code
                return jsonify({
                    'message': 'Вы уже зарегистрированы. Ваш код:',
                    'uniqueCode': existing_code
                })

        # Генерация нового кода и сохранение
        unique_code = generate_unique_code()
        clients[unique_code] = {'name': name, 'phone': phone, 'email': email}
        save_clients(clients)

        # Отправка email
        email_body = f"Здравствуйте, {name}!\n\nВаш уникальный код регистрации: {unique_code}\nПожалуйста, сохраните его для использования в будущем."
        send_email(email, "Код регистрации", email_body)

        return jsonify({
            'message': 'Регистрация успешна. Ваш уникальный код отправлен на email.',
            'uniqueCode': unique_code
        })
    except Exception as e:
        print(f"Ошибка регистрации клиента: {e}")
        return jsonify({'error': 'Ошибка на сервере.'}), 500

# Маршрут для проверки кода клиента
@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code', '').strip()

    if code in clients:
        return jsonify({'valid': True, 'client': clients[code]})
    return jsonify({'valid': False})

# Маршрут для чата с AI
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')

        if not user_message:
            return jsonify({'error': 'Сообщение не может быть пустым.'}), 400

        # Запрос к OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты — AI-ассистент. Отвечай на вопросы профессионально и вежливо."},
                {"role": "user", "content": user_message},
            ]
        )

        ai_message = response['choices'][0]['message']['content']
        return jsonify({'response': ai_message})
    except Exception as e:
        print(f"Ошибка чата: {e}")
        return jsonify({'error': 'Ошибка на сервере.'}), 500

# Запуск приложения
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
