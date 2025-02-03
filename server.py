from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import openai
import requests
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import pandas as pd

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

# Загрузка данных из Bible.xlsx
def load_bible_data():
    bible_path = "./CAEC_API_Data/BIG_DATA/Bible.xlsx"
    if not os.path.exists(bible_path):
        logger.error("Файл Bible.xlsx не найден.")
        return None
    try:
        data = pd.read_excel(bible_path)
        logger.info(f"Файл Bible.xlsx успешно загружен. Данные: {data.to_dict()}")
        return data
    except Exception as e:
        logger.error(f"Ошибка при чтении Bible.xlsx: {e}")
        return None

# Загрузка данных клиента
def load_client_data(client_code):
    client_path = f"./CAEC_API_Data/Data_CAEC_Client/Client_{client_code}.xlsx"
    if not os.path.exists(client_path):
        logger.info(f"Файл клиента {client_code} не найден. Клиент новый.")
        return None
    try:
        data = pd.read_excel(client_path)
        logger.info(f"Файл клиента {client_code} успешно загружен. Данные: {data.to_dict()}")
        return data
    except Exception as e:
        logger.error(f"Ошибка при чтении файла клиента {client_code}: {e}")
        return None

# Подготовка контекста для ассистента
def prepare_assistant_context(client_code):
    # Загружаем данные из Bible.xlsx
    bible_data = load_bible_data()
    if bible_data is None:
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
            {"role": "system", "content": "Вы - помощник компании CAEC."},
            {"role": "user", "content": user_message}
        ]

        # Если есть история переписки, добавляем её в контекст
        if context["client_history"] is not None:
            for _, row in context["client_history"].iterrows():
                messages.append({"role": "assistant" if row["is_assistant"] else "user", "content": row["message"]})

        # Добавляем данные из Bible.xlsx в контекст
        if context["bible"] is not None:
            bible_context = "Данные из Bible.xlsx:\n"
            for _, row in context["bible"].iterrows():
                bible_context += f"Вопрос: {row['Question']}\nОтвет: {row['Answer']}\n"
            messages.append({"role": "system", "content": bible_context})

        logger.info(f"Запрос к OpenAI с контекстом: {messages}")

        # Запрос к OpenAI
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=500  # Увеличено для более длинных ответов
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

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        logger.info(f"Получен запрос на верификацию кода: {data}")

        client_code = data.get('client_code', '')
        if not client_code:
            logger.error("Ошибка: Код клиента не может быть пустым")
            return jsonify({'error': 'Код клиента не может быть пустым'}), 400

        # Верифицируем код клиента
        client_info = verify_client_code(client_code)
        if client_info is None:
            logger.info(f"Клиент с кодом {client_code} не найден.")
            return jsonify({'error': 'Клиент не найден'}), 404

        logger.info(f"Клиент с кодом {client_code} успешно верифицирован.")
        return jsonify(client_info), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        logger.info(f"Получен запрос на регистрацию клиента: {data}")

        name = data.get('name', '')
        phone = data.get('phone', '')
        email = data.get('email', '')

        if not name or not phone or not email:
            logger.error("Ошибка: Имя, телефон и email не могут быть пустыми")
            return jsonify({'error': 'Имя, телефон и email не могут быть пустыми'}), 400

        # Генерация уникального кода
        unique_code = generate_unique_code()

        # Сохраняем данные клиента
        client_data = {
            "Client Code": unique_code,
            "Name": name,
            "Phone": phone,
            "Email": email,
            "Created Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Last Visit": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Activity Status": "Active"
        }

        # Сохраняем данные в файл
        client_path = f"./CAEC_API_Data/Data_CAEC_Client/Client_{unique_code}.xlsx"
        df = pd.DataFrame([client_data])
        df.to_excel(client_path, index=False)

        logger.info(f"Клиент {name} успешно зарегистрирован. Код: {unique_code}")
        return jsonify({'uniqueCode': unique_code}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/send-telegram', methods=['POST'])
def send_telegram():
    try:
        data = request.json
        logger.info(f"Получен запрос на отправку Telegram уведомления: {data}")

        message = data.get('message', '')
        if not message:
            logger.error("Ошибка: Сообщение не может быть пустым")
            return jsonify({'error': 'Сообщение не может быть пустым'}), 400

        send_telegram_notification(message)
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /send-telegram: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def home():
    return jsonify({"status": "Server is running!"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"✅ Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
