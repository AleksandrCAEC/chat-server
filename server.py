from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import openai
import requests
import pandas as pd
from clientdata import register_or_update_client, verify_client_code
from client_caec import add_message_to_client_file, load_client_data
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Настройка логирования
def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = RotatingFileHandler("server.log", maxBytes=1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

logger = setup_logging()

# Указание пути к файлу service_account_json
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"

# Инициализация клиента OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Инициализация приложения Flask
app = Flask(__name__)
CORS(app)

# Путь к файлу Bible.xlsx
BIBLE_PATH = "./CAEC_API_Data/BIG_DATA/Bible.xlsx"

# Загрузка данных из Bible.xlsx
def load_bible_data():
    try:
        if not os.path.exists(BIBLE_PATH):
            logger.error(f"Файл {BIBLE_PATH} не найден.")
            return None
        bible_data = pd.read_excel(BIBLE_PATH)
        logger.info(f"Данные из Bible.xlsx загружены: {bible_data.head()}")
        return bible_data
    except Exception as e:
        logger.error(f"Ошибка при чтении Bible.xlsx: {e}")
        return None

# Подготовка контекста для ассистента
def prepare_assistant_context(client_code):
    # Загружаем данные из Bible.xlsx
    bible_data = load_bible_data()
    if bible_data is None:
        logger.error("Файл Bible.xlsx не найден.")
        send_telegram_notification("❌ Ошибка базы данных: Файл Bible.xlsx не найден.")
        return None

    # Загружаем данные клиента
    client_data = load_client_data(client_code)
    if client_data is None:
        logger.info("Клиент новый. Ассистент будет общаться максимально информативно.")
        return {"bible": bible_data, "client_history": None}

    # Если клиент существует, загружаем историю переписки
    logger.info("Клиент существует. Ассистент загрузил историю переписки.")
    return {"bible": bible_data, "client_history": client_data}

# Отправка уведомлений в Telegram
def send_telegram_notification(message):
    try:
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not telegram_bot_token or not telegram_chat_id:
            raise ValueError("Переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID не настроены.")

        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"✅ Telegram уведомление отправлено: {response.json()}")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке Telegram уведомления: {e}")

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        logger.info(f"Получен запрос на регистрацию клиента: {data}")

        result = register_or_update_client(data)

        if result.get("isNewClient", True):
            send_telegram_notification(f"🆕 Новый пользователь зарегистрирован: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}")
        else:
            send_telegram_notification(f"🔙 Пользователь вернулся: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}")

        return jsonify(result), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        logger.info(f"Получен запрос на верификацию кода: {data}")

        code = data.get('code', '')
        client_data = verify_client_code(code)
        if client_data:
            send_telegram_notification(f"🔙 Пользователь вернулся: {client_data['Name']}, {client_data['Email']}, {client_data['Phone']}, Код: {code}")
            return jsonify({'status': 'success', 'clientData': client_data}), 200
        return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        logger.error(f"❌ Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        logger.info(f"Получен запрос на чат: {data}")

        user_message = data.get('message', '')
        client_code = data.get('client_code', '')

        if not user_message or not client_code:
            logger.error("Ошибка: Сообщение и код клиента не могут быть пустыми")
            return jsonify({'error': 'Сообщение и код клиента не могут быть пустыми'}), 400

        # Подготавливаем контекст для ассистента
        context = prepare_assistant_context(client_code)
        if context is None:
            return jsonify({'error': 'Ошибка базы данных. Обратитесь к менеджеру.'}), 500

        # Формируем сообщение для OpenAI с учетом контекста
        messages = [
            {"role": "system", "content": "Вы - помощник компании CAEC."}
        ]

        # Добавляем данные из Bible.xlsx в контекст
        if context["bible"] is not None:
            for _, row in context["bible"].iterrows():
                messages.append({
                    "role": "system",
                    "content": f"Вопрос: {row['FAQ']}\nОтвет: {row['Answers']}"
                })

        # Добавляем историю переписки, если она есть
        if context["client_history"] is not None:
            for _, row in context["client_history"].iterrows():
                messages.append({
                    "role": "assistant" if row["is_assistant"] else "user",
                    "content": row["message"]
                })

        # Добавляем текущее сообщение пользователя
        messages.append({"role": "user", "content": user_message})

        # Запрос к OpenAI
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=500  # Увеличиваем лимит токенов
            )
            reply = response['choices'][0]['message']['content'].strip()
        except openai.error.OpenAIError as e:
            logger.error(f"Ошибка OpenAI: {e}")
            return jsonify({'error': 'Ошибка при обработке запроса OpenAI'}), 500

        # Сохраняем сообщение в файл клиента
        try:
            add_message_to_client_file(client_code, user_message, is_assistant=False)
            add_message_to_client_file(client_code, reply, is_assistant=True)
        except Exception as e:
            logger.error(f"Ошибка при записи в файл: {e}")
            return jsonify({'error': 'Ошибка при сохранении сообщения'}), 500

        logger.info(f"Ответ от OpenAI: {reply}")
        return jsonify({'reply': reply}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def home():
    return jsonify({"status": "Server is running!"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"✅ Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
