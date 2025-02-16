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
    Находит тарифную категорию, сопоставляя извлечённую длину с пороговыми значениями,
    извлечёнными из названий тарифных категорий.
    Из каждого названия извлекается первое найденное число, которое считается порогом.
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
    logger.debug(f"Найденная категория по длине: {best_category} для длины {extracted_length}")
    return best_category

def check_ferry_price_from_site(vehicle_description, direction="Ro_Ge"):
    """
    Получает тариф исключительно с сайта, используя get_ferry_prices() из файла price.py.
    
    Алгоритм:
      1. Загружает тарифы с сайта.
      2. Пытается определить тарифную категорию по названию транспортного средства.
         Если в описании (vehicle_description) встречается слово, совпадающее (без учета регистра)
         с одним из ключей в website_prices, категория определяется на основании названия.
      3. Если по названию тариф не найден, пытается извлечь длину из vehicle_description.
         Если длина найдена, выбирается категория по диапазону с помощью find_category_by_length.
      4. Если ни название, ни длина не позволяют определить категорию, возвращается запрос на уточнение.
      5. Если тарифная категория определена, извлекаются активная цена (и, если есть, зачёркнутая цена)
         для выбранного направления, а также примечание.
      6. Формируется итоговый ответ.
    """
    try:
        website_prices = get_ferry_prices()
        logger.debug(f"Получены тарифы с сайта: {website_prices}")
    except Exception as e:
        logger.error(f"Ошибка при получении тарифов с сайта: {e}")
        return "Ошибка при получении тарифов с сайта."
    
    # 1. Попытка определить категорию по названию транспортного средства.
    category_by_name = None
    for key in website_prices:
        if key.lower() in vehicle_description.lower():
            category_by_name = key
            logger.debug(f"Найденная категория по названию: {category_by_name}")
            break

    if category_by_name:
        category = category_by_name
    else:
        # 2. Если по названию не найдено, пытаемся извлечь длину.
        extracted_length = extract_length(vehicle_description)
        logger.debug(f"Из описания '{vehicle_description}' извлечена длина: {extracted_length}")
        if extracted_length is not None:
            category = find_category_by_length(extracted_length, website_prices)
        else:
            # 3. Если длина не указана, и по названию тариф не определён.
            # Список типов, для которых длина не требуется:
            exceptions = ["контейнер", "минивэн", "легков", "мото"]
            if not any(keyword in vehicle_description.lower() for keyword in exceptions):
                return ("Пожалуйста, уточните длину вашего транспортного средства "
                        "(например, до 20, до 17, до 14, до 10 или до 8 метров).")
            else:
                # Если описание относится к типам, для которых длина не требуется,
                # пытаемся найти категорию по совпадению ключевых слов в тарифах.
                for key in website_prices:
                    for keyword in exceptions:
                        if keyword in key.lower() or keyword in vehicle_description.lower():
                            category = key
                            logger.debug(f"Найденная категория по исключающему слову '{keyword}': {category}")
                            break
                    if category:
                        break
                if category is None:
                    return "Для данного типа транспортного средства тарифные данные не найдены."

    if category is None:
        return "Не удалось определить тарифную категорию по вашему запросу. Пожалуйста, уточните информацию о транспортном средстве."

    # Извлекаем цены для выбранной категории в зависимости от направления
    if direction == "Ro_Ge":
        active_price = website_prices[category].get("price_Ro_Ge", "")
        old_price = website_prices[category].get("old_price_Ro_Ge", "")
    else:
        active_price = website_prices[category].get("price_Ge_Ro", "")
        old_price = website_prices[category].get("old_price_Ge_Ro", "")
    
    if not active_price:
        return "Цена для выбранной категории не получена."
    
    remark = website_prices[category].get("remark", "")
    
    # Формирование итогового ответа
    if old_price:
        response_message = (f"Цена перевозки для категории '{category}' ({direction.replace('_', ' ')}) составляет "
                            f"{active_price} (предложение), предыдущая цена: {old_price} (зачёрнуто).")
    else:
        response_message = f"Цена перевозки для категории '{category}' ({direction.replace('_', ' ')}) составляет {active_price}."
    
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
    # Тестовый пример 1: Клиент указывает "Фура 17 метров, Констанца-Поти, без ADR, без груза"
    sample_text1 = "Фура 17 метров, Констанца-Поти, без ADR, без груза"
    result_ro_ge = check_ferry_price(sample_text1, direction="Ro_Ge")
    logger.info(f"Результат теста (Ro_Ge): {result_ro_ge}")
    
    result_ge_ro = check_ferry_price(sample_text1, direction="Ge_Ro")
    logger.info(f"Результат теста (Ge_Ro): {result_ge_ro}")
    
    # Тестовый пример 2: Клиент указывает "Минивэн" без указания длины
    sample_text2 = "Минивэн"
    result_minivan = check_ferry_price(sample_text2, direction="Ro_Ge")
    logger.info(f"Результат теста для минивэна: {result_minivan}")
    
    # Тестовый пример 3: Клиент указывает "Грузовик 15 метров, из Поти в Констанца"
    sample_text3 = "Грузовик 15 метров, из Поти в Констанца"
    result_truck = check_ferry_price(sample_text3, direction="Ge_Ro")
    logger.info(f"Результат теста для грузовика 15 метров (Ge_Ro): {result_truck}")
