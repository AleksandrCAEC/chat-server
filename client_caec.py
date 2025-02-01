import os
import pandas as pd
from openpyxl import Workbook
import logging
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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

# ID папки на Google Drive
GOOGLE_DRIVE_FOLDER_ID = "11cQYLDGKlu2Rn_9g8R_4xNA59ikhvJpS"

# Инициализация Google Drive API
def get_drive_service():
    try:
        credentials = Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build("drive", "v3", credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Drive API: {e}")
        return None

# Загрузка файла на Google Drive
def upload_to_google_drive(file_path, file_name):
    try:
        drive_service = get_drive_service()
        if not drive_service:
            raise Exception("Google Drive API не инициализирован.")

        file_metadata = {
            "name": file_name,
            "parents": [GOOGLE_DRIVE_FOLDER_ID]
        }

        media = MediaFileUpload(file_path, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        logger.info(f"Файл {file_name} успешно загружен на Google Drive. ID файла: {file.get('id')}")
        return file.get("id")
    except Exception as e:
        logger.error(f"Ошибка загрузки файла на Google Drive: {e}")
        return None

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
        # Убираем дублирование "CAEC" в имени файла
        file_name = f"Client_{client_code}.xlsx"
        file_path = os.path.join("temp", file_name)  # Временная папка для хранения файла перед загрузкой

        # Создаем временную папку, если она не существует
        if not os.path.exists("temp"):
            os.makedirs("temp")

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

        # Загружаем файл на Google Drive
        upload_to_google_drive(file_path, file_name)

        # Удаляем временный файл
        os.remove(file_path)
        logger.info(f"Временный файл {file_path} удален.")

        return file_name
    except Exception as e:
        logger.error(f"Ошибка при создании файла клиента: {e}")
        return None

# Функция для поиска клиента по коду и создания/обновления его файла
def handle_client(client_code):
    try:
        logger.info(f"Обработка клиента с кодом: {client_code}")
        df = load_client_data()

        # Ищем клиента по коду
        client_data = df[df["Client Code"] == client_code]

        if not client_data.empty:
            client_data = client_data.iloc[0].to_dict()

            # Создаем файл клиента
            file_name = f"Client_{client_code}.xlsx"
            logger.info(f"Создание файла клиента: {file_name}")
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
