import os
import pandas as pd
import logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BIBLE_SPREADSHEET_ID = os.getenv("BIBLE_SPREADSHEET_ID")

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def load_bible_data():
    try:
        service = get_sheets_service()
        range_name = "Bible!A2:D"
        result = service.spreadsheets().values().get(
            spreadsheetId=BIBLE_SPREADSHEET_ID, range=range_name
        ).execute()
        values = result.get("values", [])
        return pd.DataFrame(values, columns=["FAQ", "Answers", "Verification", "rule"])
    except Exception as e:
        logger.error(f"Ошибка загрузки Bible.xlsx: {e}")
        return None
