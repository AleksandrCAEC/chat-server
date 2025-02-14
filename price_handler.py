import os
import logging
import re
import string
from price import get_ferry_prices  # Убедитесь, что этот модуль возвращает данные с сайта
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Spreadsheet ID для файла Price.xlsx
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
    Загружает данные из Google Sheets (Price.xlsx).
    Ожидается, что таблица имеет следующие столбцы:
      A: Наименование тарифа (например, "Standard truck with trailer (up to 17M)")
      B: Цена (Констанца-Поти)
    Возвращает словарь вида:
      {
         "Standard truck with trailer (up to 17M)": "2200",
         ...
      }
    """
    try:
        service = get_sheets_service()
        # Считываем только столбцы A и B
        range_name = "Sheet1!A2:B"
        result = service.spreadsheets().values().get(
            spreadsheetId=PRICE_SPREADSHEET_ID,
            range=range_name
        ).execute()
        values = result.get("values", [])
        if not values:
            logger.error("Пустые данные, полученные из Price.xlsx.")
            return {}
        price_data = {}
        for row in values:
            if len(row) < 2:
                continue
            tariff_name = row[0].strip()
            price = row[1].strip()
            price_data[tariff_name] = price
        logger.info(f"Данные из Price.xlsx: {price_data}")
        return price_data
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из Price.xlsx: {e}")
        return {}

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

def normalize_text(text):
    """
    Приводит текст к нижнему регистру, удаляет пунктуацию и лишние пробелы.
    """
    text = text.lower()
    text = re.sub(f'[{re.escape(string.punctuation)}]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def select_vehicle_record(query, price_data):
    """
    Определяет, какой тариф из price_data подходит для запроса.
    Использует синонимы для грузовика.
    """
    synonyms = ['truck', 'грузовик', 'фура', 'еврофура', 'трайлер', 'трас']
    query_norm = normalize_text(query)
    candidate = None
    for key in price_data.keys():
        key_norm = normalize_text(key)
        if any(s in query_norm for s in synonyms) and any(s in key_norm for s in synonyms):
            candidate = key
            break
    logger.info(f"Выбран тариф: {candidate} для запроса: '{query_norm}'")
    return candidate

def check_ferry_price(query, direction="Ro_Ge"):
    """
    Основная функция получения цены.
    1. Выбирается тариф из Price.xlsx на основе запроса (через select_vehicle_record).
    2. Получается стоимость из Price.xlsx и с сайта через get_ferry_prices().
    3. Если один из источников возвращает placeholder "PRICE_QUERY", он игнорируется.
    4. Возвращается цена, как есть, без каких-либо вычислений.
    """
    try:
        price_data = load_price_data()
        if not price_data:
            return "Ошибка чтения данных из Price.xlsx."
        record_key = select_vehicle_record(query, price_data)
        if not record_key:
            return "Информация о тарифах для данного запроса отсутствует в базе."
        
        website_prices = get_ferry_prices()
        logger.info(f"Данные с сайта: {website_prices}")
        website_raw = ""
        if website_prices and record_key in website_prices:
            website_raw = website_prices[record_key].get("price_Ro_Ge", "").strip()
        sheet_raw = price_data.get(record_key, "").strip()
        
        # Если источник возвращает "PRICE_QUERY", считаем его недействительным
        if website_raw.upper() == "PRICE_QUERY":
            website_price = None
        else:
            website_price = website_raw
        if sheet_raw.upper() == "PRICE_QUERY":
            sheet_price = None
        else:
            sheet_price = sheet_raw
        
        if website_price:
            base_price = website_price
            source_used = "сайта"
        elif sheet_price:
            base_price = sheet_price
            source_used = "базы"
        else:
            send_telegram_notification(f"Нет данных для тарифа '{record_key}'.")
            return f"Тариф для '{record_key}' недоступен."
        
        response_message = f"Стандартная цена для '{record_key}' составляет {base_price} евро (данные из {source_used})."
        return response_message
    except Exception as e:
        error_msg = f"Ошибка при получении цены для запроса '{query}': {e}"
        logger.error(error_msg)
        send_telegram_notification(error_msg)
        return "Произошла ошибка при получении цены."

def get_price_response(vehicle_query, direction="Ro_Ge"):
    try:
        response = check_ferry_price(vehicle_query, direction)
        return response
    except Exception as e:
        logger.error(f"Ошибка при получении цены для '{vehicle_query}': {e}")
        return "Ошибка получения цены."

if __name__ == "__main__":
    # Пример тестирования: запрос "Standard truck with trailer (up to 17M)"
    test_query = "Standard truck with trailer (up to 17M)"
    message = check_ferry_price(test_query, direction="Ro_Ge")
    print(message)
