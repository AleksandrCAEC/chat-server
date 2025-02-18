import requests
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TARIFF_URL = "https://e60shipping.com/en/32/static/tariff.html"

def get_ferry_prices():
    """
    Делает HTTP-запрос к странице тарифов и извлекает информацию из таблицы.
    Возвращает словарь вида:
      {
         "VehicleType1": {
             "price_Ro_Ge": <цена для направления Romania -> Georgia>,
             "price_Ge_Ro": <цена для направления Georgia -> Romania>,
             "remark": <замечание>,
             "conditions": [ <Condition1>, <Condition2>, ... ]
         },
         ...
      }
    Логика извлечения данных реализована в коде, а все примеры и описания вынесены во внешнее правило.
    """
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
    
    table = soup.find('table')
    if not table:
        logger.error("Tariff table not found.")
        return {}
    
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
    
    logger.info(f"Extracted tariffs: {prices}")
    return prices

if __name__ == "__main__":
    prices = get_ferry_prices()
    logger.info(f"Result: {prices}")
