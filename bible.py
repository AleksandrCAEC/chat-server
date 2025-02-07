import os
import pandas as pd
from openpyxl import Workbook, load_workbook
import logging

logger = logging.getLogger(__name__)

BIBLE_FILE_PATH = "./CAEC_API_Data/BIG_DATA/Bible.xlsx"

def load_bible_data():
    if not os.path.exists(BIBLE_FILE_PATH):
        try:
            os.makedirs(os.path.dirname(BIBLE_FILE_PATH), exist_ok=True)
            wb = Workbook()
            ws = wb.active
            ws.append(["FAQ", "Answers", "Verification"])
            wb.save(BIBLE_FILE_PATH)
            logger.info(f"Файл {BIBLE_FILE_PATH} создан с заголовками.")
        except Exception as e:
            logger.error(f"Ошибка при создании файла Bible.xlsx: {e}")
            return None
    try:
        df = pd.read_excel(BIBLE_FILE_PATH)
        return df
    except Exception as e:
        logger.error(f"Ошибка при загрузке Bible.xlsx: {e}")
        return None

def save_bible_pair(question, answer):
    if not os.path.exists(BIBLE_FILE_PATH):
        # Создаем файл, если его нет
        load_bible_data()
    try:
        wb = load_workbook(BIBLE_FILE_PATH)
        ws = wb.active
        ws.append([question, answer, "Check"])
        wb.save(BIBLE_FILE_PATH)
        logger.info(f"Новая пара добавлена в Bible.xlsx: Вопрос='{question}', Ответ='{answer}', Verification='Check'")
    except Exception as e:
        logger.error(f"Ошибка при сохранении пары в Bible.xlsx: {e}")
        raise
