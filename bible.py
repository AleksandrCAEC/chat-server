import os
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, numbers
import logging
from datetime import datetime
import shutil
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BIBLE_SPREADSHEET_ID = "1QB3Jv7cL5hNwDKx9rQF6FCrKHW7IHPAqrUg7FIvY7Dk"

def get_credentials():
    env_val = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_val is None:
        raise Exception("Переменная окружения GOOGLE_APPLICATION_CREDENTIALS не установлена.")
    env_val = env_val.strip()
    if env_val.startswith("{"):
        info = json.loads(env_val)
        return Credentials.from_service_account_info(info)
    else:
        return Credentials.from_service_account_file(os.path.abspath(env_val))

def get_sheets_service():
    try:
        credentials = get_credentials()
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def load_bible_data():
    try:
        service = get_sheets_service()
        range_name = "Bible!A2:C"
        result = service.spreadsheets().values().get(
            spreadsheetId=BIBLE_SPREADSHEET_ID,
            range=range_name
        ).execute()
        values = result.get("values", [])
        if values:
            df = pd.DataFrame(values, columns=["FAQ", "Answers", "Verification"])
        else:
            df = pd.DataFrame(columns=["FAQ", "Answers", "Verification"])
        logger.info(f"Bible data loaded. Количество записей: {len(df)}")
        return df
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных из Bible.xlsx: {e}")
        return None

# Остальные функции (upload_or_update_file, ensure_local_bible_file, save_bible_pair, get_rule) остаются без изменений.
