# price_handler.py
import os
import logging
from price import get_ferry_prices
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Замените на актуальный Spreadsheet ID для файла Price.xlsx
PRICE_SPREADSHEET_ID = "YOUR_PRICE_SPREADSHEET_ID"

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

def check_ferry_price(vehicle_type, direction="Ro_Ge"):
    """
    Сравнивает тарифы для указанного типа транспортного средства и направления.
    
    direction: 
      - "Ro_Ge" для направления Romania -> Georgia,
      - "Ge_Ro" для направления Georgia -> Romania.
    
    Логика:
      1. Получаем актуальные тарифы с сайта через get_ferry_prices() из модуля price.
      2. Загружаем данные из Price.xlsx с помощью load_price_data().
      3. Если для заданного типа транспортного средства данные отсутствуют в одном из источников, возвращаем соответствующее сообщение.
      4. Сравниваем цены из сайта и из Price.xlsx:
         - Если цены совпадают, формируем ответ с подтверждённой ценой и добавляем Remark.
           Если для данного типа транспортного средства в столбцах Condition* (conditions) указаны наводящие вопросы, 
           к ответу добавляется приглашение для уточнения, например:
           «Для более точного расчёта, пожалуйста, ответьте на следующие вопросы:
            {Condition1}
            {Condition2}
            ...»
         - Если цены различаются, возвращаем сообщение, что цена требует уточнения, и отправляем уведомление менеджеру.
    """
    try:
        website_prices = get_ferry_prices()
        sheet_prices = load_price_data()
        
        if vehicle_type not in website_prices:
            return f"Извините, актуальная цена для транспортного средства '{vehicle_type}' не найдена на сайте."
        if vehicle_type not in sheet_prices:
            return f"Извините, информация о тарифах для '{vehicle_type}' отсутствует в нашей базе."
        
        if direction == "Ro_Ge":
            website_price = website_prices[vehicle_type].get("price_Ro_Ge", "")
            sheet_price = sheet_prices[vehicle_type].get("price_Ro_Ge", "")
        else:
            website_price = website_prices[vehicle_type].get("price_Ge_Ro", "")
            sheet_price = sheet_prices[vehicle_type].get("price_Ge_Ro", "")
        
        if website_price == sheet_price:
            response_message = f"Цена перевозки для '{vehicle_type}' ({direction.replace('_', ' ')}) составляет {website_price}."
            if sheet_prices[vehicle_type].get("remark"):
                response_message += f" Примечание: {sheet_prices[vehicle_type]['remark']}"
            conditions = sheet_prices[vehicle_type].get("conditions", [])
            if conditions:
                response_message += "\nДля более точного расчёта, пожалуйста, ответьте на следующие вопросы:"
                for question in conditions:
                    response_message += f"\n{question}"
            return response_message
        else:
            message_to_manager = (f"ВНИМАНИЕ: Для транспортного средства '{vehicle_type}' цены различаются. "
                                  f"Сайт: {website_price}, База: {sheet_price}. Требуется уточнение!")
            send_telegram_notification(message_to_manager)
            return (f"Цена для '{vehicle_type}' требует уточнения. Пожалуйста, свяжитесь с менеджером по телефонам: "
                    "+995595198228 или +4367763198228.")
    except Exception as e:
        logger.error(f"Ошибка при сравнении цен: {e}")
        return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."

if __name__ == "__main__":
    # Пример вызова функции для тестирования
    vehicle = "Truck"  # Пример: заменить на реальный тип транспортного средства, как в таблице Price.xlsx
    direction = "Ro_Ge"  # или "Ge_Ro"
    message = check_ferry_price(vehicle, direction)
    print(message)
