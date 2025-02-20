# price_handler.py
import os
import re
import logging
from price import get_ferry_prices

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def send_telegram_notification(message):
    """
    Отправляет уведомление менеджеру через Telegram (если заданы переменные окружения).
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
        logger.error(f"Ошибка при отправке уведомления в Telegram: {ex}")

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
    Получает тариф перевозки для указанного типа ТС, используя ТОЛЬКО данные с сайта (get_ferry_prices).
    Если тариф не найден, возвращает сообщение об отсутствии данных.
    """
    try:
        website_prices = get_ferry_prices()  # Загружаем все тарифы с сайта
        matched_key = None
        
        # Пытаемся найти подходящий ключ с частичным совпадением (без учёта регистра)
        for key in website_prices.keys():
            if vehicle_type.lower() in key.lower():
                matched_key = key
                break
        
        if not matched_key:
            return f"Извините, актуальная цена для транспортного средства '{vehicle_type}' не найдена на сайте."
        
        if direction == "Ro_Ge":
            site_price = website_prices[matched_key].get("price_Ro_Ge", "")
        else:
            site_price = website_prices[matched_key].get("price_Ge_Ro", "")
        
        # Формируем ответ
        response_message = f"Цена перевозки для '{vehicle_type}' ({direction.replace('_', ' ')}) составляет {site_price}."
        remark = website_prices[matched_key].get("remark", "")
        if remark:
            response_message += f" Примечание: {remark}"
        return response_message
    except Exception as e:
        logger.error(f"Ошибка при получении цены: {e}")
        return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."
