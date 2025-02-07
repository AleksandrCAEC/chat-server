# client_caec.py
import os
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, numbers
import logging
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from io import BytesIO
from config import CLIENT_DATA_PATH  # Импортируем путь к ClientData.xlsx

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
        file_path = os.path.join(CLIENT_FILES_DIR, file_name)
        output = BytesIO()
        wb = Workbook()
        ws = wb.active
        # Записываем заголовки
        ws.append(["Client", "Assistant", "Client Code", "Name", "Phone", "Email", "Created Date"])
        # Записываем начальные данные клиента
        ws.append([
            "",  
            "",  
            client_data["Client Code"],
            client_data["Name"],
            client_data["Phone"],
            client_data["Email"],
            client_data["Created Date"]
        ])
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
        send_notification(f"Ошибка при создании файла клиента {client_code}: {e}")
        return None

def add_message_to_client_file(client_code, message, is_assistant=False):
    """
    Добавляет новое сообщение в файл клиента Client_CAECxxxxxxx.xlsx.
    Если файл существует, данные дописываются в конец.
    При ошибке записи создается временный файл Temp_Client_CAECxxxxxxx.xlsx и отправляется уведомление.
    """
    try:
        file_name = f"Client_{client_code}.xlsx"
        file_path = os.path.join(CLIENT_FILES_DIR, file_name)
        # Если файл не существует локально, пытаемся скачать его с Google Drive
        if not os.path.exists(file_path):
            if not download_client_file(file_name, file_path):
                # Если скачать не удалось, создаем новый файл с заголовками и начальными данными
                from clientdata import verify_client_code
                client_data = verify_client_code(client_code)
                if not client_data:
                    raise Exception(f"Данные клиента {client_code} не найдены.")
                create_client_file(client_code, client_data)
        wb = load_workbook(file_path)
        ws = wb.active
        current_time = datetime.now().strftime("%d.%m.%y %H:%M")
        if is_assistant:
            new_row = ["", f"{current_time} - {message}", "", "", "", "", ""]
        else:
            new_row = [f"{current_time} - {message}", "", "", "", "", "", ""]
        ws.append(new_row)
        for row in ws.iter_rows(min_row=ws.max_row, max_row=ws.max_row):
            for cell in row:
                cell.number_format = numbers.FORMAT_TEXT
                cell.alignment = Alignment(wrap_text=True)
        wb.save(file_path)
        with open(file_path, "rb") as file_stream:
            upload_or_update_file(file_name, file_stream)
        logger.info(f"Сообщение добавлено в файл клиента {client_code}.")
    except Exception as e:
        logger.error(f"Ошибка при добавлении сообщения в файл клиента {client_code}: {e}")
        send_notification(f"Ошибка при добавлении сообщения в файл клиента {client_code}: {e}")
        try:
            temp_file_name = f"Temp_Client_{client_code}.xlsx"
            temp_file_path = os.path.join(CLIENT_FILES_DIR, temp_file_name)
            if os.path.exists(file_path):
                wb_temp = load_workbook(file_path)
            else:
                wb_temp = Workbook()
                ws_temp = wb_temp.active
                ws_temp.append(["Client", "Assistant", "Client Code", "Name", "Phone", "Email", "Created Date"])
                from clientdata import verify_client_code
                client_data = verify_client_code(client_code)
                if not client_data:
                    raise Exception(f"Данные клиента {client_code} не найдены.")
                ws_temp.append(["", "", client_data["Client Code"], client_data["Name"], client_data["Phone"], client_data["Email"], client_data["Created Date"]])
            ws_temp = wb_temp.active
            ws_temp.append(new_row)
            wb_temp.save(temp_file_path)
            logger.error(f"Создан временный файл {temp_file_name} для клиента {client_code} из-за ошибки записи.")
            send_notification(f"Временный файл {temp_file_name} создан для клиента {client_code} из-за ошибки записи.")
        except Exception as e2:
            logger.error(f"Ошибка при создании временного файла для клиента {client_code}: {e2}")
            send_notification(f"Ошибка при создании временного файла для клиента {client_code}: {e2}")

def handle_client(client_code):
    try:
        logger.info(f"Обработка клиента с кодом: {client_code}")
        df = load_client_data()
        client_data = df[df["Client Code"] == client_code]
        file_name = f"Client_{client_code}.xlsx"
        file_path = os.path.join(CLIENT_FILES_DIR, file_name)
        if not os.path.exists(file_path):
            if not download_client_file(file_name, file_path):
                logger.info(f"Файл клиента {file_name} не найден локально и не удалось скачать с Google Drive. Создаем новый файл.")
                if not client_data.empty:
                    create_client_file(client_code, client_data.iloc[0].to_dict())
                else:
                    logger.warning(f"Клиент с кодом {client_code} не найден в ClientData.xlsx.")
        else:
            logger.info(f"Файл клиента {file_name} уже существует локально.")
    except Exception as e:
        logger.error(f"Ошибка при обработке клиента: {e}")
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
