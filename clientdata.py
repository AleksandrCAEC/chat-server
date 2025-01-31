import os
import pandas as pd
from datetime import datetime
import logging
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),  # Логи записываются в файл app.log
        logging.StreamHandler()  # Логи выводятся в консоль
    ]
)
logger = logging.getLogger(__name__)

# Путь к папке CAEC_API_Data/BIG_DATA
BIG_DATA_PATH = "./CAEC_API_Data/BIG_DATA"

# Путь к файлу ClientData.xlsx
CLIENT_DATA_FILE = os.path.join(BIG_DATA_PATH, "ClientData.xlsx")

# Логирование текущего рабочего каталога
logger.info(f"Текущий рабочий каталог: {os.getcwd()}")

# Проверка существования файла ClientData.xlsx
if not os.path.exists(CLIENT_DATA_FILE):
    logger.error(f"Файл {CLIENT_DATA_FILE} не найден! Проверьте путь и права доступа.")
    sys.exit(1)  # Завершаем программу с ошибкой, если файл отсутствует

# Загрузка ClientData.xlsx
def load_client_data():
    try:
        logger.info(f"Загрузка данных из файла: {CLIENT_DATA_FILE}")

        # Загрузка данных из файла
        df = pd.read_excel(CLIENT_DATA_FILE)

        # Проверка, что файл не пуст
        if df.empty:
            logger.error("Файл ClientData.xlsx пуст или не содержит данных!")
            return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])
        else:
            logger.info(f"Загруженные данные: {df}")
            return df

    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])
