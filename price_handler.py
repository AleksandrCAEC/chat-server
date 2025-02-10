# price_handler.py
import os
import re
import logging
import time
from price import get_ferry_prices
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Замените на актуальный Spreadsheet ID для файла Price.xlsx
PRICE_SPREADSHEET_ID = "YOUR_PRICE_SPREADSHEET_ID"

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        service = build('sheets', 'v4', credentials=credentials)
        logger.info("Google Sheets API service initialized successfully.")
        return service
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def load_price_data():
    """
    Загружает данные из Google Sheets (Price.xlsx) для тарифов.
    Ожидается, что таблица имеет следующие столбцы:
      A: Type of the vehicle
      B: Price_Ro_Ge (направление: Romania -> Georgia)
      C: Price_Ge_Ro (направление: Georgia -> Romania)
      D: Remark
      E: Condition1
      F: Condition2
      G: Condition3
    Возвращает словарь вида:
      {
         "fura": {
             "price_Ro_Ge": "...",
             "price_Ge_Ro": "...",
             "remark": "...",
             "conditions": [ "Condition1", "Condition2", ... ]
         },
         ...
      }
    (Тип транспортного средства приводится к нижнему регистру.)
    Добавляются только те условия, где значение равно "1".
    """
    try:
        service = get_sheets_service()
        range_name = "Sheet1!A2:G"
        result = service.spreadsheets().values().get(
            spreadsheetId=PRICE_SPREADSHEET_ID,
            range=range_name
        ).execute()
        values = result.get("values", [])
        price_data = {}
        for row in values:
            if len(row) < 4:
                continue
            vehicle_type = row[0].strip().lower()
            price_Ro_Ge = row[1].strip() if len(row) > 1 else ""
            price_Ge_Ro = row[2].strip() if len(row) > 2 else ""
            remark = row[3].strip() if len(row) > 3 else ""
            conditions = []
            if len(row) > 4 and row[4].strip() == "1":
                conditions.append("Condition1")
            if len(row) > 5 and row[5].strip() == "1":
                conditions.append("Condition2")
            if len(row) > 6 and row[6].strip() == "1":
                conditions.append("Condition3")
            price_data[vehicle_type] = {
                "price_Ro_Ge": price_Ro_Ge,
                "price_Ge_Ro": price_Ge_Ro,
                "remark": remark,
                "conditions": conditions
            }
        logger.info(f"Данные из Price.xlsx загружены: {price_data}")
        return price_data
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из Price.xlsx: {e}")
        raise

def send_telegram_notification(message):
    """
    Отправляет уведомление через Telegram.
    """
    try:
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if telegram_bot_token and telegram_chat_id:
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
            response = requests.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Уведомление отправлено: {response.json()}")
    except Exception as ex:
        logger.error(f"Ошибка при отправке уведомления: {ex}")

def remove_timestamp(text):
    """
    Удаляет временной штамп из начала строки, если он присутствует.
    Пример: "10.02.25 09:33 - 2200 (EUR)" -> "2200 (EUR)"
    """
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
    """
    Извлекает числовое значение из строки цены.
    Пример: "2200 (EUR)" -> 2200.0
    """
    try:
        cleaned = re.sub(r'[^\d.]', '', price_str)
        value = float(cleaned)
        logger.info(f"Parsed price '{price_str}' -> {value}")
        return value
    except Exception as e:
        logger.error(f"Ошибка парсинга цены из '{price_str}': {e}")
        return None

def check_ferry_price(vehicle_type, direction="Ro_Ge"):
    """
    Получает актуальные тарифы с сайта и сравнивает с данными из Price.xlsx.
    
    Логика:
      1. Получает цены с сайта через get_ferry_prices() из модуля price.
      2. Загружает данные из Price.xlsx через load_price_data().
      3. Если полученная с сайта цена содержит PLACEHOLDER ("PRICE_QUERY" или "BASE_PRICE") или не содержит цифр,
         используется запасная цена из Price.xlsx.
      4. Иначе парсится цена и, если цена с сайта не совпадает с ценой из файла (требуется точное совпадение),
         отправляется уведомление менеджеру.
    """
    try:
        website_prices = get_ferry_prices()
        logger.info(f"Получены цены с сайта: {website_prices}")
        sheet_prices = load_price_data()
        
        if vehicle_type not in website_prices:
            msg = f"Извините, актуальная цена для '{vehicle_type}' не найдена на сайте."
            logger.error(msg)
            return msg
        if vehicle_type not in sheet_prices:
            msg = f"Извините, информация о тарифах для '{vehicle_type}' отсутствует в нашей базе."
            logger.error(msg)
            return msg
        
        if direction == "Ro_Ge":
            website_price_str = website_prices[vehicle_type].get("price_Ro_Ge", "")
            sheet_price_str = sheet_prices[vehicle_type].get("price_Ro_Ge", "")
        else:
            website_price_str = website_prices[vehicle_type].get("price_Ge_Ro", "")
            sheet_price_str = sheet_prices[vehicle_type].get("price_Ge_Ro", "")
        
        website_price_str = remove_timestamp(website_price_str).strip()
        logger.info(f"Цена с сайта для {vehicle_type}: '{website_price_str}'")
        
        # Если сайт возвращает PLACEHOLDER или строка не содержит цифр, используем запасную цену
        if not re.search(r'\d', website_price_str) or website_price_str.upper() in ["PRICE_QUERY", "BASE_PRICE"]:
            fallback_price_str = sheet_prices[vehicle_type].get("price_Ro_Ge", "")
            logger.info(f"Сайт вернул PLACEHOLDER или некорректное значение. Используем запасную цену для {vehicle_type}: '{fallback_price_str}'")
            return fallback_price_str
        
        website_price_value = parse_price(website_price_str)
        sheet_price_value = parse_price(sheet_price_str)
        
        if website_price_value is None or sheet_price_value is None:
            logger.error("Не удалось распарсить цену.")
            return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."
        
        if website_price_value == sheet_price_value:
            response_message = f"Цена перевозки для '{vehicle_type}' ({direction.replace('_', ' ')}) составляет {website_price_str}."
            remark = sheet_prices[vehicle_type].get("remark", "")
            if remark:
                response_message += f" Примечание: {remark}"
            conditions = sheet_prices[vehicle_type].get("conditions", [])
            if conditions:
                response_message += "\nДля более точного расчёта, пожалуйста, ответьте на следующие вопросы:"
                for marker in conditions:
                    response_message += f"\n{marker}"
            return response_message
        else:
            message_to_manager = (f"ВНИМАНИЕ: Для '{vehicle_type}' цены различаются. "
                                  f"Сайт: {website_price_str}, Файл: {sheet_price_str}. Требуется уточнение!")
            send_telegram_notification(message_to_manager)
            return (f"Цена для '{vehicle_type}' требует уточнения. Пожалуйста, свяжитесь с менеджером по телефонам: "
                    "+995595198228 или +4367763198228.")
    except Exception as e:
        logger.error(f"Ошибка при сравнении цен: {e}")
        return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."

if __name__ == "__main__":
    # Пример вызова функции для тестирования
    vehicle = "truck"  # Используйте "truck" или "fura" (в нижнем регистре)
    direction = "Ro_Ge"  # или "Ge_Ro"
    message = check_ferry_price(vehicle, direction)
    print(message)
