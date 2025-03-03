import os
import re
import logging
import time
import openai
import requests
from bible import get_rule

try:
    from price import get_ferry_prices
except ImportError:
    get_ferry_prices = None  # Заглушка

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def remove_timestamp(text):
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
    try:
        cleaned = re.sub(r'[^\d.]', '', price_str)
        return float(cleaned) if cleaned else None
    except Exception as e:
        logger.error(f"{get_rule('price_parse_error')}: {e}")
        return None

def get_guiding_question(condition_marker):
    return f"Уточните: {condition_marker}?"

def get_openai_response(messages):
    start_time = time.time()
    attempt = 0
    while True:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=150,
                timeout=40
            )
            return response
        except Exception as e:
            logger.error(f"OpenAI error attempt {attempt+1}: {e}")
            attempt += 1
            if time.time() - start_time > 180:
                return get_rule("openai_timeout_message")
            time.sleep(2)

def check_ferry_price(vehicle_type, direction="Ro_Ge"):
    if get_ferry_prices is None:
        logger.error("Функция get_ferry_prices отсутствует, невозможно получить тарифы.")
        return get_rule("price_error_message")

    try:
        website_prices = get_ferry_prices()
        logger.info(f"Доступные категории: {list(website_prices.keys())}")
    except Exception as e:
        logger.error(f"Ошибка при получении тарифов с сайта: {e}")
        return get_rule("price_error_message")
    
    category = next((key for key in website_prices if key.lower() == vehicle_type.lower()), None)
    if category is None:
        return get_rule("vehicle_type_not_found").format(vehicle_type=vehicle_type)

    price_str = website_prices[category].get("price_Ro_Ge" if direction == "Ro_Ge" else "price_Ge_Ro", "")
    price_str = remove_timestamp(price_str).strip()
    if not re.search(r'\d', price_str):
        return get_rule("invalid_price_returned").format(vehicle_type=vehicle_type)

    remark = website_prices[category].get("remark", "")
    conditions = website_prices[category].get("conditions", "")

    response = f"Цена перевозки {vehicle_type} ({direction.replace('_', ' ')}) составляет {price_str}."
    if remark:
        response += f" Примечание: {remark}"
    if conditions:
        response += f" Доп. условия: {conditions}"
    return response
