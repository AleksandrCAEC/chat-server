from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import string
import os
import openai
import smtplib
from email.mime.text import MIMEText

# Настройка API-ключа из переменной окружения
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app)

# Словарь для хранения данных клиентов
clients = {}

def generate_unique_code():
    """Генерация уникального кода для клиента."""
    random_digits = ''.join(random.choices(string.digits, k=7))
    return f"CAEC{random_digits}"

def send_email(email, unique_code):
    """Отправка email с кодом регистрации."""
    try:
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        msg = MIMEText(f"Ваш код регистрации: {unique_code}. Пожалуйста, сохраните его для дальнейшего использования.")
        msg['Subject'] = "Код регистрации"
        msg['From'] = smtp_user
        msg['To'] = email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, email, msg.as_string())
    except Exception as e:
        print(f"Ошибка при отправке email: {e}")

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
                return jsonify({'uniqueCode': code, 'message': 'Код уже существует. Пожалуйста, используйте его.'}), 200

        unique_code = generate_unique_code()
        clients[unique_code] = {
            'name': data['name'],
            'phone': phone,
            'email': email
        }

        send_email(email, unique_code)
        return jsonify({'uniqueCode': unique_code}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Маршрут для проверки уникального кода клиента."""
    try:
        data = request.json
        code = data['code']
        if code in clients:
            return jsonify({'status': 'success', 'clientData': clients[code]}), 200
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

        # Вызов OpenAI API
        response = openai.Completion.create(
            engine="gpt-3.5-turbo",
            prompt=user_message,
            max_tokens=150
        )

        reply = response.choices[0].text.strip()
        return jsonify({'reply': reply}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
