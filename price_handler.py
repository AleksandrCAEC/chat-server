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
    Находит тарифную категорию в данных website_prices, сопоставляя извлечённую длину с пороговыми значениями,
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
    logger.debug(f"Найденная категория: {best_category} для длины {extracted_length}")
    return best_category

def check_ferry_price_from_site(vehicle_description, direction="Ro_Ge"):
    """
    Получает тариф исключительно с сайта, используя get_ferry_prices() из файла price.py.
    
    Алгоритм:
      1. Пытаемся извлечь длину из vehicle_description.
      2. Если длина указана, используем её для определения тарифной категории через find_category_by_length.
      3. Если длина не указана, то:
           - Если описание содержит ключевые слова для типов ТС, для которых длина не требуется 
             (например, "минивэн", "легков", "мото", "контейнер"),
             пытаемся найти тарифную категорию по совпадению этих ключевых слов с названиями категорий.
           - Если совпадение не найдено, возвращаем сообщение о недоступности тарифа.
           - Если описание не содержит таких ключевых слов, просим уточнить длину.
      4. Если тарифная категория найдена, извлекаем активное значение (и, при наличии, зачёркнутое значение) цены для указанного направления, а также примечание – всё из внешнего источника.
      5. Формируем итоговый ответ.
    """
    extracted_length = extract_length(vehicle_description)
    logger.debug(f"Из описания '{vehicle_description}' извлечена длина: {extracted_length}")
    
    try:
        website_prices = get_ferry_prices()
        logger.debug(f"Получены тарифы с сайта: {website_prices}")
    except Exception as e:
        logger.error(f"Ошибка при получении тарифов с сайта: {e}")
        return "Ошибка при получении тарифов с сайта."
    
    category = None
    if extracted_length is not None:
        category = find_category_by_length(extracted_length, website_prices)
    else:
        # Если длина не указана, пробуем найти тариф по ключевым словам в описании.
        # Список ключевых слов для ТС, для которых длина не требуется:
        exceptions = ["контейнер", "минивэн", "легков", "мото"]
        for keyword in exceptions:
            if keyword in vehicle_description.lower():
                # Попытаемся найти тарифную категорию, где ключевое слово встречается в названии
                for key in website_prices:
                    if keyword in key.lower():
                        category = key
                        logger.debug(f"Найденная категория по ключевому слову '{keyword}': {category}")
                        break
                if category:
                    break

    if category is None:
        if extracted_length is None:
            return ("Пожалуйста, уточните длину вашего транспортного средства "
                    "(например, до 20, до 17, до 14, до 10 или до 8 метров).")
        else:
            return f"Не найдена тарифная категория для транспортного средства длиной {extracted_length} метров."
    
    # Извлекаем активное и (опционально) старое значения цены в зависимости от направления
    if direction == "Ro_Ge":
        active_price = website_prices[category].get("price_Ro_Ge", "")
        old_price = website_prices[category].get("old_price_Ro_Ge", "")
    else:
        active_price = website_prices[category].get("price_Ge_Ro", "")
        old_price = website_prices[category].get("old_price_Ge_Ro", "")
    
    if not active_price:
        return "Цена для выбранной категории не получена."
    
    remark = website_prices[category].get("remark", "")
    
    # Формируем итоговый ответ.
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
    # Тестовый пример для фуры с указанной длиной
    sample_text1 = "Фура 17 метров, Констанца-Поти, без ADR, без груза"
    result_ro_ge = check_ferry_price(sample_text1, direction="Ro_Ge")
    logger.info(f"Результат теста (Ro_Ge): {result_ro_ge}")
    
    result_ge_ro = check_ferry_price(sample_text1, direction="Ge_Ro")
    logger.info(f"Результат теста (Ge_Ro): {result_ge_ro}")
    
    # Тестовый пример для минивэна (без указания длины)
    sample_text2 = "Минивэн, Констанца-Поти"
    result_minivan = check_ferry_price(sample_text2, direction="Ro_Ge")
    logger.info(f"Результат теста для минивэна: {result_minivan}")
