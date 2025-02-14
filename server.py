import os
import re
import logging
import asyncio
import pprint
from flask import Flask, request, jsonify
import openai
import requests
from datetime import datetime
from clientdata import register_or_update_client, verify_client_code, update_last_visit, update_activity_status
from client_caec import add_message_to_client_file, find_client_file_id, get_sheets_service, CLIENT_FILES_DIR
from bible import load_bible_data, save_bible_pair
from price_handler import get_price_response, load_price_data  # get_price_response для получения данных из price_handler.py
from flask_cors import CORS
import openpyxl

# Импорты для Telegram Bot (python-telegram-bot v20+)
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Установка пути к файлу service_account_json
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"

# Инициализация OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Инициализация Flask-приложения и CORS
app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("server.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logger.info("Текущие переменные окружения:")
pprint.pprint(dict(os.environ))

# Глобальный словарь для хранения состояния последовательного уточнения (guiding questions)
pending_guiding = {}

###############################################
# ФУНКЦИЯ ОТПРАВКИ УВЕДОМЛЕНИЙ ЧЕРЕЗ TELEGRAM
###############################################
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

###############################################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ОБРАБОТКИ ЗАПРОСОВ О ЦЕНЕ
###############################################
PRICE_KEYWORDS = ["цена", "прайс", "сколько стоит", "во сколько обойдется", "стандартный тариф"]

def is_price_query(text):
    return any(keyword in text.lower() for keyword in PRICE_KEYWORDS)

def get_vehicle_type(text):
    known_types = {"truck": "Truck", "грузовик": "Truck", "fura": "Fura", "фура": "Fura"}
    for key, standard in known_types.items():
        if key in text.lower():
            return standard
    return None

def get_price_response_wrapper(vehicle_type, direction="Ro_Ge", client_guiding_answers=None):
    try:
        response = get_price_response(vehicle_type, direction, client_guiding_answers)
        return response
    except Exception as e:
        logger.error(f"Ошибка при получении цены для {vehicle_type}: {e}")
        return "Произошла ошибка при получении актуальной цены. Пожалуйста, попробуйте позже."

###############################################
# ФУНКЦИЯ ПОДГОТОВКИ КОНТЕКСТА (ПАМЯТЬ АССИСТЕНТА)
###############################################
def prepare_chat_context(client_code):
    messages = []
    bible_df = load_bible_data()
    if bible_df is None:
        raise Exception("Bible.xlsx не найден или недоступен.")
    logger.info(f"Bible.xlsx содержит {len(bible_df)} записей.")
    bible_context = "Информация о компании (FAQ):\n"
    # Удаляем временные метки из FAQ и Answers (например, "14.02.25 14:11 -")
    for index, row in bible_df.iterrows():
        faq = row.get("FAQ", "")
        answer = row.get("Answers", "")
        faq = re.sub(r"^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*", "", faq)
        answer = re.sub(r"^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*", "", answer)
        verification = str(row.get("Verification", "")).strip().upper()
        if faq and answer and verification != "CHECK":
            bible_context += f"Вопрос: {faq}\nОтвет: {answer}\n\n"
    system_message = {
        "role": "system",
        "content": f"Вы – умный ассистент компании CAEC. Используйте следующую информацию для ответов:\n{bible_context}"
    }
    messages.append(system_message)
    
    # Чтение истории переписки из уникального файла клиента (начиная со 3-й строки)
    spreadsheet_id = find_client_file_id(client_code)
    if spreadsheet_id:
        sheets_service = get_sheets_service()
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A:B"
        ).execute()
        values = result.get("values", [])
        if len(values) >= 2:
            conversation_rows = values[2:]
            logger.info(f"Найдено {len(conversation_rows)} строк переписки для клиента {client_code}.")
            for row in conversation_rows:
                if len(row) >= 1 and row[0].strip():
                    messages.append({"role": "user", "content": row[0].strip()})
                if len(row) >= 2 and row[1].strip():
                    messages.append({"role": "assistant", "content": row[1].strip()})
    else:
        logger.info(f"Файл клиента с кодом {client_code} не найден.")
    return messages

