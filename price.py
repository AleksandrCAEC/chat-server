# price.py
import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_ferry_prices():
    """
    Получает актуальные тарифы с сайта https://e60shipping.com/en/32/static/tariff.html.
    
    Для примера предполагается, что на странице цены для Truck и Fura находятся в элементах с классами:
      - "price-truck" для Truck
      - "price-fura" для Fura
    
    Если парсинг не удаётся, возвращается PLACEHOLDER "PRICE_QUERY".
    """
    url = "https://e60shipping.com/en/32/static/tariff.html"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        prices = {}
        truck_elem = soup.find("div", class_="price-truck")
        if truck_elem:
            price_text = truck_elem.get_text(strip=True)
            prices["truck"] = {"price_Ro_Ge": price_text, "price_Ge_Ro": price_text}
        fura_elem = soup.find("div", class_="price-fura")
        if fura_elem:
            price_text = fura_elem.get_text(strip=True)
            prices["fura"] = {"price_Ro_Ge": price_text, "price_Ge_Ro": price_text}
        
        if not prices:
            logger.error("Не удалось найти цены на странице, возвращаем PLACEHOLDER.")
            prices["truck"] = {"price_Ro_Ge": "PRICE_QUERY", "price_Ge_Ro": "PRICE_QUERY"}
            prices["fura"] = {"price_Ro_Ge": "PRICE_QUERY", "price_Ge_Ro": "PRICE_QUERY"}
        
        logger.info(f"Полученные цены с сайта: {prices}")
        return prices
    except Exception as e:
        logger.error(f"Ошибка при получении цен с сайта: {e}")
        return {
            "truck": {"price_Ro_Ge": "PRICE_QUERY", "price_Ge_Ro": "PRICE_QUERY"},
            "fura": {"price_Ro_Ge": "PRICE_QUERY", "price_Ge_Ro": "PRICE_QUERY"}
        }
