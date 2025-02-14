import os
import logging
import re
import string
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
    Считывает только столбцы A и B:
      A: Наименование тарифа (например, "Standard truck with trailer (up to 17M)")
      B: Цена (например, "2200")
    Возвращает словарь вида:
      {
         "Standard truck with trailer (up to 17M)": "2200",
         ...
      }
    """
    try:
        service = get_sheets_service()
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
    Использует нормализацию текста и проверку синонимов.
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
    Функция, которая просто возвращает цену, как записана в Price.xlsx, без каких-либо вычислений.
    """
    price_data = load_price_data()
    if not price_data:
        return "Ошибка чтения данных из Price.xlsx."
    record_key = select_vehicle_record(query, price_data)
    if not record_key:
        return "Информация о тарифах для данного запроса отсутствует в базе."
    
    price = price_data.get(record_key, "")
    if price.upper() == "PRICE_QUERY":
        return f"Тариф для '{record_key}' недоступен."
    
    response_message = f"Стандартная цена для '{record_key}' составляет {price} евро."
    return response_message

def get_price_response(vehicle_query, direction="Ro_Ge"):
    try:
        response = check_ferry_price(vehicle_query, direction)
        return response
    except Exception as e:
        logger.error(f"Ошибка при получении цены для '{vehicle_query}': {e}")
        return "Ошибка получения цены."

if __name__ == "__main__":
    test_query = "Standard truck with trailer (up to 17M)"
    message = check_ferry_price(test_query, direction="Ro_Ge")
    print(message)
