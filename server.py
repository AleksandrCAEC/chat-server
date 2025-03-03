import os
import re
import logging
import asyncio
import pprint
from flask import Flask, request, jsonify
import openai
import requests
from datetime import datetime
from clientdata import register_or_update_client, verify_client_code, update_last_visit
from client_caec import add_message_to_client_file, find_client_file_id, get_sheets_service, CLIENT_FILES_DIR
from bible import load_bible_data, save_bible_pair
from price_handler import check_ferry_price, load_price_data, TYPE_SYNONYMS
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

# Импорты для обработки текста
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.stem import SnowballStemmer
from fuzzywuzzy import fuzz

# Загрузка необходимых ресурсов NLTK
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

# Инициализация лемматизатора и списка стоп-слов
lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('russian'))

# Установка переменной окружения для учетных данных Google и API-ключа OpenAI
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "./service_account.json")
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

# Глобальный словарь для хранения состояния последовательных уточняющих вопросов (guiding questions)
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

####################################################
# ЗАГРУЗКА И ПРИМЕНЕНИЕ ALIAS-ПРАВИЛ ИЗ BIBLE.XLSX
####################################################
try:
    bible_df = load_bible_data()
    if bible_df is not None:
        # Отфильтровать строки, являющиеся alias-правилами
        if "rule" in bible_df.columns:
            alias_df = bible_df[bible_df["rule"].str.strip().str.lower() == "alias"]
        else:
            # Если нет явной отметки "alias", считать alias все записи с перечислением синонимов через запятую
            alias_df = bible_df[bible_df["FAQ"].str.contains(",")]
        alias_count = 0
        for _, row in alias_df.iterrows():
            faq = str(row["FAQ"])
            answer = str(row["Answers"]).strip()
            if not answer:
                continue
            # Стандартное название категории приводим к формату сайта (первая буква заглавная, остальное без изменений)
            official = answer[0].upper() + answer[1:] if len(answer) > 0 else answer
            # Добавить все синонимы (через запятую) в словарь TYPE_SYNONYMS
            for syn in faq.split(','):
                syn = syn.strip().lower()
                if syn:
                    TYPE_SYNONYMS[syn] = official
                    alias_count += 1
                    logger.debug(f"Alias added: '{syn}' -> '{official}'")
        logger.info(f"Загружено alias-правил: {alias_count} синонимов из Bible.xlsx")
    else:
        logger.error("Bible data not loaded – alias rules not applied.")
except Exception as e:
    logger.error(f"Ошибка при обработке Bible.xlsx для синонимов: {e}")

###############################################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ОБРАБОТКИ ЗАПРОСОВ О ЦЕНЕ
###############################################
PRICE_KEYWORDS = ["цена", "прайс", "сколько стоит", "во сколько обойдется"]

def is_price_query(text):
    return any(keyword in text.lower() for keyword in PRICE_KEYWORDS)

def get_vehicle_type(text):
    # Простейшее определение типа ТС по ключевым словам
    known_types = {"truck": "Truck", "грузовик": "Truck", "fura": "Fura", "фура": "Fura"}
    for key, standard in known_types.items():
        if key in text.lower():
            return standard
    return None

def get_price_response(vehicle_text, direction="Ro_Ge"):
    try:
        response = check_ferry_price(vehicle_text, direction)
        return response
    except Exception as e:
        logger.error(f"Ошибка при получении цены для '{vehicle_text}': {e}")
        return "Произошла ошибка при получении актуальной цены. Пожалуйста, попробуйте позже."

###############################################
# ФУНКЦИЯ ПРЕДОБРАБОТКИ ТЕКСТА (ЛЕММАТИЗАЦИЯ, СТОП-СЛОВА)
###############################################
# Инициализируем морфологический анализатор для русского (pymorphy2) или SnowballStemmer
try:
    import pymorphy2
    morph = pymorphy2.MorphAnalyzer()
    logger.info("Russian Morphological analyzer (pymorphy2) initialized for lemmatization.")
except Exception as e:
    morph = None
    logger.warning(f"pymorphy2 not available, using Snowball stemmer for Russian. Exception: {e}")
    russian_stemmer = SnowballStemmer("russian")

