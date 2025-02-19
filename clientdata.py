import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta
import logging
from config import CLIENT_DATA_PATH, CLIENT_FILES_DIR
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Если директория для CLIENT_DATA_PATH не существует, создаём её
data_dir = os.path.dirname(CLIENT_DATA_PATH)
if not os.path.exists(data_dir):
    os.makedirs(data_dir, exist_ok=True)

SPREADSHEET_ID = "1eGpB0hiRxXPpYN75-UKyXoar7yh-zne8r8ox-hXrS1I"

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
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        return None

def load_client_data():
    try:
        logger.info("Загрузка данных из Google Sheets...")
        sheets_service = get_sheets_service()
        if not sheets_service:
            raise Exception("Google Sheets API не инициализирован.")
        range_name = "Sheet1!A2:G1000"
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
        values = result.get('values', [])
        if not values:
            logger.info("Данные не найдены.")
            return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])
        df = pd.DataFrame(values, columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])
        df["Client Code"] = df["Client Code"].astype(str)
        logger.info(f"Загружены данные: {df}")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

# Остальные функции остаются без изменений...
# (generate_unique_code, update_last_visit, save_client_data, register_or_update_client, verify_client_code)
