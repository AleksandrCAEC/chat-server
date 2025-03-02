import requests
from bs4 import BeautifulSoup
import logging
import re

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TARIFF_URL = "https://e60shipping.com/en/32/static/tariff.html"

def parse_tariff_from_text(text):
    """
    Запасной парсер: разбивает текст на строки и группирует их в блоки,
    предполагая, что после заголовка идут блоки, где:
      - Первая строка – название ТС (например, "Standard truck with trailer (up to 17M)")
      - Вторая строка – цена перевозки из Румынии в Грузии (Ro_Ge)
      - Третья строка – цена перевозки из Грузии в Румынии (может содержать зачёркнутую цену)
    Дополнительно, если после этого блока идут строки с информацией о круглых рейсах (начинающиеся с "Round Trip"),
    они пропускаются.
    """
    # Разбиваем текст по переносам строк и удаляем пустые строки
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    # Попытаемся найти индекс строки "Remark" – тогда данные идут после нее
    try:
        header_index = lines.index("Remark")
        data_lines = lines[header_index+1:]
    except ValueError:
        data_lines = lines
    tariffs = {}
    i = 0
    while i < len(data_lines):
        vehicle_type = data_lines[i]
        if i+1 < len(data_lines):
            price_Ro_Ge = data_lines[i+1]
        else:
            break
        # Формируем запись для базового тарифа; для простоты цены для Georgia–Romania и remark оставляем пустыми
        tariffs[vehicle_type] = {
            "price_Ro_Ge": price_Ro_Ge,
            "price_Ge_Ro": "",
            "remark": ""
        }
        # Если следующая строка после цены содержит не числовое значение, предполагаем, что блок завершён
        # Дополнительно, если встречается информация о "Round Trip", пропускаем весь блок (6 строк)
        if i+2 < len(data_lines) and data_lines[i+2].startswith("Round Trip"):
            i += 6
        else:
            i += 3
    return tariffs

def get_ferry_prices():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        response = requests.get(TARIFF_URL, headers=headers)
        response.raise_for_status()
        logger.info(f"Tariff page request successful. Status: {response.status_code}")
        html_text = response.text
        logger.info(f"HTML length: {len(html_text)}")
    except Exception as e:
        logger.error(f"Error requesting tariff page: {e}")
        return {}

    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Сначала пробуем найти таблицу
    table = soup.find('table')
    if table:
        rows = table.find_all('tr')
        if not rows or len(rows) < 2:
            logger.error("No data in tariff table.")
            return {}
        prices = {}
        for row in rows[1:]:
            cols = row.find_all('td')
            if len(cols) < 4:
                logger.debug("Skipping row with insufficient columns.")
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
        logger.info(f"Extracted tariffs using table: {prices}")
        return prices
    else:
        logger.warning("Tariff table not found. Falling back to text parsing.")
        text = soup.get_text(separator="\n")
        prices = parse_tariff_from_text(text)
        logger.info(f"Extracted tariffs using text parsing: {prices}")
        return prices

if __name__ == "__main__":
    prices = get_ferry_prices()
    logger.info(f"Result: {prices}")
