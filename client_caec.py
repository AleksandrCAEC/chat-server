# client_caec.py
import os
import pandas as pd
from datetime import datetime
import logging
from io import BytesIO
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from config import CLIENT_DATA_PATH  # Путь к ClientData.xlsx (локальный кэш, если используется)
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("client_caec.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Функция для отправки уведомлений через Telegram (используется и в других модулях)
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

# Для работы с клиентскими файлами в Google Sheets
# Все клиентские файлы будут храниться в папке на Google Drive; здесь мы используем Google Sheets API для работы с каждым клиентским файлом.

# Идентификатор папки на Google Drive (где хранятся клиентские файлы)
GOOGLE_DRIVE_FOLDER_ID = "11cQYLDGKlu2Rn_9g8R_4xNA59ikhvJpS"

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        send_notification(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def get_drive_service():
    try:
        from google.oauth2.service_account import Credentials
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        service = build('drive', 'v3', credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Drive API: {e}")
        send_notification(f"Ошибка инициализации Google Drive API: {e}")
        raise

def find_client_file_id(client_code):
    """
    Ищет Google Sheets файл для клиента по имени.
    Файл должен содержать фрагмент "Client_{client_code}" в имени.
    Возвращает spreadsheetId, если найден, иначе None.
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

def create_client_file(client_code, client_data):
    """
    Создает новый Google Sheets файл для клиента с начальными данными.
    Использует Google Sheets API для создания таблицы с заголовками.
    Возвращает spreadsheetId нового файла.
    """
    sheets_service = get_sheets_service()
    file_title = f"Client_{client_code}"
    # Подготавливаем данные: заголовки и начальные данные
    values = [
        ["Client", "Assistant", "Client Code", "Name", "Phone", "Email", "Created Date"],
        ["", "", client_data["Client Code"], client_data["Name"], client_data["Phone"], client_data["Email"], client_data["Created Date"]]
    ]
    # Формируем тело запроса
    body = {
        "properties": {
            "title": file_title
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
    try:
        result = sheets_service.spreadsheets().create(body=body, fields="spreadsheetId").execute()
        spreadsheet_id = result.get("spreadsheetId")
        logger.info(f"Создан файл клиента {file_title} с spreadsheetId: {spreadsheet_id}")
        # Перемещаем файл в нужную папку через Drive API
        drive_service = get_drive_service()
        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=GOOGLE_DRIVE_FOLDER_ID,
            fields="id, parents"
        ).execute()
        return spreadsheet_id
    except Exception as e:
        logger.error(f"Ошибка при создании файла клиента {file_title}: {e}")
        send_notification(f"Ошибка при создании файла клиента {client_code}: {e}")
        raise

def add_message_to_client_file(client_code, message, is_assistant=False):
    """
    Добавляет новое сообщение в Google Sheets файл клиента Client_{client_code}.xlsx.
    Если файл существует, новые строки добавляются в конец.
    Если возникает ошибка записи, создается временный файл Temp_Client_{client_code} и отправляется уведомление.
    """
    try:
        sheets_service = get_sheets_service()
        spreadsheet_id = find_client_file_id(client_code)
        if not spreadsheet_id:
            # Если файл не найден, создаем его
            from clientdata import verify_client_code
            client_data = verify_client_code(client_code)
            if not client_data:
                raise Exception(f"Данные клиента {client_code} не найдены.")
            spreadsheet_id = create_client_file(client_code, client_data)
        current_time = datetime.now().strftime("%d.%m.%y %H:%M")
        if is_assistant:
            new_row = ["", f"{current_time} - {message}", "", "", "", "", ""]
        else:
            new_row = [f"{current_time} - {message}", "", "", "", "", "", ""]
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
            # Создаем временный файл для клиента
            temp_identifier = f"Temp_Client_{client_code}"
            temp_spreadsheet_id = create_client_file(temp_identifier, {"Client Code": client_code, "Name": "Temp", "Phone": "", "Email": "", "Created Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
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

def handle_client(client_code):
    try:
        logger.info(f"Обработка клиента с кодом: {client_code}")
        from clientdata import load_client_data as load_cd
        df = load_cd()
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
        from clientdata import load_client_data as load_cd
        df = load_cd()
        for _, row in df.iterrows():
            client_code = row["Client Code"]
            handle_client(client_code)
        logger.info("Все клиенты обработаны.")
    except Exception as e:
        logger.error(f"Ошибка при обработке всех клиентов: {e}")
        send_notification(f"Ошибка при обработке всех клиентов: {e}")

if __name__ == "__main__":
    handle_all_clients()
