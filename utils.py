# utils.py
import os
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("utils.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация Google Sheets API
def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        return None

# Загрузка данных из Google Sheets (ClientData.xlsx)
def load_client_data():
    try:
        logger.info("Загрузка данных из Google Sheets...")
        sheets_service = get_sheets_service()
        if not sheets_service:
            raise Exception("Google Sheets API не инициализирован.")

        # Идентификатор таблицы ClientData.xlsx
        SPREADSHEET_ID = "1eGpB0hiRxXPpYN75-UKyXoar7yh-zne8r8ox-hXrS1I"
        range_name = "Sheet1!A2:G1000"  # Диапазон для всех столбцов

        # Загрузка данных
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()

        values = result.get('values', [])
        if not values:
            logger.info("Данные не найдены.")
            return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

        # Преобразуем данные в DataFrame
        df = pd.DataFrame(values, columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])
        
        # Преобразуем столбец "Client Code" в строковый тип
        df["Client Code"] = df["Client Code"].astype(str)
        
        logger.info(f"Загружены данные: {df}")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

# Загрузка данных из Google Sheets (Bible.xlsx)
def load_bible_data():
    try:
        logger.info("Загрузка данных из Bible.xlsx...")
        sheets_service = get_sheets_service()
        if not sheets_service:
            raise Exception("Google Sheets API не инициализирован.")

        # Идентификатор таблицы Bible.xlsx
        SPREADSHEET_ID = "1QB3Jv7cL5hNwDKx9rQF6FCrKHW7IHPAqrUg7FIvY7Dk"
        range_name = "Bible!A2:C1000"  # Диапазон для всех столбцов

        # Загрузка данных
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()

        values = result.get('values', [])
        if not values:
            logger.info("Данные в Bible.xlsx не найдены.")
            return pd.DataFrame(columns=["FAQ", "Answers", "Verification"])

        # Преобразуем данные в DataFrame
        df = pd.DataFrame(values, columns=["FAQ", "Answers", "Verification"])
        logger.info(f"Данные из Bible.xlsx загружены: {df}")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из Bible.xlsx: {e}")
        return pd.DataFrame(columns=["FAQ", "Answers", "Verification"])
