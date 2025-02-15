import os
import logging
import re
from price import get_ferry_prices  # Функция для получения тарифов с сайта

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def extract_length(text):
    """
    Извлекает числовое значение длины (в метрах) из текста.
    Возвращает число или None, если длина не найдена.
    """
    match = re.search(r'(\d+)\s*(м|метров)', text.lower())
    if match:
        length = int(match.group(1))
        logger.debug(f"Извлечена длина: {length} метров из текста: '{text}'")
        return length
    logger.debug(f"Не удалось извлечь длину из текста: '{text}'")
    return None

def find_category_by_length(extracted_length, website_prices):
    """
    Находит категорию транспортного средства в данных website_prices,
    сопоставляя извлечённую длину с пороговыми значениями в имени категории.
    Ожидается, что имена категорий содержат подстроку вида "up to <число>".
    Возвращает найденную категорию или None.
    """
    logger.debug(f"Попытка сопоставления длины {extracted_length} с тарифными категориями:")
    logger.debug(f"Доступные категории: {list(website_prices.keys())}")
    best_category = None
    best_threshold = None
    for category in website_prices:
        m = re.search(r'up to\s*(\d+)', category, re.IGNORECASE)
        if m:
            threshold = int(m.group(1))
            logger.debug(f"Категория '{category}' имеет порог {threshold}")
            if extracted_length <= threshold:
                if best_threshold is None or threshold < best_threshold:
                    best_threshold = threshold
                    best_category = category
    logger.debug(f"Найденная категория: {best_category} для длины {extracted_length}")
    return best_category

def check_ferry_price_from_site(vehicle_description, direction="Ro_Ge"):
    """
    Получает тариф исключительно с сайта, используя get_ferry_prices() из файла price.py.
    
    Шаги:
      1. Извлекаем длину из vehicle_description.
      2. Загружаем тарифы с сайта.
      3. Находим категорию, соответствующую извлечённой длине.
      4. Если категория найдена, возвращаем цену из данных сайта.
      5. Если не найдена, возвращаем сообщение об отсутствии данных.
    """
    extracted_length = extract_length(vehicle_description)
    logger.debug(f"Из описания '{vehicle_description}' извлечена длина: {extracted_length}")
    if extracted_length is None:
        return "Пожалуйста, уточните длину вашего транспортного средства (например, 17 метров)."
    
    try:
        website_prices = get_ferry_prices()
        logger.debug(f"Получены тарифы с сайта: {website_prices}")
    except Exception as e:
        logger.error(f"Ошибка при получении тарифов с сайта: {e}")
        return "Ошибка при получении тарифов с сайта."
    
    category = find_category_by_length(extracted_length, website_prices)
    if category is None:
        return f"Не найдена тарифная категория для транспортного средства длиной {extracted_length} метров."
    
    if direction == "Ro_Ge":
        website_price = website_prices[category].get("price_Ro_Ge", "")
    else:
        website_price = website_prices[category].get("price_Ge_Ro", "")
    
    response_message = f"Цена перевозки для категории '{category}' ({direction.replace('_', ' ')}) составляет {website_price}."
    if website_prices[category].get("remark"):
        response_message += f" Примечание: {website_prices[category]['remark']}"
    logger.debug(f"Итоговый ответ: {response_message}")
    return response_message

# Для обратной совместимости с сервером назначаем check_ferry_price как обёртку для check_ferry_price_from_site.
check_ferry_price = check_ferry_price_from_site

def load_price_data():
    # Заглушка, так как на данный момент мы не используем этот метод.
    return {}

if __name__ == "__main__":
    sample_text = "Фура 17 метров, Констанца-Поти, без ADR, без водителя"
    result = check_ferry_price(sample_text, direction="Ro_Ge")
    logger.info(f"Результат теста: {result}")
