from flask import Flask, request, jsonify
import openai
import os

app = Flask(__name__)

# Настройка API-ключа OpenAI из переменной окружения
openai.api_key = os.getenv("OPENAI_API_KEY")

# Существующие клиенты
clients = {}

# Функция для генерации уникального кода
def generate_unique_code():
    import random
    import string
    random_digits = ''.join(random.choices(string.digits, k=7))
    return f"CAEC{random_digits}"

@app.route('/register-client', methods=['POST'])
def register_client():
    data = request.json
    unique_code = generate_unique_code()
    clients[unique_code] = {
        "name": data['name'],
        "phone": data['phone'],
        "email": data['email']
    }
    return jsonify({"uniqueCode": unique_code})

@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data['code']
    if code in clients:
        return jsonify({"valid": True, "clientData": clients[code]})
    else:
        return jsonify({"valid": False})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')

    try:
        # Вызов модели OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Используем актуальную модель
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_message},
            ]
        )

        # Извлечение ответа модели
        assistant_reply = response['choices'][0]['message']['content']
        return jsonify({"response": assistant_reply})

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