###############################################
# ЭНДПОИНТЫ РЕГИСТРАЦИИ, ВЕРИФИКАЦИИ И ЧАТА
###############################################
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
        user_message = data.get("message", "")
        client_code = data.get("client_code", "")
        if not user_message or not client_code:
            logger.error("Ошибка: Сообщение и код клиента не могут быть пустыми")
            return jsonify({'error': 'Сообщение и код клиента не могут быть пустыми'}), 400

        update_last_visit(client_code)
        update_activity_status()
        
        # Если клиент уже находится в режиме уточнения (pending guiding questions)
        if client_code in pending_guiding:
            pending = pending_guiding[client_code]
            # Если клиент явно пишет "базовая цена" (или содержит слово "базовая"), то возвращаем только базовую цену
            if "базовая" in user_message.lower():
                final_price = get_price_response_wrapper(pending["vehicle_type"], direction="Ro_Ge", client_guiding_answers=[])
                response_message = f"Базовая цена составляет: {final_price}"
                del pending_guiding[client_code]
            # Если клиент присылает сообщение с ключевыми словами, означающими завершение уточнения
            elif is_price_query(user_message):
                final_price = get_price_response_wrapper(pending["vehicle_type"], direction="Ro_Ge", client_guiding_answers=pending["answers"])
                response_message = f"Спасибо, ваши ответы приняты. {final_price}"
                del pending_guiding[client_code]
            else:
                # Иначе сохраняем очередной ответ и спрашиваем следующий guiding вопрос
                pending.setdefault("answers", []).append(user_message)
                pending["current_index"] += 1
                if pending["current_index"] < len(pending["conditions"]):
                    response_message = pending["conditions"][pending["current_index"]]
                else:
                    final_price = get_price_response_wrapper(pending["vehicle_type"], direction="Ro_Ge", client_guiding_answers=pending["answers"])
                    response_message = f"Спасибо, ваши ответы приняты. {final_price}"
                    del pending_guiding[client_code]
        # Если запрос содержит ключевые слова о цене и клиент не в guiding режиме
        elif is_price_query(user_message):
            vehicle_type = get_vehicle_type(user_message)
            if not vehicle_type:
                response_message = ("Для определения цены, пожалуйста, уточните тип транспортного средства "
                                    "(например, грузовик или фура).")
            else:
                # Загружаем данные из Price.xlsx через load_price_data() из price_handler.py
                price_data = load_price_data()
                if vehicle_type not in price_data:
                    response_message = f"Извините, информация о тарифах для '{vehicle_type}' отсутствует в нашей базе."
                else:
                    conditions = price_data[vehicle_type].get("conditions", [])
                    if conditions:
                        # Если guiding questions имеются, сохраняем состояние и задаем первый вопрос
                        pending_guiding[client_code] = {
                            "vehicle_type": vehicle_type,
                            "conditions": conditions,
                            "current_index": 0,
                            "answers": []
                        }
                        response_message = conditions[0]
                    else:
                        response_message = get_price_response_wrapper(vehicle_type, direction="Ro_Ge")
        else:
            # Стандартная обработка: формируем контекст из Bible.xlsx и истории переписки, затем вызываем OpenAI
            messages = prepare_chat_context(client_code)
            messages.append({"role": "user", "content": user_message})
            openai_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=150
            )
            response_message = openai_response['choices'][0]['message']['content'].strip()
        
        add_message_to_client_file(client_code, user_message, is_assistant=False)
        add_message_to_client_file(client_code, response_message, is_assistant=True)
        
        logger.info(f"Ответ от OpenAI/price_handler: {response_message}")
        return jsonify({'reply': response_message}), 200
    except Exception as e:
        logger.error(f"❌ Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "Server is running!"}), 200

##############################################
# Интеграция Telegram Bot для команды /bible
##############################################
from telegram.ext import ConversationHandler

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("Переменная окружения TELEGRAM_BOT_TOKEN не задана!")
    exit(1)

BIBLE_ASK_ACTION, BIBLE_ASK_QUESTION, BIBLE_ASK_ANSWER = range(3)

async def bible_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите 'add' для добавления новой пары вопрос-ответ, или 'cancel' для отмены.")
    return BIBLE_ASK_ACTION

async def ask_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    action = update.message.text.strip().lower()
    if action == "add":
        context.user_data['action'] = 'add'
        await update.message.reply_text("Введите новый вопрос:")
        return BIBLE_ASK_QUESTION
    elif action == "cancel":
        return await cancel_bible(update, context)
    else:
        await update.message.reply_text("Неверное значение. Введите 'add' или 'cancel'.")
        return BIBLE_ASK_ACTION

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    question = update.message.text.strip()
    context.user_data['question'] = question
    await update.message.reply_text("Введите ответ для этого вопроса:")
    return BIBLE_ASK_ANSWER

async def ask_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip()
    question = context.user_data.get('question')
    logger.info(f"Сохраняем пару: Вопрос: {question} | Ответ: {answer}")
    try:
        save_bible_pair(question, answer)
    except Exception as e:
        logger.error(f"Ошибка сохранения пары в Bible.xlsx: {e}")
    await update.message.reply_text("Пара вопрос-ответ сохранена с отметкой 'Check'.")
    return ConversationHandler.END

async def cancel_bible(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

bible_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("bible", bible_start)],
    states={
        BIBLE_ASK_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_action)],
        BIBLE_ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_question)],
        BIBLE_ASK_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_answer)],
    },
    fallbacks=[CommandHandler("cancel", cancel_bible)]
)

application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
bot = application.bot
application.add_handler(bible_conv_handler)

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot)
        global_loop.run_until_complete(application.process_update(update))
        return 'OK', 200
    except Exception as e:
        logger.error(f"Ошибка обработки Telegram update: {e}")
        return jsonify({'error': str(e)}), 500

##############################################
# Основной блок запуска
##############################################
global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error("Переменная окружения WEBHOOK_URL не задана!")
        exit(1)
    global_loop.run_until_complete(application.initialize())
    global_loop.run_until_complete(bot.set_webhook(WEBHOOK_URL))
    logger.info(f"Webhook установлен на {WEBHOOK_URL}")
    logger.info(f"✅ Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
