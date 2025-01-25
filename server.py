from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import json
import random
import string
import requests

# Настройки приложения Flask
app = Flask(__name__)
CORS(app)

# Настройки OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Telegram настройки
TELEGRAM_BOT_TOKEN = "ВАШ_ТЕЛЕГРАМ_ТОКЕН"
TELEGRAM_CHAT_ID = "ВАШ_CHAT_ID"

# Глобальная переменная для управления активностью ассистента
assistant_active = True

# Путь к файлу знаний
KNOWLEDGE_FILE = "knowledge.json"

# Загрузка знаний из файла
def load_knowledge():
    if os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, "r") as file:
            return json.load(file)
    return {}

# Сохранение знаний в файл
def save_knowledge(knowledge):
    with open(KNOWLEDGE_FILE, "w") as file:
        json.dump(knowledge, file, indent=4)

# Загрузка существующих знаний
knowledge = load_knowledge()

# Отправка уведомлений в Telegram
def notify_in_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

# Маршрут для регистрации клиента
@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()

        if not name or not phone or not email:
            return jsonify({'error': 'All fields are required.'}), 400

        unique_code = f"CAEC{''.join(random.choices(string.digits, k=7))}"

        # Отправка уведомления в Telegram
        notify_in_telegram(f"Новый клиент зарегистрирован:\nИмя: {name}\nТелефон: {phone}\nEmail: {email}\nКод: {unique_code}")

        return jsonify({'uniqueCode': unique_code})
    except Exception as e:
        print(f"Ошибка регистрации: {e}")
        return jsonify({'error': 'Internal server error.'}), 500

# Маршрут для проверки кода клиента
@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code', '').strip()

    # Здесь можно проверить код в базе данных или другом хранилище
    if code.startswith("CAEC"):
        return jsonify({'valid': True, 'client': {'code': code}})
    return jsonify({'valid': False})

# Чат с ассистентом
@app.route('/chat', methods=['POST'])
def chat():
    global assistant_active
    try:
        data = request.json
        user_message = data.get('message', '')

        if not user_message:
            return jsonify({'error': 'Message cannot be empty.'}), 400

        # Если ассистент отключён
        if not assistant_active:
            notify_in_telegram(f"Вопрос клиента: {user_message}")
            return jsonify({'response': 'Ваш вопрос передан специалисту. Ожидайте ответа.'})

        # Проверка известных вопросов
        for question, answer in knowledge.items():
            if user_message.lower() in question.lower():
                notify_in_telegram(f"Клиент: {user_message}\nAI: {answer}")
                return jsonify({'response': answer})

        # Запрос к OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты — AI-ассистент. Отвечай на вопросы профессионально и вежливо."},
                {"role": "user", "content": user_message},
            ]
        )

        ai_message = response['choices'][0]['message']['content']

        # Отправка переписки в Telegram
        notify_in_telegram(f"Клиент: {user_message}\nAI: {ai_message}")

        return jsonify({'response': ai_message})
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({'error': 'Internal server error.'}), 500

# Добавление нового знания
@app.route('/add-knowledge', methods=['POST'])
def add_knowledge():
    try:
        data = request.json
        question = data.get('question', '').strip()
        answer = data.get('answer', '').strip()

        if not question or not answer:
            return jsonify({'error': 'Question and answer cannot be empty.'}), 400

        # Обновление знаний
        knowledge[question] = answer
        save_knowledge(knowledge)

        return jsonify({'message': 'Knowledge added successfully.'})
    except Exception as e:
        print(f"Ошибка добавления знаний: {e}")
        return jsonify({'error': 'Internal server error.'}), 500

# Управление ассистентом через команды
@app.route('/toggle-assistant', methods=['POST'])
def toggle_assistant():
    global assistant_active
    try:
        data = request.json
        command = data.get('command', '').strip()

        if command == "@Team":
            assistant_active = False
            notify_in_telegram("Ассистент отключён. Ответы только вручную.")
        elif command == "@Resume":
            assistant_active = True
            notify_in_telegram("Ассистент снова активен.")
        else:
            return jsonify({'error': 'Unknown command.'}), 400

        return jsonify({'status': 'success', 'assistant_active': assistant_active})
    except Exception as e:
        print(f"Ошибка управления ассистентом: {e}")
        return jsonify({'error': 'Internal server error.'}), 500

# Запуск приложения
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
