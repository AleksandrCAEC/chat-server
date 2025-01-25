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
        email = data.get('email')
        phone = data.get('phone')

        # Проверка, существует ли уже клиент с такими данными
        for code, client in clients.items():
            if client['email'] == email or client['phone'] == phone:
                return jsonify({
                    'uniqueCode': code,
                    'message': f"Добро пожаловать обратно, {client['name']}! Ваш код: {code}."
                }), 200

        # Генерация нового кода
        unique_code = generate_unique_code()
        clients[unique_code] = {
            'name': data['name'],
            'phone': phone,
            'email': email
        }

        # Отправка приветственного сообщения
        return jsonify({
            'uniqueCode': unique_code,
            'message': f"Регистрация успешна! Ваш код: {unique_code}. Пожалуйста, сохраните его."
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    """Маршрут для проверки уникального кода клиента."""
    try:
        data = request.json
        code = data.get('code')
        if code in clients:
            return jsonify({
                'status': 'success',
                'clientData': clients[code],
                'message': f"Добро пожаловать, {clients[code]['name']}!"
            }), 200
        else:
            return jsonify({'status': 'error', 'message': 'Неверный код.'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    """Маршрут для общения с OpenAI."""
    try:
        data = request.json
        user_message = data.get('message', '')

        if not user_message.strip():
            return jsonify({'error': 'Сообщение не может быть пустым.'}), 400

        # Вызов OpenAI API с новой моделью
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Вы AI-ассистент, готовый помочь."},
                {"role": "user", "content": user_message}
            ]
        )

        reply = response['choices'][0]['message']['content'].strip()
        return jsonify({'reply': reply}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
