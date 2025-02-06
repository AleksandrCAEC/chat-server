# server.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import openai
import requests
import logging
from datetime import datetime
from clientdata import register_or_update_client, verify_client_code
from client_caec import add_message_to_client_file  # Функция для работы с историей переписки
from bible import load_bible_data  # Новый модуль для работы с Bible.xlsx

# Установка пути к файлу service_account_json
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"

# Инициализация OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Инициализация приложения Flask
app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def send_telegram_notification(message):
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not telegram_bot_token or not telegram_chat_id:
        logger.error("Переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID не настроены.")
        return
    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"✅ Telegram уведомление отправлено: {response.json()}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ошибка при отправке Telegram уведомления: {e}")

def prepare_chat_context(client_code):
    """
    Формирует список сообщений для запроса к OpenAI:
    1. Загружает данные из Bible.xlsx и создает системное сообщение с информацией о компании.
    2. Если существует файл истории переписки клиента, считывает его и добавляет предыдущие сообщения.
    """
    messages = []

    # Чтение Bible.xlsx через Google Sheets API
    bible_df = load_bible_data()
    if bible_df is None:
        raise Exception("Bible.xlsx не найден или недоступен.")

    bible_context = "Информация о компании (FAQ):\n"
    # Проходим по всем записям и объединяем FAQ и ответы
    for index, row in bible_df.iterrows():
        faq = row.get("FAQ", "")
        answer = row.get("Answers", "")
        if faq and answer:
            bible_context += f"Вопрос: {faq}\nОтвет: {answer}\n\n"

    system_message = {
        "role": "system",
        "content": f"Вы – умный ассистент компании CAEC. Используйте следующую информацию для ответов:\n{bible_context}"
    }
    messages.append(system_message)

    # Попытка загрузить историю переписки клиента из файла
    import openpyxl
    from client_caec import CLIENT_FILES_DIR
    client_file_path = os.path.join(CLIENT_FILES_DIR, f"Client_{client_code}.xlsx")
    if os.path.exists(client_file_path):
        try:
            wb = openpyxl.load_workbook(client_file_path, data_only=True)
            ws = wb.active
            # Пропускаем первую строку (заголовки)
            for row in ws.iter_rows(min_row=2, values_only=True):
                client_msg = row[0]  # Сообщения клиента (столбец A)
                assistant_msg = row[1]  # Сообщения ассистента (столбец B)
                if client_msg and isinstance(client_msg, str):
                    messages.append({"role": "user", "content": client_msg})
                if assistant_msg and isinstance(assistant_msg, str):
                    messages.append({"role": "assistant", "content": assistant_msg})
        except Exception as e:
            logger.error(f"Ошибка при чтении файла клиента {client_file_path}: {e}")

    return messages

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

        try:
            messages = prepare_chat_context(client_code)
        except Exception as e:
            error_msg = f"Ошибка подготовки контекста: {e}"
            logger.error(error_msg)
            send_telegram_notification(f"Ошибка базы данных: {error_msg}")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

        messages.append({"role": "user", "content": user_message})

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=150
        )

        reply = response['choices'][0]['message']['content'].strip()

        # Логирование переписки в файле клиента
        add_message_to_client_file(client_code, user_message, is_assistant=False)
        add_message_to_client_file(client_code, reply, is_assistant=True)

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
