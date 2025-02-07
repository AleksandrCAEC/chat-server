# client_caec.py
import os
import pandas as pd
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, numbers
import logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from io import BytesIO
from config import CLIENT_DATA_PATH  # Импортируем путь к ClientData.xlsx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("client_caec.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Функция для отправки уведомлений через Telegram
def send_notification(message):
    try:
        import requests
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if telegram_bot_token and telegram_chat_id:
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
            requests.post(url, json=payload)
    except Exception as ex:
        logger.error(f"Ошибка при отправке уведомления: {ex}")

# Константа для директории файлов клиента
CLIENT_FILES_DIR = "./CAEC_API_Data/BIG_DATA/Data_CAEC_client/"

if not os.path.exists(CLIENT_FILES_DIR):
    try:
        os.makedirs(CLIENT_FILES_DIR, exist_ok=True)
        logger.info(f"Директория {CLIENT_FILES_DIR} создана.")
    except Exception as e:
        logger.error(f"Ошибка при создании директории {CLIENT_FILES_DIR}: {e}")
        send_notification(f"Ошибка при создании директории {CLIENT_FILES_DIR}: {e}")

# Идентификатор папки на Google Drive (если используется)
GOOGLE_DRIVE_FOLDER_ID = "11cQYLDGKlu2Rn_9g8R_4xNA59ikhvJpS"

