import requests
from bs4 import BeautifulSoup
import logging

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# URL тарифной страницы
TARIFF_URL = "https://e60shipping.com/en/32/static/tariff.html"

def get_ferry_prices():
    """
    Делает HTTP-запрос к странице тарифов и извлекает информацию из таблицы.
    Возвращает словарь вида:
      {
         "VehicleType1": {
             "price_Ro_Ge": "Цена для направления Romania -> Georgia",
             "price_Ge_Ro": "Цена для направления Georgia -> Romania",
             "remark": "Remark",
             "conditions": [ "Condition1 текст", "Condition2 текст", ... ]
         },
         ...
      }
    Если таблица не найдена или в ней нет данных, возвращает пустой словарь.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"
        }
        response = requests.get(TARIFF_URL, headers=headers)
        response.raise_for_status()
        logger.info(f"Запрос к тарифной странице выполнен успешно. Код ответа: {response.status_code}")
        html_text = response.text
        logger.info(f"Длина полученного HTML: {len(html_text)} символов")
    except Exception as e:
        logger.error(f"Ошибка при запросе к тарифной странице: {e}")
        return {}

    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Попытка найти таблицу тарифов
    table = soup.find('table')
    if not table:
        logger.error("Таблица тарифов не найдена на странице.")
        return {}
    
    rows = table.find_all('tr')
    if not rows or len(rows) < 2:
        logger.error("В таблице тарифов нет данных для обработки.")
        return {}
    
    prices = {}
    # Предполагается, что первая строка - заголовок, остальные - данные
    for row in rows[1:]:
        cols = row.find_all('td')
        if len(cols) < 4:
            logger.debug("Пропущена строка с недостаточным количеством столбцов.")
            continue
        vehicle_type = cols[0].get_text(strip=True)
        price_Ro_Ge = cols[1].get_text(strip=True)
        price_Ge_Ro = cols[2].get_text(strip=True)
        remark = cols[3].get_text(strip=True)
        conditions = []
        if len(cols) > 4:
            for col in cols[4:]:
                text = col.get_text(strip=True)
                if text:
                    conditions.append(text)
        prices[vehicle_type] = {
            "price_Ro_Ge": price_Ro_Ge,
            "price_Ge_Ro": price_Ge_Ro,
            "remark": remark,
            "conditions": conditions
        }
    
    logger.info(f"Извлечены тарифы: {prices}")
    return prices

if __name__ == "__main__":
    prices = get_ferry_prices()
    logger.info(f"Результат: {prices}")
