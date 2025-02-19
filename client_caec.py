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
from config import CLIENT_DATA_PATH, CLIENT_FILES_DIR
import tempfile

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

if not os.path.exists(CLIENT_FILES_DIR):
    try:
        os.makedirs(CLIENT_FILES_DIR, exist_ok=True)
        logger.info(f"Директория {CLIENT_FILES_DIR} создана.")
    except Exception as e:
        logger.error(f"Ошибка при создании директории {CLIENT_FILES_DIR}: {e}")
        send_notification(f"Ошибка при создании директории {CLIENT_FILES_DIR}: {e}")

GOOGLE_DRIVE_FOLDER_ID = "11cQYLDGKlu2Rn_9g8R_4xNA59ikhvJpS"

def get_drive_service():
    try:
        credentials = Credentials.from_service_account_file(get_credentials_file())
        return build("drive", "v3", credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Drive API: {e}")
        send_notification(f"Ошибка инициализации Google Drive API: {e}")
        raise

def get_credentials_file():
    env_val = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_val is None:
        raise Exception("Переменная окружения GOOGLE_APPLICATION_CREDENTIALS не установлена.")
    env_val = env_val.strip()
    if env_val.startswith("{"):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
        tmp.write(env_val)
        tmp.close()
        logger.info(f"Credentials written to temporary file: {tmp.name}")
        return tmp.name
    return os.path.abspath(env_val)

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(get_credentials_file())
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        send_notification(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def get_first_sheet_id(spreadsheet_id):
    try:
        sheets_service = get_sheets_service()
        spreadsheet = sheets_service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId))"
        ).execute()
        sheet_id = spreadsheet["sheets"][0]["properties"]["sheetId"]
        return sheet_id
    except Exception as e:
        logger.error(f"Ошибка получения sheetId для файла {spreadsheet_id}: {e}")
        return 0

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

def set_column_width(spreadsheet_id, column_index, width):
    try:
        sheets_service = get_sheets_service()
        sheet_id = get_first_sheet_id(spreadsheet_id)
        requests_body = {
            "requests": [
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
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

def set_text_wrap(spreadsheet_id, start_column_index, end_column_index):
    try:
        sheets_service = get_sheets_service()
        sheet_id = get_first_sheet_id(spreadsheet_id)
        requests_body = {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startColumnIndex": start_column_index,
                            "endColumnIndex": end_column_index
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "wrapStrategy": "WRAP"
                            }
                        },
                        "fields": "userEnteredFormat.wrapStrategy"
                    }
                }
            ]
        }
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=requests_body
        ).execute()
        logger.info(f"Текст в столбцах с {start_column_index} по {end_column_index - 1} настроен на перенос по словам.")
    except Exception as e:
        logger.error(f"Ошибка при установке переноса текста в столбцах {start_column_index} - {end_column_index - 1}: {e}")
        send_notification(f"Ошибка при установке переноса текста в столбцах {start_column_index} - {end_column_index - 1}: {e}")

def add_message_to_client_file(client_code, message, is_assistant=False):
    try:
        sheets_service = get_sheets_service()
        spreadsheet_id = find_client_file_id(client_code)
        if not spreadsheet_id:
            from clientdata import verify_client_code
            client_data = verify_client_code(client_code)
            if not client_data:
                raise Exception(f"Данные клиента {client_code} не найдены.")
            spreadsheet_id = create_client_file(client_code, client_data)
        
        current_time = datetime.now().strftime("%d.%m.%y %H:%M")
        
        if not is_assistant:
            new_row = [f"{current_time} - {message}", ""]
            while len(new_row) < 7:
                new_row.append("")
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
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range="Sheet1!A:B"
            ).execute()
            values = result.get("values", [])
            if len(values) < 3:
                logger.error("Нет записей переписки для обновления ответа ассистента.")
                return
            target_row = None
            conversation_rows = values[2:]
            for idx, row in enumerate(conversation_rows):
                if row and row[0].strip() and (len(row) < 2 or not row[1].strip()):
                    target_row = idx + 3
            if target_row is not None:
                range_update = f"Sheet1!B{target_row}"
                body = {"values": [[f"{current_time} - {message}"]]}
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=range_update,
                    valueInputOption="RAW",
                    body=body
                ).execute()
                logger.info(f"Ответ ассистента обновлен в строке {target_row} файла клиента {client_code}.")
            else:
                logger.error("Не найдена строка с вопросом без ответа для обновления.")
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
    pass
