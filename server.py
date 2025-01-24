from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import random
import string

# Создание приложения Flask
app = Flask(__name__)

# Включение CORS
CORS(app)

# Установка API-ключа OpenAI (используйте переменные окружения для безопасности)
import os
openai.api_key = os.getenv("OPENAI_API_KEY")

# Существующие клиенты
clients = {}

# Функция генерации уникального кода клиента
def generate_unique_code():
    random_digits = ''.join(random.choices(string.digits, k=7))
    return f"CAEC{random_digits}"

# Регистрация клиента
@app.route('/register-client', methods=['POST'])
def register_client():
    data = request.json
    unique_code = generate_unique_code()
    clients[unique_code] = {
        'name': data['name'],
        'phone': data['phone'],
        'email': data['email']
    }
    return jsonify({'uniqueCode': unique_code})

# Проверка кода клиента
@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data['code']
    if code in clients:
        return jsonify({'valid': True, 'client': clients[code]})
    return jsonify({'valid': False})

# Обработчик маршрута для чата
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')

        if not user_message:
            return jsonify({'error': 'Message cannot be empty.'}), 400

        # Запрос к OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Убедитесь, что используемая модель поддерживается
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_message},
            ]
        )

        ai_message = response['choices'][0]['message']['content']
        return jsonify({'response': ai_message})

    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({'error': 'Internal server error.'}), 500

# Запуск приложения
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
