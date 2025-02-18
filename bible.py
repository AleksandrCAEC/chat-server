import os
import pandas as pd
from openpyxl import Workbook, load_workbook
import logging
from datetime import datetime
import shutil
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BIBLE_SPREADSHEET_ID = "1QB3Jv7cL5hNwDKx9rQF6FCrKHW7IHPAqrUg7FIvY7Dk"  # Замените на реальный ID

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Error initializing Sheets API: {e}")
        raise

def load_bible_data():
    try:
        service = get_sheets_service()
        range_name = "Bible!A2:E"  # Если у вас есть еще столбец Remark, можно указать его
        result = service.spreadsheets().values().get(
            spreadsheetId=BIBLE_SPREADSHEET_ID,
            range=range_name
        ).execute()
        values = result.get("values", [])
        if values:
            # Ожидается, что столбцы: FAQ, Answers, Verification, rule, Remark
            df = pd.DataFrame(values, columns=["FAQ", "Answers", "Verification", "rule", "Remark"])
        else:
            df = pd.DataFrame(columns=["FAQ", "Answers", "Verification", "rule", "Remark"])
        logger.info(f"Bible data loaded. Records: {len(df)}")
        return df
    except Exception as e:
        logger.error(f"Error loading Bible data: {e}")
        return None

def upload_or_update_file(file_name, file_stream):
    pass

def ensure_local_bible_file(local_path):
    if not os.path.exists(local_path):
        try:
            directory = os.path.dirname(local_path)
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            wb = Workbook()
            ws = wb.active
            ws.append(["FAQ", "Answers", "Verification", "rule", "Remark"])
            wb.save(local_path)
            logger.info(f"Local Bible file created: {local_path}")
        except Exception as e:
            logger.error(f"Error creating local Bible file {local_path}: {e}")
            raise

def save_bible_pair(question, answer):
    try:
        service = get_sheets_service()
        new_row = [[question, answer, "Check", "", ""]]  # Для обычных вопросов rule и Remark могут быть пустыми
        body = {"values": new_row}
        result = service.spreadsheets().values().append(
            spreadsheetId=BIBLE_SPREADSHEET_ID,
            range="Bible!A:E",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
        logger.info(f"New pair added: FAQ='{question}', Answers='{answer}', Verification='Check'. API response: {result}")
    except Exception as e:
        logger.error(f"Error saving pair to Bible: {e}")
        try:
            temp_file = os.path.join(os.getcwd(), "Temp_Bible.xlsx")
            ensure_local_bible_file(temp_file)
            wb = load_workbook(temp_file)
            ws = wb.active
            ws.append([question, answer, "Check", "", ""])
            wb.save(temp_file)
            logger.error(f"Temporary Bible file created: {temp_file}")
        except Exception as e2:
            logger.error(f"Error creating temporary Bible file: {e2}")
        raise

def get_rule(rule_key):
    """
    Функция возвращает правило (шаблон или текст) по ключу rule_key.
    Для этого ищутся строки, где:
      - FAQ равно "-" (то есть это внутренняя инструкция),
      - Verification содержит значение "RULE" (без учета регистра),
      - Remark (ключ) совпадает с rule_key (без учета регистра).
    Если правило найдено, возвращается значение из столбца Answers.
    Если не найдено, возвращается строка вида "<rule_key>".
    """
    df = load_bible_data()
    if df is None:
        return f"<{rule_key}>"
    # Отбираем строки, где FAQ равен "-" и Verification == "RULE"
    rules_df = df[(df["FAQ"].str.strip() == "-") & (df["Verification"].str.upper() == "RULE")]
    matching = rules_df[rules_df["Remark"].str.strip().str.lower() == rule_key.lower()]
    if not matching.empty:
        return matching.iloc[0]["Answers"]
    else:
        return f"<{rule_key}>"

if __name__ == "__main__":
    df = load_bible_data()
    logger.info(df)
