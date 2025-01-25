from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import string
import os
import openai
import smtplib
from email.mime.text import MIMEText

openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app)

clients = {}

def generate_unique_code():
    """Генерация уникального кода клиента."""
    return f"CAEC{''.join(random.choices(string.digits, k=7))}"

def send_email(recipient_email, unique_code, is_admin=False):
    """Отправка email через SMTP."""
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        subject = "Новая регистрация пользователя" if is_admin else "Ваш код регистрации"
        body = (f"Новый зарегистрированный пользователь. Код: {unique_code}."
                if is_admin else
                f"Добро пожаловать! Ваш код регистрации: {unique_code}. Пожалуйста, сохраните его.")

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = recipient_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipient_email, msg.as_string())

    except Exception as e:
        print(f"Ошибка при отправке email: {e}")

@app.route('/register-client', methods=['POST'])
def register_client():
    """Регистрация клиента."""
    try:
        data = request.json
        email = data['email']
        phone = data['phone']

        # Проверяем существующего клиента
        for code, client_data in clients.items():
            if client_data['email'] == email or client_data['phone'] == phone:
                return jsonify({'uniqueCode': code, 'message': f'Добро пожаловать обратно, {client_data["name"]}! Ваш код: {code}.'}), 200

        unique_code = generate_unique_code()
        clients[unique_code] = {
            'name': data['name'],
            'phone': phone,
            'email': email
        }

        # Отправка писем
        send_email(email, unique_code)
        send_email("office@caec.bz", unique_code, is_admin=True)

        return jsonify({'uniqueCode': unique_code, 'message': f'Добро пожаловать, {data["name"]}! Ваш код: {unique_code}.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Проверка кода клиента."""
    try:
        data = request.json
        code = data['code']
        if code in clients:
            return jsonify({'status': 'success', 'clientData': clients[code], 'message': f'Добро пожаловать обратно, {clients[code]["name"]}!'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    """Обработка общения с AI."""
    try:
        data = request.json
        user_message = data.get('message', '')

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
