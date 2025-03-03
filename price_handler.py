import os
import re
import logging
import time
import openai
import requests
from bible import get_rule

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def remove_timestamp(text):
    """
    Удаляет возможную временную метку в начале строки вида "DD.MM.YY HH:MM - ".
    """
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
    """
    Извлекает числовое значение цены из строки.
    Удаляет все символы, кроме цифр и точки, и пытается преобразовать результат в float.
    Если результат пуст или не может быть преобразован, возвращает None.
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
    Возвращает уточняющий вопрос по указанному условию.
    Если требуется, можно расширить логику для разных condition_marker.
    """
    return f"Уточните условие: {condition_marker}?"

def get_openai_response(messages):
    """
    Отправляет запрос в OpenAI ChatCompletion, повторяя попытки до достижения общего таймаута.
    В случае неудачи возвращает стандартное сообщение, заданное правилом.
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

if __name__ == "__main__":
    # Пример тестирования функций parse_price и remove_timestamp
    sample_price = "15,990 (EUR)"
    parsed = parse_price(sample_price)
    print(f"Parsed price: {parsed}")
    
    sample_text = "03.03.25 14:30 - 15,990 (EUR)"
    cleaned_text = remove_timestamp(sample_text)
    print(f"Cleaned text: '{cleaned_text}'")
