# bible.py
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def load_bible_data():
    """
    Загружает данные из файла Bible.xlsx.
    Файл ожидается по пути: ./CAEC_API_Data/BIG_DATA/Bible.xlsx
    Лист: "Bible"
    Столбцы:
      - FAQ
      - Answers
      - Verification
    """
    bible_path = "./CAEC_API_Data/BIG_DATA/Bible.xlsx"
    try:
        df = pd.read_excel(bible_path, sheet_name="Bible")
        logger.info(f"Данные Bible.xlsx успешно загружены: {df.shape[0]} записей.")
        return df
    except Exception as e:
        logger.error(f"Ошибка чтения Bible.xlsx: {e}")
        return None
