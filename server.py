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

def send_email(recipient, subject, body):
    """Функция для отправки email."""
    try:
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = recipient

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipient, msg.as_string())
    except Exception as e:
        print(f"Ошибка при отправке email на {recipient}: {e}")

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

        # Если клиента нет, генерируем новый код
        unique_code = generate_unique_code()
        clients[unique_code] = {
            'name': data['name'],
            'phone': phone,
            'email': email
        }

        # Отправка письма пользователю
        user_subject = "Добро пожаловать в CAEC"
        user_body = f"Здравствуйте, {data['name']}!\n\nВаш код регистрации: {unique_code}.\nПожалуйста, сохраните его для дальнейшего использования.\n\nС уважением, команда CAEC."
        send_email(email, user_subject, user_body)

        # Отправка письма администратору
        admin_subject = "Новый зарегистрированный пользователь"
        admin_body = f"Новый пользователь зарегистрирован:\n\nИмя: {data['name']}\nТелефон: {phone}\nEmail: {email}\nКод регистрации: {unique_code}"
        send_email("office@caec.bz", admin_subject, admin_body)

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
