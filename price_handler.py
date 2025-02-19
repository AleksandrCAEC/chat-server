# price_handler.py
import os
import re
import logging
import json
from price import get_ferry_prices
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Замените на актуальный Spreadsheet ID для файла Price.xlsx
PRICE_SPREADSHEET_ID = "1N4VpU1rBw3_MPx6GJRDiSQ03iHhS24noTq5-i6V01z8"

def get_sheets_service():
    try:
        # Используем метод from_service_account_file напрямую, т.к. Price.xlsx временно отключён
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        return build('sheets', 'v4', credentials=credentials)
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
      E, F, G: Conditions (при необходимости)
    Возвращает словарь вида:
      {
         "VehicleType1": {
             "price_Ro_Ge": "...",
             "price_Ge_Ro": "...",
             "remark": "...",
             "conditions": [ "Condition1", "Condition2", ... ]
         },
         ...
      }
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
            key = row[0].strip()
            price_Ro_Ge = row[1].strip() if len(row) > 1 else ""
            price_Ge_Ro = row[2].strip() if len(row) > 2 else ""
            remark = row[3].strip() if len(row) > 3 else ""
            conditions = []
            if len(row) > 4 and row[4].strip():
                conditions.append(row[4].strip())
            if len(row) > 5 and row[5].strip():
                conditions.append(row[5].strip())
            if len(row) > 6 and row[6].strip():
                conditions.append(row[6].strip())
            price_data[key] = {
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
    try:
        import requests
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if telegram_bot_token and telegram_chat_id:
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
            requests.post(url, json=payload)
    except Exception as ex:
        logger.error(f"Ошибка при отправке уведомления: {ex}")

def remove_timestamp(text):
    return re.sub(r'^\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*-\s*', '', text)

def parse_price(price_str):
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
    Сравнивает тарифы для указанного типа транспортного средства и направления.
    
    Если цены из сайта и базы совпадают, возвращает строку с подтвержденной ценой и примечанием.
    Если не совпадают – отправляет уведомление менеджеру и просит уточнения.
    
    Для поиска тарифов используется частичное (case-insensitive) сопоставление ключей.
    """
    try:
        website_prices = get_ferry_prices()
        sheet_prices = load_price_data()
        
        # Поиск ключа в данных с сайта (website_prices)
        matched_key_site = None
        for key in website_prices.keys():
            if vehicle_type.lower() in key.lower():
                matched_key_site = key
                break
        if not matched_key_site:
            return f"Извините, актуальная цена для транспортного средства '{vehicle_type}' не найдена на сайте."
        
        # Поиск ключа в данных из базы (sheet_prices)
        matched_key_sheet = None
        for key in sheet_prices.keys():
            if vehicle_type.lower() in key.lower():
                matched_key_sheet = key
                break
        if not matched_key_sheet:
            return f"Извините, информация о тарифах для '{vehicle_type}' отсутствует в нашей базе."
        
        if direction == "Ro_Ge":
            website_price = website_prices[matched_key_site].get("price_Ro_Ge", "")
            sheet_price = sheet_prices[matched_key_sheet].get("price_Ro_Ge", "")
        else:
            website_price = website_prices[matched_key_site].get("price_Ge_Ro", "")
            sheet_price = sheet_prices[matched_key_sheet].get("price_Ge_Ro", "")
        
        if website_price == sheet_price and website_price:
            response_message = f"Цена перевозки для '{vehicle_type}' ({direction.replace('_', ' ')}) составляет {website_price}."
            if sheet_prices[matched_key_sheet].get("remark"):
                response_message += f" Примечание: {sheet_prices[matched_key_sheet]['remark']}"
            conditions = sheet_prices[matched_key_sheet].get("conditions", [])
            if conditions:
                response_message += "\nДля более точного расчёта, пожалуйста, ответьте на следующие вопросы:"
                for question in conditions:
                    response_message += f"\n{question}"
            return response_message
        else:
            message_to_manager = (f"ВНИМАНИЕ: Для транспортного средства '{vehicle_type}' цены различаются. "
                                  f"Сайт: {website_price}, База: {sheet_price}. Требуется уточнение!")
            send_telegram_notification(message_to_manager)
            return (f"Цена для '{vehicle_type}' требует уточнения. Пожалуйста, свяжитесь с менеджером "
                    "или дождитесь уточнённого ответа.")
    except Exception as e:
        logger.error(f"Ошибка при сравнении цен: {e}")
        return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."

if __name__ == "__main__":
    vehicle = "Truck"
    direction = "Ro_Ge"
    message = check_ferry_price(vehicle, direction)
    print(message)
