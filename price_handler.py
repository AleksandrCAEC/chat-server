# price_handler.py
import os
import logging
import re
from price import get_ferry_prices
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Замените на актуальный Spreadsheet ID для файла Price.xlsx
PRICE_SPREADSHEET_ID = "1N4VpU1rBw3_MPx6GJRDiSQ03iHhS24noTq5-i6V01z8"

def get_sheets_service():
    try:
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
      E: Condition1
      F: Condition2
      G: Condition3
    Возвращает словарь вида:
      {
         "VehicleType1": {
             "price_Ro_Ge": "...",
             "price_Ge_Ro": "...",
             "remark": "...",
             "conditions": [ "Condition1 текст", "Condition2 текст", "Condition3 текст" ]
         },
         ...
      }
    """
    try:
        service = get_sheets_service()
        # Измените диапазон, если количество столбцов больше
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
            vehicle_type = row[0].strip()
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
    Отправляет уведомление через Telegram, используя переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID.
    """
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

def extract_numeric(price_str):
    """
    Извлекает числовое значение из строки с ценой, удаляя лишние символы.
    Возвращает float или None, если извлечение не удалось.
    """
    if not price_str:
        return None
    # Удаляем все символы, кроме цифр, точки и запятой
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    # Если есть запятая без точки, заменяем запятую на точку
    if cleaned.count(',') > 0 and cleaned.count('.') == 0:
        cleaned = cleaned.replace(',', '.')
    # Если есть и запятая и точка, предполагаем, что точка - десятичный разделитель, а запятая - разделитель тысяч
    elif cleaned.count(',') > 0 and cleaned.count('.') > 0:
        cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None

def check_ferry_price(vehicle_type, direction="Ro_Ge"):
    """
    Сравнивает тарифы для указанного типа транспортного средства и направления.
    
    direction: 
      - "Ro_Ge" для направления Romania -> Georgia,
      - "Ge_Ro" для направления Georgia -> Romania.
    
    Логика:
      1. Получаем актуальные тарифы с сайта через get_ferry_prices() из модуля price.
      2. Загружаем данные из Price.xlsx с помощью load_price_data().
      3. Если данные доступны из обоих источников, сравниваем их; данные с сайта имеют приоритет.
         Если цены совпадают (с учетом небольших погрешностей), формируем ответ с подтверждённой ценой.
         Если цены различаются, отправляем уведомление менеджеру и просим уточнить цену.
      4. Если один из источников недоступен, возвращаем данные из доступного источника.
      5. В случае сбоя в сверке или обработки данных, отправляем уведомление через Telegram для отладки.
    """
    try:
        website_prices = get_ferry_prices()
        sheet_prices = load_price_data()
        
        # Определяем сырые значения цены в зависимости от направления
        if direction == "Ro_Ge":
            website_raw = website_prices.get(vehicle_type, {}).get("price_Ro_Ge", "")
            sheet_raw = sheet_prices.get(vehicle_type, {}).get("price_Ro_Ge", "")
        else:
            website_raw = website_prices.get(vehicle_type, {}).get("price_Ge_Ro", "")
            sheet_raw = sheet_prices.get(vehicle_type, {}).get("price_Ge_Ro", "")
        
        # Извлекаем числовые значения из цен
        website_price_numeric = extract_numeric(website_raw)
        sheet_price_numeric = extract_numeric(sheet_raw)
        
        # Получаем дополнительные данные из Price.xlsx для ответа
        remark = sheet_prices.get(vehicle_type, {}).get("remark", "")
        conditions = sheet_prices.get(vehicle_type, {}).get("conditions", [])
        
        # Логика выбора: если данные с сайта доступны, используем их как приоритет
        if website_price_numeric is not None:
            final_price = website_price_numeric
            source_used = "сайта"
        elif sheet_price_numeric is not None:
            final_price = sheet_price_numeric
            source_used = "базы"
        else:
            message = f"Извините, тариф для '{vehicle_type}' недоступен ни на сайте, ни в базе."
            send_telegram_notification(f"Ошибка: Нет данных о тарифе для '{vehicle_type}' в обоих источниках.")
            return message
        
        # Если оба источника доступны, сравниваем их
        if website_price_numeric is not None and sheet_price_numeric is not None:
            if abs(website_price_numeric - sheet_price_numeric) > 0.001:
                message_to_manager = (f"ВНИМАНИЕ: Для транспортного средства '{vehicle_type}' цены различаются. "
                                      f"Сайт: {website_raw} (обработано как {website_price_numeric}), "
                                      f"База: {sheet_raw} (обработано как {sheet_price_numeric}). Требуется уточнение!")
                send_telegram_notification(message_to_manager)
                return (f"Цена для '{vehicle_type}' требует уточнения. Пожалуйста, свяжитесь с менеджером по телефонам: "
                        "+995595198228 или +4367763198228.")
            # Если цены совпадают (с учетом погрешности), используем данные с сайта
            final_price = website_price_numeric
            source_used = "сайта"
        
        # Формируем ответное сообщение
        response_message = f"Цена перевозки для '{vehicle_type}' ({direction.replace('_', ' ')}) составляет {final_price} (данные из {source_used})."
        if remark:
            response_message += f" Примечание: {remark}"
        if conditions:
            response_message += "\nДля более точного расчёта, пожалуйста, ответьте на следующие вопросы:"
            for question in conditions:
                response_message += f"\n{question}"
        return response_message
    except Exception as e:
        error_msg = f"Ошибка при сравнении цен для '{vehicle_type}': {e}"
        logger.error(error_msg)
        send_telegram_notification(error_msg)
        return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."

if __name__ == "__main__":
    # Пример вызова функции для тестирования
    vehicle = "Truck"  # Пример: заменить на реальный тип транспортного средства, как в таблице Price.xlsx
    direction = "Ro_Ge"  # или "Ge_Ro"
    message = check_ferry_price(vehicle, direction)
    print(message)
