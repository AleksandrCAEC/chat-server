import os
import re
import logging
import time
from price import get_ferry_prices
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import requests
from bible import load_bible_data, get_rule

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

PRICE_SPREADSHEET_ID = "1N4VpU1rBw3_MPx6GJRDiSQ03iHhS24noTq5-i6V01z8"

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        service = build('sheets', 'v4', credentials=credentials)
        logger.info(get_rule())
        return service
    except Exception as e:
        logger.error(f"{get_rule()}: {e}")
        raise

def send_telegram_notification(message):
    try:
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if telegram_bot_token and telegram_chat_id:
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
            response = requests.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"{get_rule()}: {response.json()}")
    except Exception as ex:
        if hasattr(ex, 'retry_after'):
            delay = ex.retry_after
            logger.warning(f"{get_rule()} {delay} секунд.")
            time.sleep(delay)
            send_telegram_notification(message)
        else:
            logger.error(f"{get_rule()}: {ex}")

def remove_timestamp(text):
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
    try:
        cleaned = re.sub(r'[^\d.]', '', price_str)
        value = float(cleaned)
        logger.info(f"Parsed price '{price_str}' -> {value}")
        return value
    except Exception as e:
        logger.error(f"{get_rule()}: {e}")
        return None

def get_guiding_question(condition_marker):
    bible_df = load_bible_data()
    if bible_df is None:
        return None
    for index, row in bible_df.iterrows():
        if row["Verification"].strip().upper() == "RULE":
            question = row["Answers"].strip()
            logger.info(f"{get_rule()} {condition_marker}: {question}")
            return question
    logger.info(f"{get_rule()} {condition_marker}")
    return None

def check_ferry_price(vehicle_type, direction="Ro_Ge"):
    try:
        website_prices = get_ferry_prices()
        logger.info(f"{get_rule()}: {website_prices}")
        
        if vehicle_type not in website_prices:
            msg = f"Извините, актуальная цена для '{vehicle_type}' не найдена на сайте."
            logger.error(msg)
            return msg
        
        if direction == "Ro_Ge":
            website_price_str = website_prices[vehicle_type].get("price_Ro_Ge", "")
        else:
            website_price_str = website_prices[vehicle_type].get("price_Ge_Ro", "")
        
        website_price_str = remove_timestamp(website_price_str).strip()
        logger.info(f"Цена с сайта для {vehicle_type}: '{website_price_str}'")
        
        if not re.search(r'\d', website_price_str) or website_price_str.upper() in ["PRICE_QUERY", "BASE_PRICE"]:
            logger.info(f"{get_rule()} для {vehicle_type}")
            return website_price_str
        
        response_message = f"Цена перевозки для '{vehicle_type}' ({direction.replace('_', ' ')}) составляет {website_price_str}."
        remark = website_prices[vehicle_type].get("remark", "")
        if remark:
            response_message += f" Примечание: {remark}"
        conditions = website_prices[vehicle_type].get("conditions", [])
        if conditions:
            response_message += "\nДля более точного расчёта, пожалуйста, ответьте на следующие вопросы:"
            for marker in conditions:
                response_message += f"\n{marker}"
        return response_message
    except Exception as e:
        logger.error(f"{get_rule()}: {e}")
        return get_rule()

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
    vehicle = ""
    direction = "Ro_Ge"
    message = check_ferry_price(vehicle, direction)
    print(message)
