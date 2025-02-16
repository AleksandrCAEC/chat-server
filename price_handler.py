import os
import logging
import re
from price import get_ferry_prices  # Функция для получения тарифов с сайта

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Словарь синонимов для типов транспортных средств.
# Ключи – варианты, которые может ввести клиент (в нижнем регистре),
# значения – официальный термин, используемый в тарифных данных.
TYPE_SYNONYMS = {
    "минивэн": "Minivan",
    "minivan": "Minivan",
    "фура": "Standard truck with trailer (up to 17M)",
    "грузовик": "Standard truck with trailer (up to 17M)",
    "еврофура": "Standard truck with trailer (up to 17M)",
    "тягач": "Standard truck with trailer (up to 17M)"
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
      2. Сначала пытается определить тарифную категорию по названию транспортного средства:
         – Если в описании встречается синоним из TYPE_SYNONYMS, преобразует его в официальный термин и,
           если он присутствует в тарифных данных, использует его.
      3. Если по названию тариф не найден, пытается извлечь длину из vehicle_description
         и определяет категорию через find_category_by_length.
      4. Если ни название, ни длина не позволяют однозначно определить категорию, возвращается запрос на уточнение.
      5. Если тарифная категория определена, извлекаются активная цена (и, если есть, зачёркнутая цена)
         и примечание для указанного направления – данные полностью поднимаются из источника.
      6. Формируется итоговый ответ.
    """
    try:
        website_prices = get_ferry_prices()
        logger.debug(f"Получены тарифы с сайта: {website_prices}")
    except Exception as e:
        logger.error(f"Ошибка при получении тарифов с сайта: {e}")
        return "Ошибка при получении тарифов с сайта."
    
    vehicle_lower = vehicle_description.lower()
    category = None

    # 1. Попытка определить тариф по синониму
    for synonym, official in TYPE_SYNONYMS.items():
        if synonym in vehicle_lower:
            if official in website_prices:
                category = official
                logger.debug(f"Синоним '{synonym}' определил тарифную категорию: {category}")
                break

    # 2. Если по синониму не найдено, пробуем определить тариф по совпадению ключей из website_prices
    if category is None:
        for key in website_prices:
            if key.lower() in vehicle_lower:
                category = key
                logger.debug(f"Найденная категория по совпадению названия: {category}")
                break

    # 3. Если и по названию не удалось определить, пытаемся извлечь длину
    if category is None:
        extracted_length = extract_length(vehicle_description)
        logger.debug(f"Из описания '{vehicle_description}' извлечена длина: {extracted_length}")
        if extracted_length is not None:
            category = find_category_by_length(extracted_length, website_prices)
        else:
            return ("Пожалуйста, уточните длину вашего транспортного средства "
                    "(например, до 20, до 17, до 14, до 10 или до 8 метров).")
    
    if category is None:
        return "Не удалось определить тарифную категорию по вашему запросу. Пожалуйста, уточните информацию о транспортном средстве."

    # 4. Извлекаем цены для выбранной категории в зависимости от направления
    if direction == "Ro_Ge":
        active_price = website_prices[category].get("price_Ro_Ge", "")
        old_price = website_prices[category].get("old_price_Ro_Ge", "")
    else:
        active_price = website_prices[category].get("price_Ge_Ro", "")
        old_price = website_prices[category].get("old_price_Ge_Ro", "")
    
    if not active_price:
        return "Цена для выбранной категории не получена."
    
    remark = website_prices[category].get("remark", "")
    
    # 5. Формируем итоговый ответ
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
    # Тестовый пример 1: Фура с указанием длины
    sample_text1 = "Фура 17 метров, Констанца-Поти, без ADR, без груза"
    result_ro_ge = check_ferry_price(sample_text1, direction="Ro_Ge")
    logger.info(f"Результат теста (Ro_Ge): {result_ro_ge}")
    
    result_ge_ro = check_ferry_price(sample_text1, direction="Ge_Ro")
    logger.info(f"Результат теста (Ge_Ro): {result_ge_ro}")
    
    # Тестовый пример 2: Минивэн без указания длины
    sample_text2 = "Минивэн"
    result_minivan = check_ferry_price(sample_text2, direction="Ge_Ro")
    logger.info(f"Результат теста для минивэна: {result_minivan}")
    
    # Тестовый пример 3: Грузовик с длиной
    sample_text3 = "Грузовик 15 метров, из Поти в Констанца"
    result_truck = check_ferry_price(sample_text3, direction="Ge_Ro")
    logger.info(f"Результат теста для грузовика 15 метров (Ge_Ro): {result_truck}")
