import os
import logging
import re
import string
from price import get_ferry_prices  # Этот модуль должен возвращать данные с сайта тарифов
# Мы отключаем работу с Price.xlsx и Bible.xlsx, так как сейчас собираем данные только с сайта

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def extract_numeric(price_str):
    """
    Извлекает числовое значение из строки с ценой, удаляя лишние символы.
    Возвращает float или None, если преобразование невозможно.
    """
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    if cleaned.count(',') > 0 and cleaned.count('.') == 0:
        cleaned = cleaned.replace(',', '.')
    elif cleaned.count(',') > 0 and cleaned.count('.') > 0:
        cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None

def extract_vehicle_size(query):
    """
    Извлекает размер (число метров) из запроса.
    Например, "17 метров" или "17m" вернет число 17.
    """
    match = re.search(r'(\d{1,2})\s*(m|м|метр)', query.lower())
    if match:
        return int(match.group(1))
    return None

def normalize_text(text):
    """
    Приводит текст к нижнему регистру, удаляет пунктуацию и лишние пробелы.
    """
    text = text.lower()
    text = re.sub(f'[{re.escape(string.punctuation)}]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def select_vehicle_record(query, website_data):
    """
    Определяет, какой тариф из данных, полученных с сайта, подходит для запроса.
    Использует синонимы для грузовика и анализирует размер транспортного средства.
    Если в запросе упоминается "trailer", тариф должен содержать это слово.
    """
    synonyms = ['truck', 'грузовик', 'фура', 'еврофура', 'трайлер', 'трас']
    trailer_keywords = ['trailer', 'трейлер']
    query_norm = normalize_text(query)
    size = extract_vehicle_size(query)
    
    candidate = None
    best_score = 0
    for key in website_data.keys():
        key_norm = normalize_text(key)
        score = 0
        # Проверяем совпадение с синонимами
        for syn in synonyms:
            if syn in query_norm and syn in key_norm:
                score += 1
        # Если запрос содержит "trailer", тариф должен содержать его
        if any(t in query_norm for t in trailer_keywords):
            if any(t in key_norm for t in trailer_keywords):
                score += 1
            else:
                continue
        # Если в названии тарифа указан размер, сравниваем с размером из запроса
        size_match = re.search(r'(\d+)\s*(m|м)', key_norm)
        if size_match:
            max_size = int(size_match.group(1))
            if size is not None and size <= max_size:
                score += 1
            else:
                continue
        if score > best_score:
            best_score = score
            candidate = key
    logger.info(f"Выбран тариф: {candidate} для запроса: '{query_norm}', размер: {size}, score: {best_score}")
    return candidate

def check_ferry_price(query, direction="Ro_Ge"):
    """
    Функция получает данные с сайта (через get_ferry_prices()), выбирает нужный тариф
    на основе запроса и возвращает стоимость, как она записана в источнике.
    """
    try:
        website_data = get_ferry_prices()
        if not website_data:
            return "Ошибка получения данных с сайта тарифов."
        record_key = select_vehicle_record(query, website_data)
        if not record_key:
            return "Информация о тарифах для данного запроса отсутствует."
        
        tariff = website_data.get(record_key, {})
        price = tariff.get("price_Ro_Ge", "").strip()
        if price.upper() == "PRICE_QUERY":
            return f"Тариф для '{record_key}' недоступен."
        
        response_message = f"Стандартная цена для '{record_key}' составляет {price} евро."
        return response_message
    except Exception as e:
        logger.error(f"Ошибка при получении цены для запроса '{query}': {e}")
        return "Произошла ошибка при получении цены."

def get_price_response(vehicle_query, direction="Ro_Ge"):
    try:
        response = check_ferry_price(vehicle_query, direction)
        return response
    except Exception as e:
        logger.error(f"Ошибка при получении цены для '{vehicle_query}': {e}")
        return "Произошла ошибка при получении актуальной цены."

if __name__ == "__main__":
    test_query = "Standard truck with trailer (up to 17M)"
    message = check_ferry_price(test_query, direction="Ro_Ge")
    print(message)
