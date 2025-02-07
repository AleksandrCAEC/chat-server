# bible.py
import os
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, numbers
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Определяем текущий рабочий каталог и выводим его для отладки
current_dir = os.getcwd()
logger.info(f"Текущий рабочий каталог: {current_dir}")

# Формируем абсолютный путь к файлу Bible.xlsx
BIBLE_FILE_PATH = os.path.join(current_dir, "CAEC_API_Data", "BIG_DATA", "Bible.xlsx")
logger.info(f"Путь к Bible.xlsx: {BIBLE_FILE_PATH}")

def ensure_bible_file():
    """
    Проверяет наличие файла Bible.xlsx и создаёт его с заголовками, если отсутствует.
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
        logger.info(f"Bible.xlsx загружен. Количество записей: {len(df)}")
        return df
    except Exception as e:
        logger.error(f"Ошибка при загрузке Bible.xlsx: {e}")
        return None

def save_bible_pair(question, answer):
    """
    Добавляет новую строку в Bible.xlsx с вопросом, ответом и статусом "Check".
    После сохранения логирует количество строк.
    
    :param question: Текст вопроса.
    :param answer: Текст ответа.
    :raises Exception: При ошибке записи.
    """
    try:
        ensure_bible_file()
        wb = load_workbook(BIBLE_FILE_PATH)
        ws = wb.active
        # Добавляем новую строку с вопросом, ответом и статусом "Check"
        ws.append([question, answer, "Check"])
        wb.save(BIBLE_FILE_PATH)
        logger.info(f"Новая пара добавлена: FAQ='{question}', Answers='{answer}', Verification='Check'")
        
        # Повторно открываем файл и считаем число строк для проверки
        wb2 = load_workbook(BIBLE_FILE_PATH)
        ws2 = wb2.active
        row_count = ws2.max_row
        logger.info(f"После сохранения, количество строк в Bible.xlsx: {row_count}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении пары в Bible.xlsx: {e}")
        raise
