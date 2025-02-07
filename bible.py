# bible.py
import os
import logging
import pandas as pd
from openpyxl import Workbook, load_workbook

logger = logging.getLogger(__name__)

# Задайте путь к файлу Bible.xlsx (укажите нужный путь, например, согласно вашей архитектуре)
BIBLE_FILE_PATH = "./CAEC_API_Data/BIG_DATA/Bible.xlsx"

def load_bible_data():
    """
    Загружает данные из файла Bible.xlsx.
    Если файл не существует, создаёт его с заголовками: FAQ, Answers, Verification.
    Возвращает DataFrame с данными или None в случае ошибки.
    """
    if not os.path.exists(BIBLE_FILE_PATH):
        try:
            # Создаем новую книгу и добавляем заголовки
            wb = Workbook()
            ws = wb.active
            ws.append(["FAQ", "Answers", "Verification"])
            # Создаем директорию, если ее нет
            os.makedirs(os.path.dirname(BIBLE_FILE_PATH), exist_ok=True)
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
    """
    Добавляет новую строку с вопросом, ответом и статусом "Check" в файл Bible.xlsx.
    
    :param question: Текст вопроса.
    :param answer: Текст ответа.
    :raises: Exception, если возникает ошибка записи.
    """
    # Если файла не существует, создаем его с заголовками
    if not os.path.exists(BIBLE_FILE_PATH):
        try:
            wb = Workbook()
            ws = wb.active
            ws.append(["FAQ", "Answers", "Verification"])
            os.makedirs(os.path.dirname(BIBLE_FILE_PATH), exist_ok=True)
            wb.save(BIBLE_FILE_PATH)
            logger.info(f"Файл {BIBLE_FILE_PATH} создан для сохранения пар.")
        except Exception as e:
            logger.error(f"Ошибка при создании файла Bible.xlsx: {e}")
            raise
    try:
        wb = load_workbook(BIBLE_FILE_PATH)
        ws = wb.active
        # Добавляем новую строку с вопросом, ответом и статусом "Check"
        ws.append([question, answer, "Check"])
        wb.save(BIBLE_FILE_PATH)
        logger.info(f"Новая пара добавлена: FAQ='{question}', Answers='{answer}', Verification='Check'")
    except Exception as e:
        logger.error(f"Ошибка при сохранении пары в Bible.xlsx: {e}")
        raise
