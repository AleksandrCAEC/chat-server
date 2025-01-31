import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime
import logging

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

# Убедимся, что директория BIG_DATA существует
os.makedirs(BIG_DATA_PATH, exist_ok=True)

# Путь к файлу ClientData.xlsx
CLIENT_DATA_FILE = os.path.join(BIG_DATA_PATH, "ClientData.xlsx")

# Инициализация ClientData.xlsx, если файл не существует
def initialize_client_data():
    if not os.path.exists(CLIENT_DATA_FILE):
        columns = ["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"]
        df = pd.DataFrame(columns=columns)
        df.to_excel(CLIENT_DATA_FILE, index=False)
        logger.info(f"Инициализирован новый файл ClientData.xlsx по пути: {CLIENT_DATA_FILE}")

# Загрузка ClientData.xlsx
def load_client_data():
    try:
        logger.info(f"Загрузка данных из файла: {CLIENT_DATA_FILE}")
        df = pd.read_excel(CLIENT_DATA_FILE)
        logger.info(f"Загруженные данные: {df}")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        initialize_client_data()
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

# Верификация кода клиента
def verify_client_code(code):
    try:
        logger.info(f"Поиск клиента с кодом: {code}")
        df = load_client_data()

        # Убедимся, что столбец "Client Code" существует
        if "Client Code" not in df.columns:
            logger.error("Столбец 'Client Code' отсутствует в файле ClientData.xlsx")
            return None

        # Поиск клиента по коду
        client_data = df[df["Client Code"].astype(str).str.strip() == code.strip()]

        if not client_data.empty:
            logger.info(f"Клиент найден: {client_data.iloc[0].to_dict()}")
            return client_data.iloc[0].to_dict()
        else:
            logger.info(f"Клиент с кодом {code} не найден")
            return None
    except Exception as e:
        logger.error(f"Ошибка при верификации кода: {e}")
        return None

# Инициализация системы при первом запуске
initialize_client_data()
