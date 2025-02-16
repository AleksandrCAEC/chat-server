import os
import logging
import re
from price import get_ferry_prices  # Функция для получения тарифов с сайта

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Словарь синонимов для типов транспортных средств.
# Здесь указываются варианты, которые может ввести клиент (в нижнем регистре),
# а значения – официальный термин, который используется в тарифных данных.
# Обратите внимание: если в запросе присутствует явная информация о длине, то выбор тарифа будет переопределён.
TYPE_SYNONYMS = {
    "минивэн": "Minivan",
    "minivan": "Minivan",
    # Для грузовика оставляем общий синоним, но если длина указана, то логика подберёт более узкую категорию
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
    Для каждой категории извлекается первое найденное число, которое считается порогом.
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
         если в описании встречается синоним из TYPE_SYNONYMS, преобразует его в официальный термин и,
         если этот термин присутствует в тарифных данных, используется для определения тарифа.
      3. Если по названию тариф не найден, пытается извлечь длину из vehicle_description
         и определить категорию через find_category_by_length.
      4. Если ни название, ни длина не позволяют однозначно определить категорию, возвращается запрос на уточнение длины.
      5. Если тарифная категория определена, извлекается активное значение цены для указанного направления и примечание.
         Если активная цена содержит маркер "PRICE_QUERY", возвращается сообщение об отсутствии актуальной цены.
      6. Формируется итоговый ответ, который включает только активное значение цены и примечание.
      
      **Доработка по грузовику:**  
      Если в запросе присутствует слово "грузовик" или "truck" и извлеченная длина меньше или равна 8, то даже если синоним
      вернул "Standard truck with trailer (up to 17M)", функция попытается найти категорию по длине, которая, как правило,
      будет "Mini truck (up to 8M)".
    """
    try:
        website_prices = get_ferry_prices()
        logger.debug(f"Получены тарифы с сайта: {website_prices}")
    except Exception as e:
        logger.error(f"Ошибка при получении тарифов с сайта: {e}")
        return "Ошибка при получении тарифов с сайта."
    
    vehicle_lower = vehicle_description.lower()
    category = None

    # 1. Попытка определить тарифную категорию по синониму.
    for synonym, official in TYPE_SYNONYMS.items():
        if synonym in vehicle_lower:
            if official in website_prices:
                category = official
                logger.debug(f"Синоним '{synonym}' определил тарифную категорию: {category}")
                break

    # 2. Если по синониму не удалось, ищем совпадение по ключам тарифных данных.
    if category is None:
        for key in website_prices:
            if key.lower() in vehicle_lower:
                category = key
                logger.debug(f"Найденная категория по совпадению названия: {category}")
                break

    # 3. Если информация о длине присутствует, используем её для уточнения тарифной категории.
    extracted_length = extract_length(vehicle_description)
    if extracted_length is not None:
        category_by_length = find_category_by_length(extracted_length, website_prices)
        if category_by_length is not None:
            # Если категория, определённая по длине, отличается от найденной по синониму,
            # используем категорию по длине, так как она более специфична.
            if category is None or (category_by_length != category):
                logger.debug(f"Переопределяем тарифную категорию с '{category}' на '{category_by_length}' на основе длины {extracted_length} метров")
                category = category_by_length

    # 4. Если ни по названию, ни по длине не удалось определить категорию, просим уточнить длину.
    if category is None:
        return ("Пожалуйста, уточните длину вашего транспортного средства "
                "(например, до 20, до 17, до 14, до 10 или до 8 метров).")
    
    # 5. Извлекаем активное значение цены для выбранной категории в зависимости от направления.
    if direction == "Ro_Ge":
        active_price = website_prices[category].get("price_Ro_Ge", "")
    else:
        active_price = website_prices[category].get("price_Ge_Ro", "")
    
    active_price_clean = active_price.strip().upper()
    if not active_price or "PRICE_QUERY" in active_price_clean:
        return "Актуальная цена для выбранной категории не получена. Пожалуйста, обратитесь к менеджеру."
    
    remark = website_prices[category].get("remark", "")
    
    # 6. Формируем итоговый ответ (выводим только активную цену и примечание).
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
    
    # Тестовый пример 3: Грузовик 15 метров, из Поти в Констанца
    sample_text3 = "Грузовик 15 метров, из Поти в Констанца"
    result_truck = check_ferry_price(sample_text3, direction="Ge_Ro")
    logger.info(f"Результат теста для грузовика 15 метров (Ge_Ro): {result_truck}")
    
    # Тестовый пример 4: Грузовик 8 метров, из Ro_Ge запроса
    sample_text4 = "Грузовик 8 метров"
    result_truck8 = check_ferry_price(sample_text4, direction="Ro_Ge")
    logger.info(f"Результат теста для грузовика 8 метров (Ro_Ge): {result_truck8}")
