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

def get_first_sheet_id(spreadsheet_id):
    """Получает sheetId первого листа в таблице."""
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
        return 0  # возвращаем 0 по умолчанию

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
        # Убираем установку ширины столбцов и настройки переноса текста
        # set_column_width(spreadsheet_id, 0, 650)
        # set_column_width(spreadsheet_id, 1, 650)
        # set_text_wrap(spreadsheet_id, 0, 2)
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
    """
    Устанавливает перенос текста (wrap text) для столбцов от start_column_index до end_column_index (не включая end_column_index).
    """
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
    """
    Добавляет новое сообщение в Google Sheets файл клиента Client_{client_code}.xlsx.
    
    Если сообщение от клиента, создаётся новая строка с текстом в столбце A (вопрос),
    а столбец B оставляется пустым.
    
    Если сообщение от ассистента, производится анализ всех строк (начиная с 3-й),
    чтобы найти последнюю строку, в которой записан вопрос без ответа, и затем
    обновляется ячейка столбца B именно в этой строке.
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
        
        # Убираем установку ширины столбцов и настройки переноса текста
        # set_column_width(spreadsheet_id, 0, 650)
        # set_column_width(spreadsheet_id, 1, 650)
        # set_text_wrap(spreadsheet_id, 0, 2)
        
        current_time = datetime.now().strftime("%d.%m.%y %H:%M")
        
        if not is_assistant:
            # Добавляем новую строку: в столбце A записываем вопрос, в столбце B оставляем пустым.
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
            # Считываем все значения из диапазона A:B
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range="Sheet1!A:B"
            ).execute()
            values = result.get("values", [])
            if len(values) < 3:
                logger.error("Нет записей переписки для обновления ответа ассистента.")
                return
            # Проходим по строкам, начиная с 3-й, чтобы найти последнюю строку, где в столбце A есть текст (вопрос) и столбец B пуст
            target_row = None
            conversation_rows = values[2:]  # начиная с 3-й строки
            for idx, row in enumerate(conversation_rows):
                if row and row[0].strip() and (len(row) < 2 or not row[1].strip()):
                    target_row = idx + 3  # нумерация строк: первые две строки заняты
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

# Запуск обработки всех клиентов отключён, чтобы обрабатывать только файлы, связанные с текущим посещением чата.
if __name__ == "__main__":
    # handle_all_clients()  # Отключено для повышения производительности при большом количестве клиентов.
    pass
