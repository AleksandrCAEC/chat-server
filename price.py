import requests
from bs4 import BeautifulSoup
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TARIFF_URL = "https://e60shipping.com/en/32/static/tariff.html"

def get_ferry_prices():
    """
    Делает HTTP-запрос к странице тарифов паромного сервиса и извлекает информацию о ценах.
    Возвращает словарь вида:
    {
        "VehicleType1": {
            "price_Ro_Ge": "Цена для направления Romania -> Georgia",
            "price_Ge_Ro": "Цена для направления Georgia -> Romania",
            "remark": "Remark",
            "condition": "Condition"
        },
        ...
    }
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36'
        }
        response = requests.get(TARIFF_URL, headers=headers)
        response.raise_for_status()
        logger.info("Запрос к тарифной странице выполнен успешно. Код ответа: %s", response.status_code)
        logger.info("Длина полученного HTML: %d символов", len(response.text))
    except Exception as e:
        logger.error(f"Ошибка при запросе тарифов с сайта: {e}")
        raise Exception(f"Ошибка при запросе тарифов с сайта: {e}")

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table')
    if not table:
        logger.error("Таблица тарифов не найдена на странице. Попытка поиска альтернативных селекторов.")
        # Альтернативная попытка: если таблица обёрнута в div с классом 'table-responsive'
        table_container = soup.find('div', class_='table-responsive')
        if table_container:
            table = table_container.find('table')
    
    if not table:
        logger.error("Таблица тарифов так и не найдена на странице.")
        raise Exception("Таблица тарифов не найдена на странице.")

    prices = {}
    rows = table.find_all('tr')
    if not rows or len(rows) < 2:
        logger.error("В таблице тарифов нет данных для обработки.")
        raise Exception("В таблице тарифов нет данных для обработки.")

    # Предполагается, что первая строка таблицы – заголовок, а последующие строки – данные
    for row in rows[1:]:
        cols = row.find_all('td')
        if len(cols) < 5:
            continue  # если строка не содержит достаточное число ячеек, пропускаем её
        vehicle_type = cols[0].get_text(strip=True)
        price_Ro_Ge = cols[1].get_text(strip=True)
        price_Ge_Ro = cols[2].get_text(strip=True)
        remark = cols[3].get_text(strip=True)
        condition = cols[4].get_text(strip=True)
        prices[vehicle_type] = {
            "price_Ro_Ge": price_Ro_Ge,
            "price_Ge_Ro": price_Ge_Ro,
            "remark": remark,
            "condition": condition
        }
        logger.info(f"Найден тариф для '{vehicle_type}': {prices[vehicle_type]}")

    return prices

if __name__ == "__main__":
    try:
        ferry_prices = get_ferry_prices()
        for vehicle, data in ferry_prices.items():
            print(f"{vehicle}: {data}")
    except Exception as e:
        print(f"Error: {e}")
