# price_handler.py
import os
import re
import logging
import json
from price import get_ferry_prices
# Убираем импорты, связанные с Google Sheets, поскольку работа с файлом price.xlsx отключена.
# from google.oauth2.service_account import Credentials
# from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Поскольку тарифы из файла price.xlsx не используются, PRICE_SPREADSHEET_ID можно оставить или удалить.
# PRICE_SPREADSHEET_ID = "1N4VpU1rBw3_MPx6GJRDiSQ03iHhS24noTq5-i6V01z8"

def send_telegram_notification(message):
    """
    Отправляет уведомление через Telegram, используя переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID.
    """
    try:
        import requests
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
    """
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
    """
    Извлекает числовое значение из строки цены.
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
    Получает тариф перевозки для указанного типа транспортного средства и направления,
    используя данные, полученные с сайта через get_ferry_prices().
    
    Поскольку работа с файлом price.xlsx отключена, здесь используется только информация с сайта.
    Если тариф не найден, возвращается соответствующее сообщение.
    """
    try:
        website_prices = get_ferry_prices()
        # Поиск ключа с частичным совпадением (без учёта регистра)
        matched_key = None
        for key in website_prices.keys():
            if vehicle_type.lower() in key.lower():
                matched_key = key
                break
        if not matched_key:
            return f"Извините, актуальная цена для транспортного средства '{vehicle_type}' не найдена на сайте."
        
        if direction == "Ro_Ge":
            website_price = website_prices[matched_key].get("price_Ro_Ge", "")
        else:
            website_price = website_prices[matched_key].get("price_Ge_Ro", "")
        
        response_message = f"Цена перевозки для '{vehicle_type}' ({direction.replace('_', ' ')}) составляет {website_price}."
        remark = website_prices[matched_key].get("remark", "")
        if remark:
            response_message += f" Примечание: {remark}"
        return response_message
    except Exception as e:
        logger.error(f"Ошибка при получении цены: {e}")
        return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."

if __name__ == "__main__":
    vehicle = "Truck"
    direction = "Ro_Ge"
    message = check_ferry_price(vehicle, direction)
    print(message)
