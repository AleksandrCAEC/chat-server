import os
import pandas as pd
from openpyxl import Workbook, load_workbook
import logging
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Используем переменную окружения или путь по умолчанию (относительный к корню проекта)
default_path = "./service_account.json"
service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", default_path)
service_account_path = os.path.abspath(service_account_path)
if not os.path.exists(service_account_path):
    logger.warning(f"Файл учетных данных {service_account_path} не найден. Проверьте, что он существует, или задайте корректный путь.")
else:
    logger.info(f"Найден файл учетных данных: {service_account_path}")

# Реальный идентификатор таблицы Google Sheets (из вашей ссылки)
BIBLE_SPREADSHEET_ID = "1QB3Jv7cL5hNwDKx9rQF6FCrKHW7IHPAqrUg7FIvY7Dk"

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(service_account_path)
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Error initializing Sheets API: {e}")
        raise

def load_bible_data():
    try:
        service = get_sheets_service()
        # Ожидается, что лист "Bible" содержит столбцы: FAQ, Answers, Verification
        # Для внутренних инструкций в FAQ должен стоять знак "-", а в Verification — "RULE"
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
        logger.info(f"Bible data loaded. Records: {len(df)}")
        return df
    except Exception as e:
        logger.error(f"Error loading Bible data: {e}")
        return None

def ensure_local_bible_file(local_path):
    if not os.path.exists(local_path):
        try:
            directory = os.path.dirname(local_path)
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            wb = Workbook()
            ws = wb.active
            ws.append(["FAQ", "Answers", "Verification"])
            wb.save(local_path)
            logger.info(f"Local Bible file created: {local_path}")
        except Exception as e:
            logger.error(f"Error creating local Bible file {local_path}: {e}")
            raise

def save_bible_pair(question, answer):
    try:
        service = get_sheets_service()
        new_row = [[question, answer, "Check"]]
        body = {"values": new_row}
        result = service.spreadsheets().values().append(
            spreadsheetId=BIBLE_SPREADSHEET_ID,
            range="Bible!A:C",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
        logger.info(f"New pair added: FAQ='{question}', Answers='{answer}', Verification='Check'. Result: {result}")
    except Exception as e:
        logger.error(f"Error saving pair to Bible: {e}")
        try:
            temp_file = os.path.join(os.getcwd(), "Temp_Bible.xlsx")
            ensure_local_bible_file(temp_file)
            wb = load_workbook(temp_file)
            ws = wb.active
            ws.append([question, answer, "Check"])
            wb.save(temp_file)
            logger.error(f"Temporary Bible file created: {temp_file}")
        except Exception as e2:
            logger.error(f"Error creating temporary Bible file: {e2}")
        raise

def get_rule():
    """
    Возвращает объединённый текст всех внутренних инструкций,
    то есть строк, где в столбце FAQ стоит "-" и в столбце Verification записано "RULE".
    Если таких строк нет, возвращается "<no_rules_found>".
    """
    df = load_bible_data()
    if df is None:
        return "<no_rules_found>"
    internal_rules = df[
        (df["FAQ"].str.strip() == "-") &
        (df["Verification"].str.upper() == "RULE")
    ]
    if internal_rules.empty:
        return "<no_rules_found>"
    lines = internal_rules["Answers"].tolist()
    return "\n".join(lines)

if __name__ == "__main__":
    df = load_bible_data()
    logger.info(df)
