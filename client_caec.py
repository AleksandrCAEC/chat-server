import os
import pandas as pd
from openpyxl import Workbook
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("client_caec.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Путь к файлу ClientData.xlsx
CLIENT_DATA_PATH = "ClientData.xlsx"

# Путь к директории для сохранения файлов клиентов
CLIENT_FILES_DIR = "./CAEC_API_Data/Data_CAEC_client"

# Создаем директорию, если она не существует
if not os.path.exists(CLIENT_FILES_DIR):
    os.makedirs(CLIENT_FILES_DIR)
    logger.info(f"Создана директория для файлов клиентов: {CLIENT_FILES_DIR}")

# Функция для загрузки данных из ClientData.xlsx
def load_client_data():
    try:
        logger.info("Загрузка данных из ClientData.xlsx...")
        df = pd.read_excel(CLIENT_DATA_PATH)
        logger.info(f"Данные загружены: {df}")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из ClientData.xlsx: {e}")
        return pd.DataFrame()

# Функция для создания файла Client_CAECxxxxxxx.xlsx
def create_client_file(client_code, client_data):
    try:
        file_name = f"Client_CAEC{client_code}.xlsx"
        file_path = os.path.join(CLIENT_FILES_DIR, file_name)
        logger.info(f"Создание файла клиента: {file_path}")

        # Создаем новый Excel-файл
        wb = Workbook()
        ws = wb.active

        # Записываем заголовки
        ws.append(["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

        # Записываем данные клиента
        ws.append([
            client_data["Client Code"],
            client_data["Name"],
            client_data["Phone"],
            client_data["Email"],
            client_data["Created Date"],
            client_data["Last Visit"],
            client_data["Activity Status"]
        ])

        # Сохраняем файл
        wb.save(file_path)
        logger.info(f"Файл {file_path} успешно создан.")
        return file_path
    except Exception as e:
        logger.error(f"Ошибка при создании файла клиента: {e}")
        return None

# Функция для обновления данных клиента в Client_CAECxxxxxxx.xlsx
def update_client_file(client_code, new_data):
    try:
        file_name = f"Client_CAEC{client_code}.xlsx"
        file_path = os.path.join(CLIENT_FILES_DIR, file_name)
        logger.info(f"Обновление файла клиента: {file_path}")

        # Загружаем существующий файл
        wb = load_workbook(file_path)
        ws = wb.active

        # Добавляем новую строку с обновленными данными
        ws.append([
            new_data["Client Code"],
            new_data["Name"],
            new_data["Phone"],
            new_data["Email"],
            new_data["Created Date"],
            new_data["Last Visit"],
            new_data["Activity Status"]
        ])

        # Сохраняем изменения
        wb.save(file_path)
        logger.info(f"Файл {file_path} успешно обновлен.")
    except Exception as e:
        logger.error(f"Ошибка при обновлении файла клиента: {e}")

# Функция для поиска клиента по коду и создания/обновления его файла
def handle_client(client_code):
    try:
        logger.info(f"Обработка клиента с кодом: {client_code}")
        df = load_client_data()

        # Ищем клиента по коду
        client_data = df[df["Client Code"] == client_code]

        if not client_data.empty:
            client_data = client_data.iloc[0].to_dict()

            # Проверяем, существует ли файл клиента
            file_name = f"Client_CAEC{client_code}.xlsx"
            file_path = os.path.join(CLIENT_FILES_DIR, file_name)
            if os.path.exists(file_path):
                logger.info(f"Файл клиента {file_path} уже существует. Обновляем данные.")
                update_client_file(client_code, client_data)
            else:
                logger.info(f"Файл клиента {file_path} не существует. Создаем новый.")
                create_client_file(client_code, client_data)
        else:
            logger.warning(f"Клиент с кодом {client_code} не найден в ClientData.xlsx.")
    except Exception as e:
        logger.error(f"Ошибка при обработке клиента: {e}")

# Функция для обработки всех клиентов из ClientData.xlsx
def handle_all_clients():
    try:
        logger.info("Обработка всех клиентов из ClientData.xlsx...")
        df = load_client_data()

        for _, row in df.iterrows():
            client_code = row["Client Code"]
            handle_client(client_code)

        logger.info("Все клиенты обработаны.")
    except Exception as e:
        logger.error(f"Ошибка при обработке всех клиентов: {e}")

# Пример использования
if __name__ == "__main__":
    # Обработка всех клиентов при запуске
    handle_all_clients()