def preprocess_text(text):
    # Приведение к нижнему регистру и удаление пунктуации
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    words = nltk.word_tokenize(text)
    # Лемматизация (или стемминг) и удаление стоп-слов
    if morph:
        words = [morph.parse(word)[0].normal_form for word in words if word not in stop_words]
    else:
        words = [russian_stemmer.stem(word) for word in words if word not in stop_words]
    normalized_text = " ".join(words)
    logger.debug(f"Normalized text: '{text}' -> '{normalized_text}'")
    return normalized_text

###############################################
# ПОДГОТОВКА КОНТЕКСТА (ИСТОРИИ) ДЛЯ OPENAI-ЧАТА
###############################################
def prepare_chat_context(client_code):
    messages = []
    bible_df = load_bible_data()
    if bible_df is None:
        raise Exception("Bible.xlsx не найден или недоступен.")
    logger.info(f"Bible.xlsx содержит {len(bible_df)} записей.")
    
    # Собрать системные правила из строк, где FAQ = "-" и Verification = "RULE"
    rules_df = bible_df[(bible_df["FAQ"].str.strip() == "-") & (bible_df["Verification"].str.upper() == "RULE")]
    system_rule = "\n".join(rules_df["Answers"].tolist())
    
    # Строгие инструкции для ассистента
    strict_instructions = (
        "ВНИМАНИЕ: Ниже приведены обязательные правила, которым вы должны строго следовать. "
        "1. Все инструкции, полученные из документа Bible.xlsx, имеют высший приоритет и обязательны к исполнению. "
        "2. Вы не должны отклоняться от этих правил ни при каких обстоятельствах. "
        "3. При формировании ответов используйте исключительно данные, предоставленные в этих инструкциях. "
        "4. Любые дополнительные предположения или информация, противоречащая указанным правилам, должны игнорироваться."
    )
    
    system_message = {
        "role": "system",
        "content": f"{strict_instructions}\n\n{system_rule}"
    }
    messages.append(system_message)
    
    # Загрузка истории диалога клиента из Google Sheets (если есть)
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

# Маршруты Flask API
@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        logger.info(f"Получен запрос на регистрацию клиента: {data}")
        result = register_or_update_client(data)
        if result.get("isNewClient", True):
            send_telegram_notification(
                f"🆕 Новый пользователь зарегистрирован: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}"
            )
        else:
            send_telegram_notification(
                f"🔙 Пользователь вернулся: {result['name']}, {result['email']}, {result['phone']}, Код: {result['uniqueCode']}"
            )
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
            send_telegram_notification(
                f"✅ Код подтверждён для: {client_data['Name']}, {client_data['Email']}, {client_data['Phone']}, Код: {code}"
            )
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

        # Обновить время последнего визита пользователя
        update_last_visit(client_code)

        # Проверка: является ли сообщение запросом о цене парома
        if is_price_query(user_message):
            # Обработка запроса о цене паромной перевозки
            logger.info(f"Обнаружен ценовой запрос: '{user_message}'")
            price_response = check_ferry_price(user_message, direction="Ro_Ge")
            logger.info(f"Ответ на ценовой запрос: {price_response}")
            # Сохранение переписки в файл клиента
            add_message_to_client_file(client_code, user_message, price_response)
            return jsonify({"response": price_response}), 200

        # Обычный запрос – формируем контекст и запрашиваем OpenAI
        messages = prepare_chat_context(client_code)
        messages.append({"role": "user", "content": user_message})
        logger.info("Отправка запроса в OpenAI ChatCompletion")
        try:
            openai_resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=150,
                timeout=30
            )
            assistant_reply = openai_resp['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Ошибка OpenAI: {e}")
            assistant_reply = "Извините, произошла ошибка при обработке запроса."
        # Сохранение переписки
        add_message_to_client_file(client_code, user_message, assistant_reply)
        return jsonify({"response": assistant_reply}), 200

    except Exception as e:
        logger.error(f"❌ Ошибка в /chat: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    # Запуск Flask-приложения
    app.run(host="0.0.0.0", port=8080)
