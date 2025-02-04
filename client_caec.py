import os
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, numbers
import logging
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO

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
CLIENT_DATA_PATH = "./CAEC_API_Data/BIG_DATA/ClientData.xlsx"

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

# Поиск файла на Google Drive по имени
def find_file_id(drive_service, file_name):
    try:
        response = drive_service.files().list(
            q=f"name='{file_name}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents",
            fields="files(id, name)"
        ).execute()
        files = response.get("files", [])
        if files:
            return files[0]["id"]  # Возвращаем ID первого найденного файла
        return None
    except Exception as e:
        logger.error(f"Ошибка при поиске файла на Google Drive: {e}")
        return None

# Загрузка или обновление файла на Google Drive
def upload_or_update_file(file_name, file_stream):
    try:
        drive_service = get_drive_service()
        if not drive_service:
            raise Exception("Google Drive API не инициализирован.")

        # Проверяем, существует ли файл локально
        if not os.path.exists(file_name):
            logger.error(f"Файл {file_name} не найден локально.")
            return

        # Ищем файл на Google Drive
        file_id = find_file_id(drive_service, file_name)

        if file_id:
            # Если файл существует, обновляем его
            media = MediaIoBaseUpload(file_stream, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            drive_service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            logger.info(f"Файл {file_name} успешно обновлён на Google Drive.")
        else:
            # Если файл не существует, создаем новый
            file_metadata = {
                "name": file_name,
                "parents": [GOOGLE_DRIVE_FOLDER_ID]
            }
            media = MediaIoBaseUpload(file_stream, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id"
            ).execute()
            logger.info(f"Файл {file_name} успешно создан и загружен на Google Drive. ID файла: {file.get('id')}")
    except Exception as e:
        logger.error(f"Ошибка при загрузке/обновлении файла на Google Drive: {e}")

# Функция для добавления сообщения в файл клиента
def add_message_to_client_file(client_code, message, is_assistant=False):
    try:
        file_name = f"./CAEC_API_Data/Data_CAEC_Client/Client_{client_code}.xlsx"

        # Создаем директорию, если она не существует
        os.makedirs(os.path.dirname(file_name), exist_ok=True)

        # Открываем существующий файл или создаем новый, если он не существует
        if os.path.exists(file_name):
            wb = load_workbook(file_name)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            # Записываем заголовки, если файл новый
            ws.append(["Timestamp", "Message", "is_assistant"])

        # Добавляем новое сообщение
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append([timestamp, message, is_assistant])

        # Сохраняем файл
        wb.save(file_name)

        logger.info(f"Сообщение добавлено в файл клиента {client_code}.")
    except Exception as e:
        logger.error(f"Ошибка при добавлении сообщения в файл клиента: {e}")

# Функция для загрузки данных клиента
def load_client_data(client_code):
    try:
        file_name = f"./CAEC_API_Data/Data_CAEC_Client/Client_{client_code}.xlsx"
        if not os.path.exists(file_name):
            logger.info(f"Файл клиента {client_code} не найден. Клиент новый.")
            return None
        df = pd.read_excel(file_name)
        logger.info(f"Данные клиента {client_code} загружены: {df.head()}")
        return df
    except Exception as e:
        logger.error(f"Ошибка при чтении файла клиента {client_code}: {e}")
        return None
