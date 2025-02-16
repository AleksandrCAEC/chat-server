import os
import re
import logging
import asyncio
import pprint
import threading
from flask import Flask, request, jsonify
import openai
import requests
from datetime import datetime
from clientdata import register_or_update_client, verify_client_code, update_last_visit
from client_caec import add_message_to_client_file, find_client_file_id, get_sheets_service, CLIENT_FILES_DIR
from bible import load_bible_data, save_bible_pair
from price_handler import check_ferry_price, load_price_data  # Тарифы получаются через эту функцию
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

# Глобальный словарь для хранения состояния уточняющих вопросов (guiding questions)
# Дополнительные уточняющие вопросы отключены – единственный возможный уточняющий вопрос касается направления.
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
# ФУНКЦИЯ ПОДГОТОВКИ КОНТЕКСТА (ПАМЯТЬ АССИСТЕНТА)
###############################################
def prepare_chat_context(client_code):
    messages = []
    bible_df = load_bible_data()
    if bible_df is None:
        raise Exception("Bible.xlsx не найден или недоступен.")
    logger.info(f"Bible.xlsx содержит {len(bible_df)} записей.")
    
    # Внутренние правила (FAQ = "-" и Verification = "RULE") используются только для внутренней логики.
    internal_rules = []
    for index, row in bible_df.iterrows():
        faq = row.get("FAQ", "").strip()
        answer = row.get("Answers", "").strip()
        verification = str(row.get("Verification", "")).strip().upper()
        if faq == "-" and verification == "RULE" and answer:
            internal_rules.append(answer)
    if internal_rules:
        system_instructions = "Инструкция для ассистента (не показывать клиенту): " + " ".join(internal_rules)
        messages.append({"role": "system", "content": system_instructions})
    
    # Общая информация из Bible.xlsx (только строки, где FAQ != "-" и Verification != "RULE")
    for index, row in bible_df.iterrows():
        faq = row.get("FAQ", "").strip()
        answer = row.get("Answers", "").strip()
        verification = str(row.get("Verification", "")).strip().upper()
        if faq and faq != "-" and answer and verification != "RULE":
            messages.append({"role": "system", "content": f"Вопрос: {faq}\nОтвет: {answer}"})
    
    # История переписки из уникального файла клиента
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
# ФУНКЦИЯ ДЛЯ ИЗВЛЕЧЕНИЯ ПОЛНОГО ОПИСАНИЯ ТС
###############################################
def get_last_vehicle_description(client_code):
    """
    Извлекает последнее полное сообщение от клиента, содержащее информацию о транспортном средстве,
    из истории переписки (использует prepare_chat_context).
    Возвращает текст или None, если подходящее сообщение не найдено.
    """
    try:
        messages = prepare_chat_context(client_code)
    except Exception as e:
        logger.error(f"Ошибка получения истории переписки: {e}")
        return None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            text = msg.get("content", "").strip()
            if text and (re.search(r'\d+', text) or any(kw in text.lower() for kw in ["фура", "грузовик", "минивэн", "minivan", "тягач", "еврофура"])):
                return text
    return None

###############################################
# ЭНДПОИНТ /register-client
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

###############################################
# ЭНДПОИНТ /verify-code
###############################################
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

###############################################
# ЭНДПОИНТ /get-price - для проверки тарифа через Postman
###############################################
@app.route('/get-price', methods=['POST'])
def get_price_endpoint():
    """
    Эндпоинт ожидает POST-запрос с JSON-телом:
    {
       "vehicle_description": "Минивэн, Из Констанцы в Поти",
       "direction": "Ge_Ro"  // или "Ro_Ge"
    }
    """
    data = request.get_json()
    if not data or "vehicle_description" not in data:
        return jsonify({"error": "Не передано описание транспортного средства"}), 400

    vehicle_description = data["vehicle_description"]
    direction = data.get("direction", "Ro_Ge")
    
    result = check_ferry_price(vehicle_description, direction=direction)
    return jsonify({"price": result}), 200

