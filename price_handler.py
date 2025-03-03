import os
import logging
import re
from price import get_ferry_prices  # функция для получения тарифов с сайта

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Словарь синонимов для типов транспортных средств.
# Например, если в запросе встречается "минивэн" или "minivan", будет использован термин "Minivan"
TYPE_SYNONYMS = {
    "минивэн": "Minivan",
    "minivan": "Minivan",
    "фура": "Standard truck with trailer (up to 17M)",
    "грузовик": "Standard truck with trailer (up to 17M)",
    "еврофура": "Standard truck with trailer (up to 17M)",
    "тягач": "Standard truck with trailer (up to 17M)"
}

# Категории, для которых не применяется логика выбора второго значения цены (не грузовики)
NON_TRUCK_CATEGORIES = {
    "Motorcycle",
    "Car",
    "Minivan",
    "Container 20’",
    "Container 40’",
    "Container ref 20’",
    "Container ref 40’"
}

def extract_length(text):
    """
    Извлекает числовое значение длины (в метрах) из текста.
    Возвращает число или None, если длина не найдена.
    """
    match = re.search(r'(\d+)\s*(м|метр)', text.lower())
    if match:
        length = int(match.group(1))
        logger.debug(f"Извлечена длина: {length} м из текста: '{text}'")
        return length
    logger.debug(f"Не удалось извлечь длину из текста: '{text}'")
    return None

