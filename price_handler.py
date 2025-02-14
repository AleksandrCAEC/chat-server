import os
import logging
import re
from price import get_ferry_prices
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from bible import load_bible_data  # Для получения пояснений из Bible.xlsx

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
      E, F, G, ...: Дополнительные условия (Condition1, Condition2, …),
          где в каждой ячейке стоит "1" (условие активно) или "0" (не активно).
    Возвращает словарь вида:
      {
         "VehicleType1": {
             "price_Ro_Ge": "...",
             "price_Ge_Ro": "...",
             "remark": "...",
             "conditions": [ значение из ячеек, если есть ]
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
            vehicle_type = row[0].strip()
            price_Ro_Ge = row[1].strip() if len(row) > 1 else ""
            price_Ge_Ro = row[2].strip() if len(row) > 2 else ""
            remark = row[3].strip() if len(row) > 3 else ""
            # Сохраняем оставшиеся столбцы как условия (например, Condition1, Condition2, ...)
            conditions = []
            for i in range(4, len(row)):
                conditions.append(row[i].strip())
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
    Извлекает числовое значение из строки с ценой, удаляя лишние символы (например, валюту).
    Возвращает float или None, если извлечение не удалось.
    """
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    if cleaned.count(',') > 0 and cleaned.count('.') == 0:
        cleaned = cleaned.replace(',', '.')
    elif cleaned.count(',') > 0 and cleaned.count('.') > 0:
        cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None

def get_condition_detail(condition_index, guiding_answer):
    """
    Для заданного индекса условия (ConditionX) возвращает пояснение из Bible.xlsx.
    Ищется строка, где в столбце Verification содержится точное значение "ConditionX"
    (например, для condition_index=2 ищется "Condition3").
    
    Возвращает кортеж (detail_text, extra_cost), где:
      - detail_text: текстовое описание условия из столбца Answers.
      - extra_cost: числовое значение дополнительной платы, извлечённое из detail_text (если есть),
                    иначе None.
    """
    condition_key = f"Condition{condition_index + 1}"
    bible_df = load_bible_data()
    for index, row in bible_df.iterrows():
        verification_val = str(row.get("Verification", "")).strip()
        if verification_val.lower() == condition_key.lower():
            detail_text = row.get("Answers", "").strip()
            extra_cost = extract_numeric(detail_text)
            return detail_text, extra_cost
    return None, None

def check_ferry_price(vehicle_type, direction="Ro_Ge", client_guiding_answers=None):
    """
    Сравнивает тарифы для указанного типа транспортного средства и направления.
    
    Логика:
      1. Получает базовую цену из двух источников: сайта (приоритет) и Price.xlsx.
      2. Если оба источника доступны, проверяет их согласованность.
      3. Из Price.xlsx считываются все столбцы с условиями (Condition1, Condition2, ...).
         Для каждого условия, где стоит метка "1" (активное), если клиент подтвердил его (ответ присутствует
         в client_guiding_answers в соответствующем порядке), вызывается get_condition_detail(), которая ищет
         в Bible.xlsx строку с Verification равным "ConditionX". Если найдена, из Answers извлекается подробное
         описание и, возможно, дополнительная плата.
      4. Итоговое сообщение теперь формируется так:
            - Сначала выводится **базовая цена** перевозки (с указанием источника).
            - Затем, если есть активные условия, выводится перечень дополнительных услуг и их суммарная стоимость.
            - После этого, если применимы дополнительные услуги, показывается **итоговая стоимость** (базовая + доплаты).
      5. При ошибках или несоответствии источников отправляется уведомление менеджеру.
    """
    try:
        website_prices = get_ferry_prices()
        sheet_prices = load_price_data()
        
        # Получение "сырых" значений цены по направлению
        if direction == "Ro_Ge":
            website_raw = website_prices.get(vehicle_type, {}).get("price_Ro_Ge", "")
            sheet_raw = sheet_prices.get(vehicle_type, {}).get("price_Ro_Ge", "")
        else:
            website_raw = website_prices.get(vehicle_type, {}).get("price_Ge_Ro", "")
            sheet_raw = sheet_prices.get(vehicle_type, {}).get("price_Ge_Ro", "")
        
        website_price_numeric = extract_numeric(website_raw)
        sheet_price_numeric = extract_numeric(sheet_raw)
        
        remark = sheet_prices.get(vehicle_type, {}).get("remark", "")
        conditions = sheet_prices.get(vehicle_type, {}).get("conditions", [])
        
        # Определяем базовую цену с приоритетом данных с сайта
        if website_price_numeric is not None:
            base_price = website_price_numeric
            source_used = "сайта"
        elif sheet_price_numeric is not None:
            base_price = sheet_price_numeric
            source_used = "базы"
        else:
            message = f"Извините, тариф для '{vehicle_type}' недоступен ни на сайте, ни в базе."
            send_telegram_notification(f"Ошибка: Нет данных о тарифе для '{vehicle_type}' в обоих источниках.")
            return message
        
        # Если оба источника доступны, проверяем их согласованность
        if website_price_numeric is not None and sheet_price_numeric is not None:
            if abs(website_price_numeric - sheet_price_numeric) > 0.001:
                message_to_manager = (f"ВНИМАНИЕ: Для транспортного средства '{vehicle_type}' цены различаются. "
                                      f"Сайт: {website_raw} (обработано как {website_price_numeric}), "
                                      f"База: {sheet_raw} (обработано как {sheet_price_numeric}). Требуется уточнение!")
                send_telegram_notification(message_to_manager)
                return (f"Цена для '{vehicle_type}' требует уточнения. Пожалуйста, свяжитесь с менеджером по телефонам: "
                        "+995595198228 или +4367763198228.")
            base_price = website_price_numeric
            source_used = "сайта"
        
        # Обработка активных условий из Price.xlsx
        additional_total = 0.0
        active_conditions_details = []
        if client_guiding_answers and conditions:
            # Перебираем условия по порядку
            for i, cond in enumerate(conditions):
                if cond == "1" and i < len(client_guiding_answers):
                    client_answer = client_guiding_answers[i].strip().lower()
                    if client_answer:
                        detail_text, extra_cost = get_condition_detail(i, client_answer)
                        if detail_text:
                            active_conditions_details.append(detail_text)
                        if extra_cost is not None:
                            additional_total += extra_cost
        
        total_price = base_price + additional_total
        
        # Формирование итогового ответа с разделением базовой цены и доплат
        response_message = f"Базовая цена перевозки для '{vehicle_type}' ({direction.replace('_', ' ')}) составляет {base_price} евро (данные из {source_used})."
        if remark:
            response_message += f"\nПримечание: {remark}"
        if active_conditions_details:
            response_message += "\n\nДополнительные услуги:"
            for detail in active_conditions_details:
                response_message += f"\n- {detail}"
            response_message += f"\nСуммарная стоимость дополнительных услуг: {additional_total} евро."
            response_message += f"\n\nИтоговая стоимость перевозки: {total_price} евро."
        else:
            response_message += f"\n\nИтоговая стоимость перевозки: {base_price} евро."
        return response_message
    except Exception as e:
        error_msg = f"Ошибка при сравнении цен для '{vehicle_type}': {e}"
        logger.error(error_msg)
        send_telegram_notification(error_msg)
        return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."

def get_price_response(vehicle_type, direction="Ro_Ge", client_guiding_answers=None):
    try:
        response = check_ferry_price(vehicle_type, direction, client_guiding_answers)
        return response
    except Exception as e:
        logger.error(f"Ошибка при получении цены для {vehicle_type}: {e}")
        return "Произошла ошибка при получении актуальной цены. Пожалуйста, попробуйте позже."

if __name__ == "__main__":
    # Пример вызова функции для тестирования
    vehicle = "Truck"  # Например, "Truck" или "Fura"
    direction = "Ro_Ge"  # или "Ge_Ro"
    guiding_answers = ["без водителя", "нет ADR"]
    message = check_ferry_price(vehicle, direction, client_guiding_answers=guiding_answers)
    print(message)
