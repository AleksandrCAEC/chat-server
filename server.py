from flask import Flask, request, jsonify
import random
import string
import os
import openai

# Настройка API-ключа из переменной окружения
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

# Словарь для хранения данных клиентов
clients = {}

def generate_unique_code():
    """Генерация уникального кода для клиента."""
    random_digits = ''.join(random.choices(string.digits, k=7))
    return f"CAEC{random_digits}"

@app.route('/register-client', methods=['POST'])
def register_client():
    """Маршрут для регистрации клиента."""
    try:
        data = request.json
        unique_code = generate_unique_code()
        clients[unique_code] = {
            'name': data['name'],
            'phone': data['phone'],
            'email': data['email']
        }
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
            return jsonify({'status': 'error', 'message': 'Invalid code'}), 404
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
            engine="text-davinci-003",
            prompt=user_message,
            max_tokens=150
        )

        reply = response.choices[0].text.strip()
        return jsonify({'reply': reply}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
