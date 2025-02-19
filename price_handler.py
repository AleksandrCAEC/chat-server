# price_handler.py
import os
import re
import logging
import time
from price import get_ferry_prices
import requests
import tempfile

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Замените на актуальный Spreadsheet ID для файла Price.xlsx (файл временно отключён)
PRICE_SPREADSHEET_ID = "1N4VpU1rBw3_MPx6GJRDiSQ03iHhS24noTq5-i6V01z8"

def get_credentials_file():
    """
    Если переменная окружения GOOGLE_APPLICATION_CREDENTIALS содержит путь, возвращает его;
    если содержит JSON-текст, записывает его во временный файл и возвращает путь к нему.
    """
    env_val = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_val is None:
        raise Exception("Переменная окружения GOOGLE_APPLICATION_CREDENTIALS не установлена.")
    env_val = env_val.strip()
    if env_val.startswith("{"):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
        tmp.write(env_val)
        tmp.close()
        logger.info(f"Содержимое переменной окружения записано во временный файл: {tmp.name}")
        return tmp.name
    return os.path.abspath(env_val)

def get_sheets_service():
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        credentials = Credentials.from_service_account_file(get_credentials_file())
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def send_telegram_notification(message):
    """
    Отправляет уведомление через Telegram, используя переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID.
    """
    try:
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if telegram_bot_token and telegram_chat_id:
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
            requests.post(url, json=payload)
    except Exception as ex:
        logger.error(f"Ошибка при отправке уведомления: {ex}")

def remove_timestamp(text):
    """
    Удаляет из строки временной штамп в начале строки.
    Пример: "10.02.25 09:33 - 2200 (EUR)" -> "2200 (EUR)"
    """
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
    """
    Извлекает числовое значение из строки цены.
    Пример: "2200 (EUR)" -> 2200.0
    """
    try:
        cleaned = re.sub(r'[^\d.]', '', price_str)
        value = float(cleaned)
        logger.info(f"Parsed price '{price_str}' -> {value}")
        return value
    except Exception as e:
        logger.error(f"Ошибка парсинга цены из '{price_str}': {e}")
        return None

def check_ferry_price(vehicle_type, direction="Ro_Ge"):
    """
    Получает цену перевозки для указанного типа транспортного средства и направления исключительно с сайта.
    Поскольку файл price.xlsx временно отключён, используется только информация с сайта.
    direction: "Ro_Ge" для направления Romania -> Georgia, "Ge_Ro" для направления Georgia -> Romania.
    """
    try:
        website_prices = get_ferry_prices()
        if vehicle_type not in website_prices:
            return f"Извините, актуальная цена для транспортного средства '{vehicle_type}' не найдена на сайте."
        
        if direction == "Ro_Ge":
            price = website_prices[vehicle_type].get("price_Ro_Ge", "")
        else:
            price = website_prices[vehicle_type].get("price_Ge_Ro", "")
        
        response_message = f"Цена перевозки для '{vehicle_type}' ({direction.replace('_', ' ')}) составляет {price}."
        
        remark = website_prices[vehicle_type].get("remark", "")
        if remark:
            response_message += f" Примечание: {remark}"
        
        condition = website_prices[vehicle_type].get("condition", "")
        if condition:
            response_message += f" Условие: {condition}"
        
        return response_message
    except Exception as e:
        logger.error(f"Ошибка при получении цены: {e}")
        return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."

def get_openai_response(messages):
    start_time = time.time()
    attempt = 0
    while True:
        try:
            import openai
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=150,
                timeout=40
            )
            return response
        except Exception as e:
            logger.error(f"Попытка {attempt+1} ошибки в OpenAI: {e}")
            attempt += 1
            if time.time() - start_time > 180:
                send_telegram_notification(get_rule())
                return None
            time.sleep(2)

if __name__ == "__main__":
    vehicle = "Truck"
    direction = "Ro_Ge"
    message = check_ferry_price(vehicle, direction)
    print(message)
