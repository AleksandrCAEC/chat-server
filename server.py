from flask import Flask, request, jsonify
import random
import string
import openai  # Библиотека OpenAI

app = Flask(__name__)

# Настройте API-ключ OpenAI
openai.api_key = "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"

# Существующие маршруты
clients = {}

def generate_unique_code():
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
        return jsonify(clients[code])
    else:
        return jsonify({"error": "Invalid code"}), 404

# Новый маршрут для чата с AI
@app.route('/chat', methods=['POST'])
def chat_with_ai():
    data = request.json
    user_message = data.get("message")

    if not user_message:
        return jsonify({"error": "Message is required"}), 400

    try:
        # Запрос к OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Вы — помощник, который помогает клиентам."},
                {"role": "user", "content": user_message}
            ]
        )
        ai_response = response['choices'][0]['message']['content']
        return jsonify({"response": ai_response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Запуск приложения
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
