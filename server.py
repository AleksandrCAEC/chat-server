from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import json

# Создание приложения Flask
app = Flask(__name__)
CORS(app)  # Разрешение запросов с других доменов

# Установка API-ключа OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Путь для хранения знаний ассистента
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

# Базовые знания ассистента
knowledge = load_knowledge()

# Регистрация клиента (пример функционала)
@app.route('/register-client', methods=['POST'])
def register_client():
    data = request.json
    unique_code = f"CAEC{''.join(random.choices(string.digits, k=7))}"
    return jsonify({"uniqueCode": unique_code})

# Чат с ассистентом
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')

        if not user_message:
            return jsonify({'error': 'Message cannot be empty.'}), 400

        # Проверка известных вопросов
        for question, answer in knowledge.items():
            if user_message.lower() in question.lower():
                return jsonify({'response': answer})

        # Запрос к OpenAI с системным сообщением
        system_message = {
            "role": "system",
            "content": (
                "Ты — AI-ассистент. Вот несколько стандартных вопросов и ответов:\n"
                + "\n".join([f"{q} Ответ: {a}" for q, a in knowledge.items()]) +
                "\nЕсли вопрос неизвестен, отвечай: 'Извините, я пока не могу ответить на этот вопрос.'"
            )
        }

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                system_message,
                {"role": "user", "content": user_message},
            ]
        )

        ai_message = response['choices'][0]['message']['content']
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
        print(f"Ошибка: {e}")
        return jsonify({'error': 'Internal server error.'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
