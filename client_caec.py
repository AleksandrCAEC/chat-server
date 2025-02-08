# client_caec.py
import os
import pandas as pd
from datetime import datetime
import logging
from io import BytesIO
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, numbers
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from config import CLIENT_DATA_PATH, CLIENT_FILES_DIR  # Импортируем константы из config

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

# Если директория для файлов клиента не существует, создаём её
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
        raise

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        send_notification(f"Ошибка инициализации Google Sheets API: {e}")
        raise

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
        raise

def find_client_file_id(client_code):
    """
    Ищет Google Sheets файл для клиента по имени, содержащий "Client_{client_code}".
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
    Возвращает spreadsheetId нового файла.
    """
    sheets_service = get_sheets_service()
    file_title = f"Client_{client_code}.xlsx"
    values = [
        ["Client", "Assistant", "Client Code", "Name", "Phone", "Email", "Created Date"],
        ["", "", client_data["Client Code"], client_data["Name"], client_data["Phone"], client_data["Email"], client_data["Created Date"]]
    ]
    body = {
        "properties": {"title": file_title},
        "sheets": [
            {
                "data": [
                    {
                        "startRow": 0,
                        "startColumn": 0,
                        "rowData": [
                            {"values": [{"userEnteredValue": {"stringValue": cell}} for cell in row]} for row in values
                        ]
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
        # Устанавливаем ширину столбцов A и B равной 450 пикселей
        set_column_width(spreadsheet_id, 0, 450)
        set_column_width(spreadsheet_id, 1, 450)
        return spreadsheet_id
    except Exception as e:
        logger.error(f"Ошибка при создании файла клиента {file_title}: {e}")
        send_notification(f"Ошибка при создании файла клиента {client_code}: {e}")
        raise

def set_column_width(spreadsheet_id, column_index, width):
    try:
        sheets_service = get_sheets_service()
        requests_body = {
            "requests": [
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": 0,
                            "dimension": "COLUMNS",
                            "startIndex": column_index,
                            "endIndex": column_index + 1
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize"
                    }
                }
            ]
        }
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=requests_body
        ).execute()
        logger.info(f"Ширина столбца {column_index} установлена в {width} пикселей для файла {spreadsheet_id}.")
    except Exception as e:
        logger.error(f"Ошибка при установке ширины столбца: {e}")
        send_notification(f"Ошибка при установке ширины столбца в файле {spreadsheet_id}: {e}")

def add_message_to_client_file(client_code, message, is_assistant=False):
    """
    Добавляет новое сообщение в Google Sheets файл клиента Client_{client_code}.xlsx.
    Если сообщение от клиента, создаётся новая строка с текстом в столбце A.
    Если сообщение от ассистента, обновляется ячейка в столбце B той же строки, где указан вопрос без ответа.
    """
    try:
        sheets_service = get_sheets_service()
        spreadsheet_id = find_client_file_id(client_code)
        if not spreadsheet_id:
            from clientdata import verify_client_code
            client_data = verify_client_code(client_code)
            if not client_data:
                raise Exception(f"Данные клиента {client_code} не найдены.")
            spreadsheet_id = create_client_file(client_code, client_data)
        # Обновляем ширину столбцов A и B до 450 пикселей (на случай, если файл уже существует)
        set_column_width(spreadsheet_id, 0, 450)
        set_column_width(spreadsheet_id, 1, 450)
        current_time = datetime.now().strftime("%d.%m.%y %H:%M")
        if not is_assistant:
            # Сообщение от клиента – создаём новую строку с текстом в столбце A
            new_row = [f"{current_time} - {message}", "", "", "", "", "", ""]
            body = {"values": [new_row]}
            sheets_service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range="Sheet1!A:G",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body
            ).execute()
            logger.info(f"Запрос клиента добавлен в файл клиента {client_code}.")
        else:
            # Сообщение от ассистента – пытаемся дописать ответ в ту же строку, где есть вопрос без ответа.
            # Используем диапазон, начиная с 3-й строки, чтобы пропустить заголовок и строку с данными клиента.
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range="Sheet1!A3:B"
            ).execute()
            values = result.get("values", [])
            # По умолчанию готовим новую строку с ответом в столбце B
            new_row = ["", f"{current_time} - {message}", "", "", "", "", ""]
            if values and len(values) > 0:
                last_row = values[-1]
                # Если в последней строке в столбце A есть текст, а столбец B отсутствует или пуст, обновляем ячейку B.
                if len(last_row) >= 1 and last_row[0] and (len(last_row) < 2 or not last_row[1].strip()):
                    row_number = len(values) + 2  # учитываем первые две строки (заголовок и данные клиента)
                    range_update = f"Sheet1!B{row_number}"
                    body = {"values": [[f"{current_time} - {message}"]]}
                    sheets_service.spreadsheets().values().update(
                        spreadsheetId=spreadsheet_id,
                        range=range_update,
                        valueInputOption="RAW",
                        body=body
                    ).execute()
                    logger.info(f"Ответ ассистента добавлен в строку {row_number} файла клиента {client_code}.")
                else:
                    # Иначе добавляем новую строку с ответом в столбце B
                    body = {"values": [new_row]}
                    sheets_service.spreadsheets().values().append(
                        spreadsheetId=spreadsheet_id,
                        range="Sheet1!A:G",
                        valueInputOption="RAW",
                        insertDataOption="INSERT_ROWS",
                        body=body
                    ).execute()
                    logger.info(f"Ответ ассистента добавлен в новую строку файла клиента {client_code}.")
            else:
                # Если лист пуст, добавляем новую строку
                body = {"values": [new_row]}
                sheets_service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range="Sheet1!A:G",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body=body
                ).execute()
                logger.info(f"Ответ ассистента добавлен в файл клиента {client_code}.")
    except Exception as e:
        logger.error(f"Ошибка при добавлении сообщения в файл клиента {client_code}: {e}")
        send_notification(f"Ошибка при добавлении сообщения в файл клиента {client_code}: {e}")
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
