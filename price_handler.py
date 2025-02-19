# price_handler.py
import os
import re
import logging
import time
from price import get_ferry_prices
import requests
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

PRICE_SPREADSHEET_ID = "1N4VpU1rBw3_MPx6GJRDiSQ03iHhS24noTq5-i6V01z8"

def get_credentials():
    env_val = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not env_val:
        raise Exception("Переменная окружения GOOGLE_APPLICATION_CREDENTIALS не установлена.")
    env_val = env_val.strip()
    if env_val.startswith('"') and env_val.endswith('"'):
        env_val = env_val[1:-1].strip()
    if env_val.startswith("{"):
        return Credentials.from_service_account_info(json.loads(env_val))
    else:
        return Credentials.from_service_account_file(os.path.abspath(env_val))

def get_sheets_service():
    try:
        credentials = get_credentials()
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def send_telegram_notification(message):
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
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
    try:
        cleaned = re.sub(r'[^\d.]', '', price_str)
        value = float(cleaned)
        logger.info(f"Parsed price '{price_str}' -> {value}")
        return value
    except Exception as e:
        logger.error(f"Ошибка парсинга цены из '{price_str}': {e}")
        return None

def check_ferry_price(vehicle_type, direction="Ro_Ge"):
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
                send_telegram_notification("Ошибка OpenAI. Превышено время ожидания.")
                return None
            time.sleep(2)

if __name__ == "__main__":
    vehicle = "Truck"
    direction = "Ro_Ge"
    message = check_ferry_price(vehicle, direction)
    print(message)
