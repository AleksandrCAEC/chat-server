import os
import logging
import re
from price import get_ferry_prices  # Функция для получения тарифов с сайта

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
    сопоставляя извлечённую длину с пороговыми значениями, извлечёнными из названий категорий.
    Для каждой категории извлекается первое найденное число.
    Возвращает найденную категорию или None.
    """
    best_category = None
    best_threshold = None
    for category in website_prices:
        numbers = re.findall(r'\d+', category)
        if numbers:
            threshold = int(numbers[0])
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
      1. Извлекает длину из vehicle_description.
      2. Загружает тарифы с сайта.
      3. Находит категорию, соответствующую извлечённой длине.
      4. Если категория найдена, возвращает тариф, используя данные из website_prices.
         (Значения цены и remark полностью берутся из данных, полученных с сайта.)
      5. Если длина не указана, возвращает наводящий вопрос (если транспортное средство не относится к исключениям).
    """
    extracted_length = extract_length(vehicle_description)
    logger.debug(f"Из описания '{vehicle_description}' извлечена длина: {extracted_length}")
    
    # Список ключевых слов для транспортных средств, для которых длина не требуется
    exceptions = ["контейнер", "мини", "легков", "мото"]
    if extracted_length is None:
        if not any(keyword in vehicle_description.lower() for keyword in exceptions):
            return ("Пожалуйста, уточните длину вашего транспортного средства "
                    "(например, до 20, до 17, до 14, до 10 или до 8 метров).")
        else:
            return "Для данного типа транспортного средства длина не требуется для расчета тарифа."
    
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
    
    remark = website_prices[category].get("remark", "")
    
    response_message = f"Цена перевозки для категории '{category}' ({direction.replace('_', ' ')}) составляет {website_price}."
    if remark:
        response_message += f" Примечание: {remark}"
    logger.debug(f"Итоговый ответ: {response_message}")
    return response_message

# Для обратной совместимости с сервером назначаем check_ferry_price как обёртку для check_ferry_price_from_site.
check_ferry_price = check_ferry_price_from_site

def load_price_data():
    # Заглушка, так как на данный момент этот метод не используется.
    return {}

if __name__ == "__main__":
    sample_text = "Фура 17 метров, Констанца-Поти, без ADR, без груза"
    result_ro_ge = check_ferry_price(sample_text, direction="Ro_Ge")
    logger.info(f"Результат теста (Ro_Ge): {result_ro_ge}")
    
    result_ge_ro = check_ferry_price(sample_text, direction="Ge_Ro")
    logger.info(f"Результат теста (Ge_Ro): {result_ge_ro}")
