import os
import re
import logging
import time
import openai
import requests
from bible import get_rule
from price import get_ferry_prices  # Функция извлечения тарифов с сайта

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def remove_timestamp(text):
    """
    Удаляет временную метку в начале строки вида "DD.MM.YY HH:MM - ".
    """
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
    """
    Извлекает числовое значение цены из строки.
    Удаляет все символы, кроме цифр и точки, и пытается преобразовать результат в float.
    Если значение не найдено, возвращает None.
    """
    try:
        cleaned = re.sub(r'[^\d.]', '', price_str)
        if not cleaned:
            return None
        value = float(cleaned)
        logger.info(f"Parsed price: '{price_str}' -> {value}")
        return value
    except Exception as e:
        logger.error(f"{get_rule('price_parse_error')}: {e}")
        return None

def get_guiding_question(condition_marker):
    """
    Возвращает уточняющий вопрос для заданного условия.
    """
    return f"Уточните: {condition_marker}?"

def get_openai_response(messages):
    """
    Отправляет запрос в OpenAI ChatCompletion, повторяя попытки до достижения общего таймаута.
    Если время истекло, возвращает стандартное сообщение, заданное правилом.
    """
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
    """
    Определяет тариф для указанного типа транспортного средства и направления.
    Алгоритм:
      1. Загружает тарифы с сайта через функцию get_ferry_prices().
      2. Пытается найти категорию, совпадающую с vehicle_type (сравнение без учета регистра).
      3. Если категория найдена, извлекает цену для направления:
         - "price_Ro_Ge" для направления "Ro_Ge"
         - "price_Ge_Ro" для направления "Ge_Ro"
      4. Применяет remove_timestamp для очистки строки цены.
      5. Если в полученной строке отсутствуют числовые данные, возвращает сообщение об ошибке.
      6. Если имеются дополнительные данные (примечание, условия), они добавляются к ответу.
    """
    try:
        website_prices = get_ferry_prices()
        logger.info(f"Доступные тарифные категории: {list(website_prices.keys())}")
    except Exception as e:
        logger.error(f"Ошибка при получении тарифов с сайта: {e}")
        return get_rule("price_error_message")
    
    category = None
    # Ищем точное совпадение (без учета регистра)
    for key in website_prices:
        if key.lower() == vehicle_type.lower():
            category = key
            break
    if category is None:
        logger.error(get_rule("vehicle_type_not_found").format(vehicle_type=vehicle_type))
        return get_rule("vehicle_type_not_found").format(vehicle_type=vehicle_type)
    
    if direction == "Ro_Ge":
        price_str = website_prices[category].get("price_Ro_Ge", "")
    else:
        price_str = website_prices[category].get("price_Ge_Ro", "")
    
    price_str = remove_timestamp(price_str).strip()
    if not re.search(r'\d', price_str):
        logger.error(get_rule("invalid_price_returned").format(vehicle_type=vehicle_type))
        return get_rule("invalid_price_returned").format(vehicle_type=vehicle_type)
    
    remark = website_prices[category].get("remark", "")
    conditions = website_prices[category].get("conditions", "")
    response = f"Цена перевозки для {vehicle_type} (направление {direction.replace('_', ' ')}) составляет {price_str}."
    if remark:
        response += f" Примечание: {remark}"
    if conditions:
        response += f" Дополнительные условия: {conditions}"
    return response

if __name__ == "__main__":
    # Тестовые примеры
    sample_vehicle = "легкового авто"
    sample_direction = "Ro_Ge"
    result = check_ferry_price(sample_vehicle, sample_direction)
    logger.info(f"Результат для '{sample_vehicle}' ({sample_direction}): {result}")