def find_category_by_length(extracted_length, website_prices):
    """
    Находит тарифную категорию, сопоставляя извлечённую длину с пороговыми значениями,
    извлечёнными из названий тарифных категорий.
    Возвращает название подходящей категории или None.
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
    logger.debug(f"Отсортированные категории по длине: {sorted_categories}")
    for category, threshold in sorted_categories:
        if extracted_length <= threshold:
            logger.debug(f"Выбрана категория '{category}' для длины {extracted_length} (порог {threshold})")
            return category
    logger.debug(f"Ни одна категория не удовлетворяет длине {extracted_length}")
    return None

# Инициализация морфологического анализатора для русского языка (если доступен)
try:
    import pymorphy2
    morph = pymorphy2.MorphAnalyzer()
    logger.info("pymorphy2 инициализирован для лемматизации.")
except Exception as e:
    morph = None
    logger.warning(f"pymorphy2 недоступен, лемматизация будет ограниченной: {e}")

def check_ferry_price_from_site(vehicle_description, direction="Ro_Ge"):
    """
    Получает актуальный тариф с сайта для указанного описания ТС (vehicle_description).
    Алгоритм:
      1. Загружает тарифы с сайта.
      2. Определяет тарифную категорию по синонимам: если в описании найден ключ из TYPE_SYNONYMS,
         используется соответствующий официальный термин.
      3. Если категория не определена по синонимам, ищется совпадение по названиям категорий тарифов.
      4. Если указана длина и выбранная категория не "Minivan", категория уточняется по длине через find_category_by_length.
      5. Если не удалось однозначно определить категорию (для грузовых ТС без длины), возвращается запрос указать длину.
      6. Если категория определена, извлекается актуальная цена и примечание для нужного направления.
         Для грузовых категорий (не в NON_TRUCK_CATEGORIES), если указано два значения цен, берётся второе (актуальное).
      7. Формируется итоговый ответ с ценой и примечанием.
    """
    logger.debug(f"Checking ferry price for query: '{vehicle_description}', direction: {direction}")
    try:
        website_prices = get_ferry_prices()
        logger.debug(f"Получены тарифы с сайта: {list(website_prices.keys())}")
    except Exception as e:
        logger.error(f"Ошибка при получении тарифов с сайта: {e}")
        return "Ошибка при получении тарифов с сайта."

    vehicle_lower = vehicle_description.lower()
    # Нормализация текста ТС: замена сокращений и лемматизация
    vehicle_norm = re.sub(r'\bавто\b', 'автомобиль', vehicle_lower)
    if morph:
        tokens = re.findall(r'\w+', vehicle_norm)
        lemmas = [morph.parse(word)[0].normal_form for word in tokens]
        vehicle_norm = " ".join(lemmas)
    logger.debug(f"Normalized vehicle description for matching: '{vehicle_lower}' -> '{vehicle_norm}'")

    category = None

    # 1. Определение категории по словарю синонимов
    for synonym, official in TYPE_SYNONYMS.items():
        if synonym in vehicle_lower or synonym in vehicle_norm:
            if official in website_prices:
                category = official
                logger.debug(f"Синоним '{synonym}' определил категорию: {category}")
                break
            else:
                logger.warning(f"Синоним '{synonym}' -> '{official}', но эта категория не найдена среди тарифов сайта")
    # 2. Если по синонимам не удалось определить
    if category is None:
        for key in website_prices:
            if key.lower() in vehicle_lower:
                category = key
                logger.debug(f"Категория определена по названию: {category}")
                break

    # 3. Обработка длины (если указана в тексте и категория != Minivan)
    extracted_length = extract_length(vehicle_description)
    if extracted_length is not None and category != "Minivan":
        category_by_length = find_category_by_length(extracted_length, website_prices)
        if category_by_length is not None:
            if category != category_by_length:
                logger.debug(f"Меняем категорию с '{category}' на '{category_by_length}' по длине {extracted_length}м")
            category = category_by_length
    elif extracted_length is None and category is not None and category not in NON_TRUCK_CATEGORIES:
        # Если категория — грузовая, а длина не указана, запрашиваем уточнение
        return ("Пожалуйста, уточните длину вашего транспортного средства "
                "(например, до 20, до 17, до 14, до 10 или до 8 метров).")

    if category is None:
        # Не удалось определить даже после всех попыток
        return "Не удалось определить тарифную категорию по вашему запросу. Пожалуйста, уточните информацию о транспортном средстве."

    # 4. Извлечение актуальной цены для выбранной категории и направления
    if direction == "Ro_Ge":
        active_price = website_prices[category].get("price_Ro_Ge", "")
    else:
        active_price = website_prices[category].get("price_Ge_Ro", "")

    # Если для грузовых категорий указаны две цены (в скобках), берём вторую как актуальную
    if category not in NON_TRUCK_CATEGORIES:
        prices_found = re.findall(r'(\d+)\s*\(EUR\)', active_price)
        if len(prices_found) > 1:
            active_price = prices_found[1] + " (EUR)"
            logger.debug(f"Для категории грузовика выбрано второе значение цены: {active_price}")

    if not active_price:
        return "Актуальная цена для выбранной категории не получена. Пожалуйста, обратитесь к менеджеру."

    remark = website_prices[category].get("remark", "")

    # 5. Формирование итогового ответа
    response_message = f"Цена перевозки для категории '{category}' ({direction.replace('_', ' ')}) составляет {active_price}."
    if remark:
        response_message += f" Примечание: {remark}"
    logger.debug(f"Итоговый ответ: {response_message}")
    return response_message

# Для совместимости: основная функция обращения
check_ferry_price = check_ferry_price_from_site

def load_price_data():
    # На данный момент локальные данные не используются
    return {}

if __name__ == "__main__":
    # Примеры тестовых запросов
    sample_text1 = "Фура 17 метров, Констанца-Поти, без ADR, без груза"
    result_ro_ge = check_ferry_price(sample_text1, direction="Ro_Ge")
    logger.info(f"Результат теста (Ro_Ge): {result_ro_ge}")
    result_ge_ro = check_ferry_price(sample_text1, direction="Ge_Ro")
    logger.info(f"Результат теста (Ge_Ro): {result_ge_ro}")

    sample_text2 = "Минивэн"
    result_minivan = check_ferry_price(sample_text2, direction="Ge_Ro")
    logger.info(f"Результат теста для минивэна: {result_minivan}")

    sample_text3 = "Грузовик 15 метров, из Поти в Констанца"
    result_truck = check_ferry_price(sample_text3, direction="Ge_Ro")
    logger.info(f"Результат теста для грузовика 15 метров (Ge_Ro): {result_truck}")

    sample_text4 = "Грузовик 10 метров, из Поти в Констанца"
    result_truck10 = check_ferry_price(sample_text4, direction="Ge_Ro")
    logger.info(f"Результат теста для грузовика 10 метров (Ge_Ro): {result_truck10}")

    # Новый тестовый пример: легковое авто (без длины)
    sample_text5 = "Сколько стоит легковое авто"
    result_car = check_ferry_price(sample_text5, direction="Ro_Ge")
    logger.info(f"Результат теста для легкового авто: {result_car}")
