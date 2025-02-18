import os
import pandas as pd
from openpyxl import Workbook, load_workbook
import logging
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Получаем путь к файлу учетных данных из переменной окружения или используем "./service_account.json" по умолчанию
default_path = "./service_account.json"
service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", default_path)
service_account_path = os.path.abspath(service_account_path)
if not os.path.exists(service_account_path):
    logger.warning(f"Файл учетных данных {service_account_path} не найден. Проверьте, что он существует, или укажите корректный путь.")
else:
    logger.info(f"Найден файл учетных данных: {service_account_path}")

# Идентификатор таблицы Google Sheets (из вашей ссылки)
BIBLE_SPREADSHEET_ID = "1QB3Jv7cL5hNwDKx9rQF6FCrKHW7IHPAqrUg7FIvY7Dk"

def get_sheets_service():
    """
    Создает и возвращает объект сервиса Google Sheets.
    """
    try:
        credentials = Credentials.from_service_account_file(service_account_path)
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def load_bible_data():
    """
    Загружает данные из листа "Bible" (столбцы: FAQ, Answers, Verification, D-столбец не используется) 
    и возвращает их в виде DataFrame.
    """
    try:
        service = get_sheets_service()
        range_name = "Bible!A2:C"  # Только FAQ (A), Answers (B), Verification (C). Если вам нужен столбец D, меняйте на A2:D
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
        logger.error(f"Ошибка при загрузке данных из Bible.xlsx: {e}")
        return None

def ensure_local_bible_file(local_path):
    """
    Создает локальный файл, если нужно (не обязательно использовать).
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
    Добавляет новую строку (FAQ=question, Answers=answer, Verification="Check") в Google Sheets.
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
        logger.info(f"Новая пара добавлена: FAQ='{question}', Answers='{answer}', Verification='Check'. Результат: {result}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении пары в Bible: {e}")
        # Пытаемся сохранить в локальный файл
        try:
            temp_file = os.path.join(os.getcwd(), "Temp_Bible.xlsx")
            ensure_local_bible_file(temp_file)
            wb = load_workbook(temp_file)
            ws = wb.active
            ws.append([question, answer, "Check"])
            wb.save(temp_file)
            logger.error(f"Временный файл {temp_file} создан.")
        except Exception as e2:
            logger.error(f"Ошибка при создании временного файла Temp_Bible.xlsx: {e2}")
        raise

def get_rule():
    """
    Возвращает все внутренние инструкции (строки, где FAQ='-' и Verification='RULE'),
    объединённые в один текст. Если таких строк нет, возвращает <no_rules_found>.
    """
    df = load_bible_data()
    if df is None:
        return "<no_rules_found>"
    # Фильтруем строки, где FAQ='-' и Verification='RULE' (без учета регистра)
    internal_rules = df[
        (df["FAQ"].str.strip() == "-") &
        (df["Verification"].str.upper() == "RULE")
    ]
    if internal_rules.empty:
        return "<no_rules_found>"
    # Возвращаем склеенный текст из столбца Answers
    lines = internal_rules["Answers"].tolist()
    return "\n".join(lines)

if __name__ == "__main__":
    df = load_bible_data()
    logger.info(df)
