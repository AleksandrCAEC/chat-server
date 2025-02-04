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

        # Создаем файл в памяти
        output = BytesIO()
        wb = Workbook()
        ws = wb.active

        # Записываем заголовки
        ws.append(["Client", "Assistant", "Client Code", "Name", "Phone", "Email", "Created Date"])

        # Записываем данные клиента в первую строку
        ws.append([
            "",  # Client (пока пусто)
            "",  # Assistant (пока пусто)
            client_data["Client Code"],
            client_data["Name"],
            client_data["Phone"],
            client_data["Email"],
            client_data["Created Date"]
        ])

        # Устанавливаем формат ячеек как текст
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.number_format = numbers.FORMAT_TEXT

        # Настраиваем ширину столбцов A и B на 650 единиц
        ws.column_dimensions['A'].width = 65  # Ширина столбца A (Client)
        ws.column_dimensions['B'].width = 65  # Ширина столбца B (Assistant)

        # Включаем перенос текста для столбцов A и B
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True)

        # Сохраняем файл в памяти
        wb.save(output)
        output.seek(0)

        # Загружаем или обновляем файл на Google Drive
        upload_or_update_file(file_name, output)

        logger.info(f"Файл {file_name} успешно создан и загружен на Google Drive.")
        return file_name
    except Exception as e:
        logger.error(f"Ошибка при создании файла клиента: {e}")
        return None

# Функция для добавления сообщения в файл клиента
def add_message_to_client_file(client_code, message, is_assistant=False):
    try:
        file_name = f"Client_{client_code}.xlsx"

        # Открываем существующий файл или создаем новый, если он не существует
        if os.path.exists(file_name):
            wb = load_workbook(file_name)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            # Записываем заголовки, если файл новый
            ws.append(["Client", "Assistant", "Client Code", "Name", "Phone", "Email", "Created Date"])

            # Загружаем данные клиента
            df = load_client_data()
            client_data = df[df["Client Code"] == client_code].iloc[0].to_dict()

            # Записываем данные клиента в первую строку
            ws.append([
                "",  # Client (пока пусто)
                "",  # Assistant (пока пусто)
                client_data["Client Code"],
                client_data["Name"],
                client_data["Phone"],
                client_data["Email"],
                client_data["Created Date"]
            ])

        # Форматируем время
        current_time = datetime.now().strftime("%d.%m.%y %H:%M")

        # Ищем последнюю строку с сообщением клиента
        last_row = ws.max_row
        if is_assistant:
            # Если это ответ ассистента, добавляем его в ту же строку, что и последнее сообщение клиента
            ws.cell(row=last_row, column=2, value=f"{current_time} - {message}")
        else:
            # Если это новое сообщение клиента, добавляем его в новую строку
            ws.append([
                f"{current_time} - {message}",  # Client
                "",  # Assistant (пока пусто)
                "",  # Client Code (пусто)
                "",  # Name (пусто)
                "",  # Phone (пусто)
                "",  # Email (пусто)
                ""   # Created Date (пусто)
            ])

        # Включаем перенос текста для столбцов A и B
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True)

        # Сохраняем файл
        wb.save(file_name)

        # Загружаем или обновляем файл на Google Drive
        with open(file_name, "rb") as file_stream:
            upload_or_update_file(file_name, file_stream)

        logger.info(f"Сообщение добавлено в файл клиента {client_code}.")
    except Exception as e:
        logger.error(f"Ошибка при добавлении сообщения в файл клиента: {e}")

# Функция для поиска клиента по коду и создания/обновления его файла
def handle_client(client_code):
    try:
        logger.info(f"Обработка клиента с кодом: {client_code}")
        df = load_client_data()

        # Ищем клиента по коду
        client_data = df[df["Client Code"] == client_code]

        if not client_data.empty:
            client_data = client_data.iloc[0].to_dict()

            # Создаем файл клиента, если он не существует
            file_name = f"Client_{client_code}.xlsx"
            if not os.path.exists(file_name):
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
