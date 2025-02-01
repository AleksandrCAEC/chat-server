import os
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment
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

# Загрузка файла на Google Drive
def upload_to_google_drive(file_stream, file_name):
    try:
        drive_service = get_drive_service()
        if not drive_service:
            raise Exception("Google Drive API не инициализирован.")

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

        # Создаем файл в памяти
        output = BytesIO()
        wb = Workbook()
        ws = wb.active

        # Записываем заголовки
        ws.append(["Assistant", "Client", "Client Code", "Name", "Phone", "Email", "Created Date"])

        # Записываем данные клиента в первую строку
        ws.append([
            "",  # Assistant (пока пусто)
            "",  # Client (пока пусто)
            client_data["Client Code"],
            client_data["Name"],
            client_data["Phone"],
            client_data["Email"],
            client_data["Created Date"]
        ])

        # Настраиваем выравнивание и автоподбор ширины столбцов
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter  # Получаем букву столбца
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2) * 1.2  # Подбираем ширину столбца
            ws.column_dimensions[column].width = adjusted_width

        # Сохраняем файл в памяти
        wb.save(output)
        output.seek(0)

        # Загружаем файл на Google Drive
        upload_to_google_drive(output, file_name)

        logger.info(f"Файл {file_name} успешно создан и загружен на Google Drive.")
        return file_name
    except Exception as e:
        logger.error(f"Ошибка при создании файла клиента: {e}")
        return None

# Функция для добавления сообщения в файл клиента
def add_message_to_client_file(client_code, message, is_assistant=False):
    try:
        # Получаем данные клиента
        df = load_client_data()
        client_data = df[df["Client Code"] == client_code]

        if not client_data.empty:
            client_data = client_data.iloc[0].to_dict()

            # Создаем файл в памяти
            output = BytesIO()
            wb = Workbook()
            ws = wb.active

            # Записываем заголовки
            ws.append(["Assistant", "Client", "Client Code", "Name", "Phone", "Email", "Created Date"])

            # Записываем данные клиента в первую строку
            ws.append([
                "",  # Assistant (пока пусто)
                "",  # Client (пока пусто)
                client_data["Client Code"],
                client_data["Name"],
                client_data["Phone"],
                client_data["Email"],
                client_data["Created Date"]
            ])

            # Добавляем новое сообщение
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if is_assistant:
                ws.append([f"{current_time} - {message}", "", "", "", "", "", ""])
            else:
                ws.append(["", f"{current_time} - {message}", "", "", "", "", ""])

            # Настраиваем выравнивание и автоподбор ширины столбцов
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter  # Получаем букву столбца
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2) * 1.2  # Подбираем ширину столбца
                ws.column_dimensions[column].width = adjusted_width

            # Сохраняем файл в памяти
            wb.save(output)
            output.seek(0)

            # Загружаем файл на Google Drive
            upload_to_google_drive(output, f"Client_{client_code}.xlsx")

            logger.info(f"Сообщение добавлено в файл клиента {client_code}.")
        else:
            logger.warning(f"Клиент с кодом {client_code} не найден в ClientData.xlsx.")
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
