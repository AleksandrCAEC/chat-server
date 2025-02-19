# bible.py
import os
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, numbers
import logging
from datetime import datetime
import shutil  # для копирования файлов

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Укажите идентификатор Google Sheets таблицы Bible.xlsx
# Например: "1QB3Jv7cL5hNwDKx9rQF6FCrKHW7IHPAqrUg7FIvY7Dk"
BIBLE_SPREADSHEET_ID = "1QB3Jv7cL5hNwDKx9rQF6FCrKHW7IHPAqrUg7FIvY7Dk"

def get_sheets_service():
    """
    Инициализирует и возвращает объект сервиса Google Sheets.
    """
    try:
        from google.oauth2.service_account import Credentials
        credentials = Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def load_bible_data():
    """
    Загружает данные из Google Sheets таблицы Bible.xlsx и возвращает их в виде DataFrame.
    Предполагается, что данные находятся на листе с именем "Bible" и в диапазоне A2:C,
    где строка 1 содержит заголовки: FAQ, Answers, Verification.
    
    Для внутренних инструкций: в столбце FAQ стоит "-", а в Verification записано "RULE".
    """
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

def upload_or_update_file(file_name, file_stream):
    """
    Обновляет или создаёт файл на Google Drive (реализация уже имеется в вашем проекте).
    """
    pass

def ensure_local_bible_file(local_path):
    """
    Если локальный файл не существует, создает его с заголовками.
    Этот вариант используется для резервного копирования или временных файлов.
    """
    if not os.path.exists(local_path):
        try:
            directory = os.path.dirname(local_path)
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            wb = Workbook()
            ws = wb.active
            ws.append(["FAQ", "Answers", "Verification"])
            wb.save(local_path)
            logger.info(f"Локальный файл {local_path} создан с заголовками.")
        except Exception as e:
            logger.error(f"Ошибка при создании локального файла {local_path}: {e}")
            raise

def save_bible_pair(question, answer):
    """
    Добавляет новую строку в Google Sheets таблицу Bible.xlsx с вопросом, ответом и статусом "Check".
    Если возникает ошибка записи, создается временный локальный файл Temp_Bible.xlsx.
    Каждый день (при первом сохранении после полуночи) создается резервная копия Reserv_Bible_YYYYMMDD.xlsx.
    """
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
        logger.info(f"Новая пара добавлена в Google Sheets: FAQ='{question}', Answers='{answer}', Verification='Check'. Ответ API: {result}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении пары в Bible.xlsx: {e}")
        try:
            temp_file = os.path.join(os.getcwd(), "Temp_Bible.xlsx")
            ensure_local_bible_file(temp_file)
            wb = load_workbook(temp_file)
            ws = wb.active
            ws.append([question, answer, "Check"])
            wb.save(temp_file)
            logger.error(f"Временный файл {temp_file} создан из-за ошибки записи в оригинальный файл.")
        except Exception as e2:
            logger.error(f"Ошибка при создании временного файла Temp_Bible.xlsx: {e2}")
        raise

def get_rule():
    """
    Возвращает объединённый текст всех внутренних инструкций (строки, где FAQ='-' и Verification='RULE').
    Если таких строк нет, возвращает "<no_rules_found>".
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
