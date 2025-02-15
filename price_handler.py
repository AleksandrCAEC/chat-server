import os
import logging
import re
from price import get_ferry_prices  # Импортируем функцию для получения тарифов с сайта
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Функции для извлечения длины и определения категории транспортного средства ---

def extract_length(text):
    """
    Извлекает числовое значение длины (в метрах) из текста.
    Возвращает число или None, если длина не найдена.
    """
    match = re.search(r'(\d+)\s*(м|метров)', text.lower())
    if match:
        return int(match.group(1))
    return None

def determine_vehicle_category(length):
    """
    Определяет категорию транспортного средства на основе длины.
    Допустимые диапазоны:
      - Если длина >17 и <=20, возвращается "Road Train (up to 20 M)"
      - Если длина <=17 и >14, возвращается "Standard truck with trailer (up to 17M)"
      - Если длина <=14 и >10, возвращается "Trailer (up to 14 m)"
      - Если длина <=10 и >8, возвращается "Truck (up to 10M)"
      - Если длина <=8, возвращается "Mini truck (up to 8M)"
    Если длина не попадает ни в один диапазон, возвращается None.
    """
    if length is None:
        return None
    if length > 17 and length <= 20:
        return "Road Train (up to 20 M)"
    elif length <= 17 and length > 14:
        return "Standard truck with trailer (up to 17M)"
    elif length <= 14 and length > 10:
        return "Trailer (up to 14 m)"
    elif length <= 10 and length > 8:
        return "Truck (up to 10M)"
    elif length <= 8:
        return "Mini truck (up to 8M)"
    return None

# --- Функция для получения цены с сайта (без использования данных из price.xlsx) ---

def check_ferry_price_from_site(vehicle_category, direction="Ro_Ge"):
    """
    Получает тариф исключительно с сайта, используя get_ferry_prices() из файла price.py.
    
    direction: 
      - "Ro_Ge" для направления Romania -> Georgia,
      - "Ge_Ro" для направления Georgia -> Romania.
    
    Логика:
      1. Получаем актуальные тарифы с сайта.
      2. Если для заданного типа транспортного средства данные отсутствуют, возвращаем сообщение об отсутствии данных.
      3. Иначе возвращаем цену с сайта (приоритетное значение).
    """
    try:
        website_prices = get_ferry_prices()
        
        if vehicle_category not in website_prices:
            return f"Извините, тариф для '{vehicle_category}' не найден на сайте."
        
        if direction == "Ro_Ge":
            website_price = website_prices[vehicle_category].get("price_Ro_Ge", "")
        else:
            website_price = website_prices[vehicle_category].get("price_Ge_Ro", "")
        
        response_message = f"Цена перевозки для '{vehicle_category}' ({direction.replace('_', ' ')}) составляет {website_price}."
        if website_prices[vehicle_category].get("remark"):
            response_message += f" Примечание: {website_prices[vehicle_category]['remark']}"
        return response_message
    except Exception as e:
        logger.error(f"Ошибка при получении цены с сайта: {e}")
        return "Произошла ошибка при получении цены с сайта. Пожалуйста, попробуйте позже."

# --- Пример тестирования логики в режиме отладки ---
if __name__ == "__main__":
    sample_text = "Фура 17 метров, Констанца-Поти, без ADR, без водителя"
    length = extract_length(sample_text)
    if length is None:
        print("Пожалуйста, уточните длину вашего транспортного средства (например, до 20, до 17, до 14, до 10 или до 8 метров).")
    else:
        vehicle_category = determine_vehicle_category(length)
        if vehicle_category:
            print(f"Определена категория: {vehicle_category}")
            price_info = check_ferry_price_from_site(vehicle_category, direction="Ro_Ge")
            print(price_info)
        else:
            print("Не удалось определить категорию по длине. Пожалуйста, уточните параметры транспортного средства.")
