# bible.py
import os
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, numbers
import logging

logger = logging.getLogger(__name__)

# Формируем абсолютный путь к файлу Bible.xlsx, относительно рабочей директории
BIBLE_FILE_PATH = os.path.join(os.getcwd(), "CAEC_API_Data", "BIG_DATA", "Bible.xlsx")

def ensure_bible_file():
    """
    Проверяет наличие файла Bible.xlsx и создаёт его, если отсутствует, с нужными заголовками.
    """
    directory = os.path.dirname(BIBLE_FILE_PATH)
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Директория {directory} создана.")
        except Exception as e:
            logger.error(f"Ошибка при создании директории {directory}: {e}")
            raise

    if not os.path.exists(BIBLE_FILE_PATH):
        try:
            wb = Workbook()
            ws = wb.active
            ws.append(["FAQ", "Answers", "Verification"])
            wb.save(BIBLE_FILE_PATH)
            logger.info(f"Файл {BIBLE_FILE_PATH} создан с заголовками.")
        except Exception as e:
            logger.error(f"Ошибка при создании файла Bible.xlsx: {e}")
            raise

def load_bible_data():
    """
    Загружает данные из файла Bible.xlsx в виде DataFrame.
    Если файла нет, создает его.
    """
    try:
        ensure_bible_file()
        df = pd.read_excel(BIBLE_FILE_PATH)
        return df
    except Exception as e:
        logger.error(f"Ошибка при загрузке Bible.xlsx: {e}")
        return None

def save_bible_pair(question, answer):
    """
    Добавляет новую строку в Bible.xlsx с вопросом, ответом и статусом "Check".
    После сохранения открывает файл и логирует количество строк для отладки.
    
    :param question: Текст вопроса.
    :param answer: Текст ответа.
    :raises Exception: При ошибке записи.
    """
    try:
        ensure_bible_file()
        wb = load_workbook(BIBLE_FILE_PATH)
        ws = wb.active
        ws.append([question, answer, "Check"])
        wb.save(BIBLE_FILE_PATH)
        logger.info(f"Новая пара добавлена: FAQ='{question}', Answers='{answer}', Verification='Check'")
        # Дополнительная проверка: открыть файл повторно и посчитать количество строк
        wb2 = load_workbook(BIBLE_FILE_PATH)
        ws2 = wb2.active
        row_count = ws2.max_row
        logger.info(f"После сохранения в Bible.xlsx, количество строк: {row_count}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении пары в Bible.xlsx: {e}")
        raise
