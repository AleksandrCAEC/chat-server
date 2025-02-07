# bible.py
import os
import pandas as pd
import logging
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
    Предполагается, что данные находятся в листе с именем "Bible" и в диапазоне A2:C,
    где строка 1 содержит заголовки: FAQ, Answers, Verification.
    """
    try:
        service = get_sheets_service()
        # Задаем диапазон: данные начинаются со 2-й строки (заголовки в 1-й)
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

def save_bible_pair(question, answer):
    """
    Добавляет новую строку в Google Sheets таблицу Bible.xlsx с вопросом, ответом и статусом "Check".
    
    :param question: Текст вопроса.
    :param answer: Текст ответа.
    :raises Exception: При ошибке записи.
    """
    try:
        service = get_sheets_service()
        # Подготовим данные: новая строка с [question, answer, "Check"]
        new_row = [[question, answer, "Check"]]
        body = {"values": new_row}
        # Используем метод append для добавления новой строки в лист "Bible"
        result = service.spreadsheets().values().append(
            spreadsheetId=BIBLE_SPREADSHEET_ID,
            range="Bible!A:C",  # Область, в которую добавляем данные
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
        logger.info(f"Новая пара добавлена: FAQ='{question}', Answers='{answer}', Verification='Check'. Ответ API: {result}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении пары в Bible.xlsx через Google Sheets API: {e}")
        raise
