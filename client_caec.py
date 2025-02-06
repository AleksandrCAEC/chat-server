# client_caec.py
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("client_caec.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Константа для директории файлов клиента
CLIENT_FILES_DIR = "./CAEC_API_Data/BIG_DATA/Data_CAEC_client/"

# ID папки на Google Drive
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
        logger.error(f"Ошибка при загрузке/обновлении файла на Google Drive: {e}")

def load_client_data():
    try:
        logger.info("Загрузка данных из ClientData.xlsx...")
        df = pd.read_excel("ClientData.xlsx")
        logger.info(f"Данные загружены: {df}")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из ClientData.xlsx: {e}")
        return pd.DataFrame()

def create_client_file(client_code, client_data):
    try:
        file_name = f"Client_{client_code}.xlsx"
        file_path = os.path.join(CLIENT_FILES_DIR, file_name)
        output = BytesIO()
        wb = Workbook()
        ws = wb.active
        ws.append(["Client", "Assistant", "Client Code", "Name", "Phone", "Email", "Created Date"])
        ws.append([
            "",  
            "",  
            client_data["Client Code"],
            client_data["Name"],
            client_data["Phone"],
            client_data["Email"],
            client_data["Created Date"]
        ])
        # Принудительно устанавливаем формат всех ячеек как текст
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
            for cell in row:
                cell.number_format = numbers.FORMAT_TEXT
        ws.column_dimensions['A'].width = 65
        ws.column_dimensions['B'].width = 65
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True)
        wb.save(output)
        output.seek(0)
        upload_or_update_file(file_name, output)
        with open(file_path, "wb") as f:
            f.write(output.getbuffer())
        logger.info(f"Файл {file_name} успешно создан и загружен на Google Drive.")
        return file_name
    except Exception as e:
        logger.error(f"Ошибка при создании файла клиента: {e}")
        return None

def add_message_to_client_file(client_code, message, is_assistant=False):
    try:
        file_name = f"Client_{client_code}.xlsx"
        file_path = os.path.join(CLIENT_FILES_DIR, file_name)
        if os.path.exists(file_path):
            wb = load_workbook(file_path)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            ws.append(["Client", "Assistant", "Client Code", "Name", "Phone", "Email", "Created Date"])
            df = load_client_data()
            client_data = df[df["Client Code"] == client_code].iloc[0].to_dict()
            ws.append([
                "",  
                "",  
                client_data["Client Code"],
                client_data["Name"],
                client_data["Phone"],
                client_data["Email"],
                client_data["Created Date"]
            ])
        current_time = datetime.now().strftime("%d.%m.%y %H:%M")
        # Всегда добавляем новую строку для нового сообщения
        if is_assistant:
            ws.append(["", f"{current_time} - {message}", "", "", "", "", ""])
        else:
            ws.append([f"{current_time} - {message}", "", "", "", "", "", ""])
        # Обходим все ячейки и принудительно устанавливаем формат как текст
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
            for cell in row:
                cell.number_format = numbers.FORMAT_TEXT
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True)
        wb.save(file_path)
        with open(file_path, "rb") as file_stream:
            upload_or_update_file(file_name, file_stream)
        logger.info(f"Сообщение добавлено в файл клиента {client_code}.")
    except Exception as e:
        logger.error(f"Ошибка при добавлении сообщения в файл клиента: {e}")

def handle_client(client_code):
    try:
        logger.info(f"Обработка клиента с кодом: {client_code}")
        df = load_client_data()
        client_data = df[df["Client Code"] == client_code]
        if not client_data.empty:
            client_data = client_data.iloc[0].to_dict()
            file_name = f"Client_{client_code}.xlsx"
            file_path = os.path.join(CLIENT_FILES_DIR, file_name)
            if not os.path.exists(file_path):
                logger.info(f"Создание файла клиента: {file_name}")
                create_client_file(client_code, client_data)
        else:
            logger.warning(f"Клиент с кодом {client_code} не найден в ClientData.xlsx.")
    except Exception as e:
        logger.error(f"Ошибка при обработке клиента: {e}")

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

if __name__ == "__main__":
    handle_all_clients()