###############################################
# ЭНДПОИНТ /chat
###############################################
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        logger.info(f"Получен запрос на чат: {data}")
        user_message = data.get("message", "").strip()
        client_code = data.get("client_code", "").strip()
        if not user_message or not client_code:
            logger.error("Ошибка: Сообщение и код клиента не могут быть пустыми")
            return jsonify({'error': 'Сообщение и код клиента не могут быть пустыми'}), 400

        # Проверяем наличие ключевых файлов: Bible.xlsx и файла клиента.
        try:
            bible_data = load_bible_data()
        except Exception as e:
            logger.error(f"Ошибка загрузки Bible.xlsx: {e}")
            send_telegram_notification("Ошибка базы данных: файл Bible.xlsx не найден. Пожалуйста, подключите менеджера.")
            return jsonify({'error': 'Ошибка базы данных: Bible.xlsx не найден.'}), 500

        client_file_id = find_client_file_id(client_code)
        if client_file_id is None:
            send_telegram_notification(f"Ошибка базы данных: для клиента {client_code} не найден файл переписки. Пожалуйста, подключите менеджера.")
            return jsonify({'error': 'Ошибка базы данных: файл клиента не найден.'}), 500

        update_last_visit(client_code)
        
        # Обработка запроса о тарифе.
        if ("цена" in user_message.lower() or "прайс" in user_message.lower() or 
            "минивэн" in user_message.lower() or "minivan" in user_message.lower() or
            "truck" in user_message.lower() or "траk" in user_message.lower()):
            lower_msg = user_message.lower()
            # Определяем направление, если оно явно указано.
            if "из поти" in lower_msg:
                direction = "Ge_Ro"
            elif "из констанца" in lower_msg or "из констанцы" in lower_msg:
                direction = "Ro_Ge"
            elif "грузия" in lower_msg or "из груз" in lower_msg:
                direction = "Ge_Ro"
            else:
                response_message = "Пожалуйста, уточните направление отправки (например, Поти-Констанца или Констанца-Поти)."
                add_message_to_client_file(client_code, user_message, is_assistant=False)
                add_message_to_client_file(client_code, response_message, is_assistant=True)
                return jsonify({'reply': response_message}), 200
            
            # Если сообщение выглядит как уточнение (короткое сообщение) – используем последнее полное описание
            if len(user_message) < 20:
                last_description = get_last_vehicle_description(client_code)
                if last_description:
                    # Удаляем из полного описания любые упоминания направлений.
                    cleaned_description = re.sub(r'\bиз\s+\w+(?:\s+в\s+\w+)?', '', last_description, flags=re.IGNORECASE).strip()
                    logger.debug(f"Используем последнее полное описание (очищенное): '{cleaned_description}'")
                    response_message = check_ferry_price(vehicle_description=cleaned_description, direction=direction)
                else:
                    response_message = check_ferry_price(vehicle_description=user_message, direction=direction)
            else:
                response_message = check_ferry_price(vehicle_description=user_message, direction=direction)
        else:
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

###############################################
# ЭНДПОИНТ домашней страницы (/)
###############################################
@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "Server is running!"}), 200

###############################################
# Интеграция Telegram Bot для команды /bible
###############################################
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

###############################################
# Основной блок запуска
###############################################
def setup_webhook():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error("Переменная окружения WEBHOOK_URL не задана!")
        exit(1)
    try:
        loop.run_until_complete(application.initialize())
        loop.run_until_complete(bot.set_webhook(WEBHOOK_URL))
        logger.info(f"Webhook установлен на {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Ошибка установки webhook: {e}")
    finally:
        loop.close()

global_loop = asyncio.new_event_loop()
asyncio.set_event_loop(global_loop)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    threading.Thread(target=setup_webhook).start()
    logger.info(f"✅ Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
