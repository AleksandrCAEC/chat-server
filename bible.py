# bible.py
import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        return None

def load_bible_data():
    """
    Загружает данные из файла Bible.xlsx через Google Sheets.
    Идентификатор таблицы: 1QB3Jv7cL5hNwDKx9rQF6FCrKHW7IHPAqrUg7FIvY7Dk
    Диапазон: "Bible!A:C" (предполагается, что первая строка – заголовки: FAQ, Answers, Verification)
    """
    bible_spreadsheet_id = "1QB3Jv7cL5hNwDKx9rQF6FCrKHW7IHPAqrUg7FIvY7Dk"
    sheets_service = get_sheets_service()
    if not sheets_service:
        logger.error("Google Sheets API не инициализирован.")
        return None
    try:
        range_name = "Bible!A:C"
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=bible_spreadsheet_id,
            range=range_name
        ).execute()
        values = result.get('values', [])
        if not values:
            logger.info("Нет данных в таблице Bible.")
            return pd.DataFrame(columns=["FAQ", "Answers", "Verification"])
        # Предполагается, что первая строка – заголовки
        df = pd.DataFrame(values[1:], columns=values[0])
        logger.info(f"Данные Bible успешно загружены: {df.shape[0]} записей.")
        return df
    except Exception as e:
        logger.error(f"Ошибка чтения Bible.xlsx через Google Sheets API: {e}")
        return None
