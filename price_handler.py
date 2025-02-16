import os
import logging
import re
from price import get_ferry_prices  # Функция для получения тарифов с сайта

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Словарь синонимов для типов транспортных средств.
# Если в запросе содержится "минивэн" или "minivan", тариф сразу будет определён как "Minivan"
TYPE_SYNONYMS = {
    "минивэн": "Minivan",
    "minivan": "Minivan",
    "фура": "Standard truck with trailer (up to 17M)",
    "грузовик": "Standard truck with trailer (up to 17M)",
    "еврофура": "Standard truck with trailer (up to 17M)",
    "тягач": "Standard truck with trailer (up to 17M)"
}

# Категории, для которых уточнение цены по двойному значению НЕ применяется (например, мотоциклы и контейнеры)
NON_TRUCK_CATEGORIES = {
    "Motorcycle",
    "Container 20’",
    "Container 40’",
    "Container ref 20’",
    "Container ref 40’",
    "Container ref 20’ with charge",
    "Container ref 40’ with charge"
}

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
    
    Сначала пытается найти число после фразы "up to" (без учета регистра);
    если такой шаблон не найден, используется первое найденное число.
    Сортирует категории по возрастанию порога и возвращает первую, для которой extracted_length <= порог.
    Возвращает найденную категорию или None.
    """
    categories_with_threshold = []
    for category in website_prices:
        match = re.search(r'up to (\d+)', category, re.IGNORECASE)
        if not match:
            match = re.search(r'(\d+)', category)
        if match:
            threshold = int(match.group(1))
            categories_with_threshold.append((category, threshold))
    if not categories_with_threshold:
        logger.debug("Не удалось извлечь пороговые значения ни из одной категории")
        return None
    sorted_categories = sorted(categories_with_threshold, key=lambda x: x[1])
    logger.debug(f"Отсортированные категории: {sorted_categories}")
    for category, threshold in sorted_categories:
        if extracted_length <= threshold:
            logger.debug(f"Выбрана категория '{category}' для длины {extracted_length} (порог {threshold})")
            return category
    logger.debug(f"Ни одна категория не удовлетворяет условию для длины {extracted_length}")
    return None

def check_ferry_price_from_site(vehicle_description, direction="Ro_Ge"):
    """
    Получает тариф с сайта, используя get_ferry_prices().
    
    Алгоритм:
      1. Загружает тарифы с сайта.
      2. Определяет тарифную категорию по синониму: если в описании встречается синоним из TYPE_SYNONYMS,
         используется соответствующий официальный термин.
      3. Если категория не определена, ищется совпадение по ключам тарифных данных.
      4. Если в запросе явно указана длина и выбранная категория не является "Minivan", тарифная категория переопределяется
         по значению длины через find_category_by_length.
      5. Если ни название, ни длина не позволяют однозначно определить категорию (для грузовиков),
         возвращается сообщение с просьбой уточнить данные.
      6. Если тарифная категория определена, извлекается активная цена для указанного направления и примечание.
         Для категорий, не входящих в NON_TRUCK_CATEGORIES, если активная цена содержит два значения,
         оставляется только второе (актуальное).
      7. Формируется итоговый ответ, который включает только активную цену и примечание.
    """
    try:
        website_prices = get_ferry_prices()
        logger.debug(f"Получены тарифы с сайта: {website_prices}")
    except Exception as e:
        logger.error(f"Ошибка при получении тарифов с сайта: {e}")
        return "Ошибка при получении тарифов с сайта."
    
    vehicle_lower = vehicle_description.lower()
    category = None

    # 1. Определение по синониму.
    for synonym, official in TYPE_SYNONYMS.items():
        if synonym in vehicle_lower:
            if official in website_prices:
                category = official
                logger.debug(f"Синоним '{synonym}' определил тарифную категорию: {category}")
                break

    # 2. Если по синониму не удалось, ищем совпадение по ключам.
    if category is None:
        for key in website_prices:
            if key.lower() in vehicle_lower:
                category = key
                logger.debug(f"Найденная категория по совпадению названия: {category}")
                break

    # 3. Если в запросе явно указана длина и выбранная категория не равна "Minivan", переопределяем категорию по длине.
    extracted_length = extract_length(vehicle_description)
    if extracted_length is not None and category != "Minivan":
        category_by_length = find_category_by_length(extracted_length, website_prices)
        if category_by_length is not None:
            if category != category_by_length:
                logger.debug(f"Переопределяем тарифную категорию с '{category}' на '{category_by_length}' на основе длины {extracted_length} метров")
            category = category_by_length
    elif extracted_length is None and category not in NON_TRUCK_CATEGORIES:
        return ("Пожалуйста, уточните длину вашего транспортного средства "
                "(например, до 20, до 17, до 14, до 10 или до 8 метров).")
    
    if category is None:
        return "Не удалось определить тарифную категорию по вашему запросу. Пожалуйста, уточните информацию о транспортном средстве."

    # 4. Извлекаем активную цену для выбранной категории в зависимости от направления.
    if direction == "Ro_Ge":
        active_price = website_prices[category].get("price_Ro_Ge", "")
    else:
        active_price = website_prices[category].get("price_Ge_Ro", "")
    
    # Если активная цена для категорий, не входящих в NON_TRUCK_CATEGORIES (т.е. для грузовиков),
    # содержит два значения, оставляем только второе.
    if category not in NON_TRUCK_CATEGORIES:
        prices_found = re.findall(r'(\d+)\s*\(EUR\)', active_price)
        if len(prices_found) > 1:
            # Берём второе значение.
            active_price = prices_found[1] + " (EUR)"
            logger.debug(f"Из активной цены выбрано второе значение: {active_price}")
    
    if not active_price:
        return "Актуальная цена для выбранной категории не получена. Пожалуйста, обратитесь к менеджеру."
    
    remark = website_prices[category].get("remark", "")
    
    # 5. Формирование итогового ответа.
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
    # Тестовый пример 1: Фура с указанием длины
    sample_text1 = "Фура 17 метров, Констанца-Поти, без ADR, без груза"
    result_ro_ge = check_ferry_price(sample_text1, direction="Ro_Ge")
    logger.info(f"Результат теста (Ro_Ge): {result_ro_ge}")
    
    result_ge_ro = check_ferry_price(sample_text1, direction="Ge_Ro")
    logger.info(f"Результат теста (Ge_Ro): {result_ge_ro}")
    
    # Тестовый пример 2: Минивэн без указания длины (для минивэнов длина не учитывается)
    sample_text2 = "Минивэн"
    result_minivan = check_ferry_price(sample_text2, direction="Ge_Ro")
    logger.info(f"Результат теста для минивэна: {result_minivan}")
    
    # Тестовый пример 3: Грузовик 15 метров, из Поти в Констанца
    sample_text3 = "Грузовик 15 метров, из Поти в Констанца"
    result_truck = check_ferry_price(sample_text3, direction="Ge_Ro")
    logger.info(f"Результат теста для грузовика 15 метров (Ge_Ro): {result_truck}")
    
    # Тестовый пример 4: Грузовик 10 метров, из Поти в Констанца
    sample_text4 = "Грузовик 10 метров, из Поти в Констанца"
    result_truck10 = check_ferry_price(sample_text4, direction="Ge_Ro")
    logger.info(f"Результат теста для грузовика 10 метров (Ge_Ro): {result_truck10}")
    
    # Тестовый пример 5: Грузовик 8 метров, из Ro_Ge запроса (ожидается категория для 8 метров, например, "Mini truck (up to 8M)")
    sample_text5 = "Грузовик 8 метров"
    result_truck8 = check_ferry_price(sample_text5, direction="Ro_Ge")
    logger.info(f"Результат теста для грузовика 8 метров (Ro_Ge): {result_truck8}")
