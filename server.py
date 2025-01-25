from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import string
import openai
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Настройка приложения Flask
app = Flask(__name__)
CORS(app)

# Настройка OpenAI API
openai.api_key = "Ваш-ключ-OpenAI"

# База данных клиентов
clients = {}

# Генерация уникального кода
def generate_unique_code():
    random_digits = ''.join(random.choices(string.digits, k=8))
    return f"CAEC{random_digits}"

# Функция отправки e-mail
def send_email(to_email, unique_code):
    try:
        # Настройка SMTP-сервера
        smtp_server = "smtp.gmail.com"  # Замените на ваш SMTP-сервер
        smtp_port = 587
        sender_email = "ваш_email@gmail.com"  # Ваш e-mail
        sender_password = "ваш_пароль"  # Пароль вашего e-mail

        # Создание сообщения
        subject = "Ваш код регистрации"
        body = f"Спасибо за регистрацию на нашем сайте!\nВаш код регистрации: {unique_code}\nПожалуйста, сохраните этот код для дальнейшего общения."

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # Отправка e-mail
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
        print(f"Email отправлен на {to_email}")
    except Exception as e:
        print(f"Ошибка отправки e-mail: {e}")

# Маршрут для регистрации клиента
@app.route('/register-client', methods=['POST'])
def register_client():
    data = request.json
    name = data.get("name")
    phone = data.get("phone")
    email = data.get("email")

    if not name or not phone or not email:
        return jsonify({"error": "Все поля обязательны для заполнения."}), 400

    # Проверка, есть ли клиент с таким e-mail или телефоном
    for code, client in clients.items():
        if client["email"] == email or client["phone"] == phone:
            return jsonify({"uniqueCode": code, "message": "Вы уже зарегистрированы. Ваш код отправлен на e-mail."})

    # Генерация нового кода и сохранение клиента
    unique_code = generate_unique_code()
    clients[unique_code] = {"name": name, "phone": phone, "email": email}

    # Отправка e-mail с кодом
    send_email(email, unique_code)

    return jsonify({"uniqueCode": unique_code, "message": "Регистрация успешна! Код отправлен на ваш e-mail."})

# Маршрут для проверки кода
@app.route('/check-code/<code>', methods=['GET'])
def check_code(code):
    if code in clients:
        return jsonify({"valid": True, "client": clients[code]})
    return jsonify({"valid": False})

# Маршрут для общения с AI
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get("message")

    if not message:
        return jsonify({"error": "Сообщение не может быть пустым."}), 400

    try:
        # Отправка сообщения в OpenAI API
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты — виртуальный помощник."},
                {"role": "user", "content": message},
            ]
        )
        reply = response["choices"][0]["message"]["content"]
        return jsonify({"response": reply})
    except Exception as e:
        return jsonify({"error": "Ошибка соединения с OpenAI API."}), 500

# Запуск сервера
if __name__ == '__main__':
    app.run(debug=True)
