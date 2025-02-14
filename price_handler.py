import os
import logging
import re
import string
from price import get_ferry_prices
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from bible import load_bible_data  # Для получения пояснений из Bible.xlsx

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
      C: Цена (Поти-Констанца)
      D: Round trip
      E и далее: Дополнительные условия (Condition1, Condition2, …) – "1" означает активное условие.
    Возвращает словарь вида:
      {
         "Standard truck with trailer (up to 17M)": {
             "price_Ro_Ge": "2200",
             "price_Ge_Ro": "1090",
             "round_trip": "3060",
             "conditions": [ "1", "0", ... ]
         },
         ...
      }
    """
    try:
        service = get_sheets_service()
        # Диапазон можно расширить, если есть больше столбцов
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
            tariff_name = row[0].strip()
            price_Ro_Ge = row[1].strip() if len(row) > 1 else ""
            price_Ge_Ro = row[2].strip() if len(row) > 2 else ""
            round_trip = row[3].strip() if len(row) > 3 else ""
            conditions = []
            for i in range(4, len(row)):
                conditions.append(row[i].strip())
            price_data[tariff_name] = {
                "price_Ro_Ge": price_Ro_Ge,
                "price_Ge_Ro": price_Ge_Ro,
                "round_trip": round_trip,
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

def extract_vehicle_size(query):
    """
    Извлекает размер (число метров) из запроса.
    Пример: "17 метров" или "17m" вернет число 17.
    """
    match = re.search(r'(\d{1,2})\s*(m|м|метр)', query.lower())
    if match:
        return int(match.group(1))
    return None

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
    Использует синонимы для грузовика и анализирует размер транспортного средства.
    Работает с нормализованными строками.
    """
    synonyms = ['truck', 'грузовик', 'фура', 'еврофура', 'трайлер', 'трас']
    query_norm = normalize_text(query)
    size = extract_vehicle_size(query)
    
    candidate = None
    for key in price_data.keys():
        key_norm = normalize_text(key)
        # Проверяем наличие одного из синонимов
        if any(s in key_norm for s in synonyms):
            size_match = re.search(r'(\d+)\s*(m|м)', key_norm)
            if size_match:
                max_size = int(size_match.group(1))
                if size is None or size <= max_size:
                    candidate = key
                    break
            else:
                candidate = key
                break
    logger.info(f"Выбран тариф: {candidate} для запроса: '{query_norm}', размер: {size}")
    return candidate

def get_condition_detail(condition_index):
  
