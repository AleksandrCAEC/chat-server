import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Путь к подпапке BIG_DATA внутри проекта (изменено для Render)
BIG_DATA_PATH = "./data/BIG_DATA"

# Убедимся, что директория BIG_DATA существует
os.makedirs(BIG_DATA_PATH, exist_ok=True)

# Путь к файлу ClientData.xlsx
CLIENT_DATA_FILE = os.path.join(BIG_DATA_PATH, "ClientData.xlsx")

# Инициализация ClientData.xlsx, если файл не существует
def initialize_client_data():
    if not os.path.exists(CLIENT_DATA_FILE):
        columns = ["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"]
        df = pd.DataFrame(columns=columns)
        df.to_excel(CLIENT_DATA_FILE, index=False)
        logger.info("Инициализирован новый файл ClientData.xlsx")

# Загрузка ClientData.xlsx
def load_client_data():
    try:
        return pd.read_excel(CLIENT_DATA_FILE)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        initialize_client_data()
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

# Генерация уникального кода клиента
def generate_unique_code():
    existing_codes = set(load_client_data()["Client Code"])
    while True:
        code = f"CAEC{str(datetime.now().timestamp()).replace('.', '')[-7:]}"
        if code not in existing_codes:
            return code

# Сохранение изменений в ClientData.xlsx и Google Sheets
def save_client_data(client_code, name, phone, email, created_date, last_visit, activity_status):
    try:
        logger.info("Подключение к Google Sheets...")
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        sheets_service = build('sheets', 'v4', credentials=credentials)

        spreadsheet_id = "1M-mRD32sQtkvTRcik7jq1n8ZshXhEearsaIBcFlheZk"
        range_name = "Sheet1!A2:G1000"

        values = [[client_code, name, phone, email, created_date, last_visit, activity_status]]
        body = {'values': values}

        logger.info(f"Отправка данных в Google Sheets: {values}")

        response = sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body=body
        ).execute()

        logger.info(f"Ответ от Google API: {response}")
    except Exception as e:
        logger.error(f"Ошибка записи в Google Sheets: {e}")

    df = load_client_data()
    existing_client = df[df["Client Code"] == client_code]

    if existing_client.empty:
        new_data = pd.DataFrame([{
            "Client Code": client_code,
            "Name": name,
            "Phone": phone,
            "Email": email,
            "Created Date": created_date,
            "Last Visit": last_visit,
            "Activity Status": activity_status
        }])
        df = pd.concat([df, new_data], ignore_index=True)
    else:
        df.loc[df["Client Code"] == client_code, ["Name", "Phone", "Email", "Last Visit", "Activity Status"]] = [name, phone, email, last_visit, activity_status]

    df.to_excel(CLIENT_DATA_FILE, index=False)
    logger.info(f"Данные сохранены в ClientData.xlsx: {client_code}, {name}, {phone}, {email}")

# Регистрация или обновление клиента
def register_or_update_client(data):
    initialize_client_data()
    df = load_client_data()

    email = data.get("email")
    phone = data.get("phone")
    name = data.get("name", "Unknown")

    existing_client = df[(df["Email"] == email) | (df["Phone"] == phone)]

    if not existing_client.empty:
        client_code = existing_client.iloc[0]["Client Code"]
        created_date = existing_client.iloc[0]["Created Date"]
        last_visit = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.loc[df["Client Code"] == client_code, "Last Visit"] = last_visit
        save_client_data(client_code, name, phone, email, created_date, last_visit, "Active")
        return {
            "uniqueCode": client_code,
            "message": f"Добро пожаловать обратно, {name}! Ваш код: {client_code}.",
        }

    client_code = generate_unique_code()
    created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    last_visit = created_date
    activity_status = "Active"

    new_client = {
        "Client Code": client_code,
        "Name": name,
        "Phone": phone,
        "Email": email,
        "Created Date": created_date,
        "Last Visit": last_visit,
        "Activity Status": activity_status
    }
    df = pd.concat([df, pd.DataFrame([new_client])], ignore_index=True)
    save_client_data(client_code, name, phone, email, created_date, last_visit, activity_status)

    create_client_file(client_code, new_client)

    return {
        "uniqueCode": client_code,
        "message": f"Добро пожаловать, {name}! Ваш код: {client_code}.",
    }

def create_client_file(client_code, client_data):
    client_file_path = os.path.join(BIG_DATA_PATH, f"{client_code}.xlsx")
    columns = ["Date", "Message"]
    initial_data = {
        "Date": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        "Message": ["Файл клиента создан"]
    }
    df = pd.DataFrame(initial_data, columns=columns)
    df.to_excel(client_file_path, index=False)
    logger.info(f"Создан файл клиента: {client_file_path}")

initialize_client_data()