def get_drive_service():
    try:
        credentials = Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build("drive", "v3", credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Drive API: {e}")
        send_notification(f"Ошибка инициализации Google Drive API: {e}")
        return None

def find_file_id(drive_service, file_name):
    try:
        response = drive_service.files().list(
            q=f"name='{file_name}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents",
            fields="files(id, name)"
        ).execute()
        files = response.get("files", [])
        if files:
            return files[0]["id"]
        return None
    except Exception as e:
        logger.error(f"Ошибка при поиске файла на Google Drive: {e}")
        send_notification(f"Ошибка при поиске файла {file_name} на Google Drive: {e}")
        return None

def upload_or_update_file(file_name, file_stream):
    try:
        drive_service = get_drive_service()
        if not drive_service:
            raise Exception("Google Drive API не инициализирован.")
        file_id = find_file_id(drive_service, file_name)
        if file_id:
            media = MediaIoBaseUpload(file_stream, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            drive_service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            logger.info(f"Файл {file_name} успешно обновлён на Google Drive.")
        else:
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
        logger.error(f"Ошибка при загрузке/обновлении файла {file_name} на Google Drive: {e}")
        send_notification(f"Ошибка при загрузке/обновлении файла {file_name} на Google Drive: {e}")

def download_client_file(file_name, local_path):
    """
    Пытается скачать файл с Google Drive и сохранить его по local_path.
    Возвращает True, если скачивание успешно, иначе False.
    """
    try:
        drive_service = get_drive_service()
        file_id = find_file_id(drive_service, file_name)
        if file_id:
            from googleapiclient.http import MediaIoBaseDownload
            fh = BytesIO()
            request = drive_service.files().get_media(fileId=file_id)
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logger.info(f"Скачивание {int(status.progress() * 100)}% завершено.")
            with open(local_path, "wb") as f:
                f.write(fh.getvalue())
            logger.info(f"Файл {file_name} скачан с Google Drive и сохранён в {local_path}.")
            return True
        else:
            logger.info(f"Файл {file_name} не найден на Google Drive.")
            return False
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла {file_name} с Google Drive: {e}")
        send_notification(f"Ошибка при скачивании файла {file_name} с Google Drive: {e}")
        return False

def load_client_data():
    if not os.path.exists(CLIENT_DATA_PATH):
        try:
            from clientdata import load_client_data as load_from_gs
            df = load_from_gs()
            df.astype(str).to_excel(CLIENT_DATA_PATH, index=False)
            return df
        except Exception as e:
            logger.error(f"Ошибка создания ClientData.xlsx: {e}")
            send_notification(f"Ошибка создания ClientData.xlsx: {e}")
            return pd.DataFrame()
    try:
        df = pd.read_excel(CLIENT_DATA_PATH)
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из ClientData.xlsx: {e}")
        send_notification(f"Ошибка загрузки данных из ClientData.xlsx: {e}")
        return pd.DataFrame()

def create_client_file(client_code, client_data):
    try:
        file_name = f"Client_{client_code}.xlsx"
        # Создаем файл через Google Sheets API
        sheets_service = get_sheets_service()
        # Подготавливаем данные: заголовки и начальные данные клиента
        values = [
            ["Client", "Assistant", "Client Code", "Name", "Phone", "Email", "Created Date"],
            ["", "", client_data["Client Code"], client_data["Name"], client_data["Phone"], client_data["Email"], client_data["Created Date"]]
        ]
        body = {
            "properties": {
                "title": file_name
            },
            "sheets": [
                {
                    "data": [
                        {
                            "startRow": 0,
                            "startColumn": 0,
                            "rowData": [{"values": [{"userEnteredValue": {"stringValue": cell}} for cell in row]} for row in values]
                        }
                    ]
                }
            ]
        }
        result = sheets_service.spreadsheets().create(body=body, fields="spreadsheetId").execute()
        spreadsheet_id = result.get("spreadsheetId")
        logger.info(f"Создан файл клиента {file_name} с spreadsheetId: {spreadsheet_id}")
        # Перемещаем файл в нужную папку через Drive API
        drive_service = get_drive_service()
        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=GOOGLE_DRIVE_FOLDER_ID,
            fields="id, parents"
        ).execute()
        return spreadsheet_id
    except Exception as e:
        logger.error(f"Ошибка при создании файла клиента {file_name}: {e}")
        send_notification(f"Ошибка при создании файла клиента {client_code}: {e}")
        raise

def add_message_to_client_file(client_code, message, is_assistant=False):
    """
    Добавляет новое сообщение в Google Sheets файл клиента Client_{client_code}.xlsx.
    Если файл уже существует, данные дописываются в конец.
    Если возникает ошибка записи, создаётся временный файл Temp_Client_{client_code}.xlsx,
    и отправляется уведомление через Telegram.
    """
    try:
        sheets_service = get_sheets_service()
        spreadsheet_id = find_client_file_id(client_code)
        if not spreadsheet_id:
            # Если файл не найден на Google Drive, создаём его
            from clientdata import verify_client_code
            client_data = verify_client_code(client_code)
            if not client_data:
                raise Exception(f"Данные клиента {client_code} не найдены.")
            spreadsheet_id = create_client_file(client_code, client_data)
        current_time = datetime.now().strftime("%d.%m.%y %H:%M")
        if is_assistant:
            new_row = [ "", f"{current_time} - {message}", "", "", "", "", "" ]
        else:
            new_row = [ f"{current_time} - {message}", "", "", "", "", "", "" ]
        body = {"values": [new_row]}
        result = sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A:G",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
        logger.info(f"Сообщение добавлено в файл клиента {client_code}. Ответ API: {result}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении сообщения в файл клиента {client_code}: {e}")
        send_notification(f"Ошибка при добавлении сообщения в файл клиента {client_code}: {e}")
        try:
            temp_file_name = f"Temp_Client_{client_code}.xlsx"
            # Создаем временный файл через создание нового Google Sheets файла
            from clientdata import verify_client_code
            client_data = verify_client_code(client_code)
            if not client_data:
                raise Exception(f"Данные клиента {client_code} не найдены.")
            temp_spreadsheet_id = create_client_file(f"Temp_{client_code}", client_data)
            body = {"values": [new_row]}
            result = sheets_service.spreadsheets().values().append(
                spreadsheetId=temp_spreadsheet_id,
                range="Sheet1!A:G",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body
            ).execute()
            logger.error(f"Временный файл для клиента {client_code} создан. Ответ API: {result}")
            send_notification(f"Временный файл для клиента {client_code} создан из-за ошибки записи.")
        except Exception as e2:
            logger.error(f"Ошибка при создании временного файла для клиента {client_code}: {e2}")
            send_notification(f"Ошибка при создании временного файла для клиента {client_code}: {e2}")
            raise

def find_client_file_id(client_code):
    """
    Ищет Google Sheets файл клиента по имени, который содержит "Client_{client_code}".
    Возвращает spreadsheetId, если файл найден, иначе None.
    """
    file_name_fragment = f"Client_{client_code}"
    drive_service = get_drive_service()
    try:
        query = f"name contains '{file_name_fragment}' and '{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.spreadsheet'"
        response = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = response.get("files", [])
        if files:
            logger.info(f"Найден файл для клиента {client_code}: {files[0]['name']}")
            return files[0]["id"]
        logger.info(f"Файл для клиента {client_code} не найден на Google Drive.")
        return None
    except Exception as e:
        logger.error(f"Ошибка при поиске файла для клиента {client_code}: {e}")
        send_notification(f"Ошибка при поиске файла для клиента {client_code}: {e}")
        raise

def handle_client(client_code):
    try:
        logger.info(f"Обработка клиента с кодом: {client_code}")
        df = load_client_data()
        client_data = df[df["Client Code"] == client_code]
        if client_data.empty:
            logger.warning(f"Клиент с кодом {client_code} не найден в ClientData.xlsx.")
            send_notification(f"Клиент с кодом {client_code} не найден в ClientData.xlsx.")
        else:
            spreadsheet_id = find_client_file_id(client_code)
            if not spreadsheet_id:
                logger.info(f"Файл для клиента {client_code} не найден на Google Drive. Создаем новый файл.")
                spreadsheet_id = create_client_file(client_code, client_data.iloc[0].to_dict())
            else:
                logger.info(f"Файл для клиента {client_code} найден на Google Drive.")
    except Exception as e:
        logger.error(f"Ошибка при обработке клиента {client_code}: {e}")
        send_notification(f"Ошибка при обработке клиента {client_code}: {e}")

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
        send_notification(f"Ошибка при обработке всех клиентов: {e}")

if __name__ == "__main__":
    handle_all_clients()
