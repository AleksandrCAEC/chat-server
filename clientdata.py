# clientdata.py
import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta
import logging
from client_caec import handle_client  # Функция для обработки файла клиента

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

# Константа для локального файла ClientData.xlsx
CLIENT_DATA_PATH = "./CAEC_API_Data/BIG_DATA/ClientData.xlsx"

# Идентификатор Google Sheets таблицы
SPREADSHEET_ID = "1eGpB0hiRxXPpYN75-UKyXoar7yh-zne8r8ox-hXrS1I"

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        return None

def load_client_data():
    try:
        logger.info("Загрузка данных из Google Sheets...")
        sheets_service = get_sheets_service()
        if not sheets_service:
            raise Exception("Google Sheets API не инициализирован.")
        range_name = "Sheet1!A2:G1000"
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
        values = result.get('values', [])
        if not values:
            logger.info("Данные не найдены.")
            return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])
        df = pd.DataFrame(values, columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])
        df["Client Code"] = df["Client Code"].astype(str)
        logger.info(f"Загружены данные: {df}")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

def generate_unique_code():
    try:
        existing_codes = set(load_client_data()["Client Code"])
        while True:
            code = f"CAEC{str(datetime.now().timestamp()).replace('.', '')[-7:]}"
            if code not in existing_codes:
                return code
    except Exception as e:
        logger.error(f"Ошибка генерации уникального кода: {e}")
        raise

def save_client_data(client_code, name, phone, email, created_date, last_visit, activity_status):
    try:
        logger.info("Подключение к Google Sheets...")
        sheets_service = get_sheets_service()
        if not sheets_service:
            raise Exception("Google Sheets API не инициализирован.")
        values = [[str(client_code), name, phone, email, created_date, last_visit, activity_status]]
        body = {'values': values}
        logger.info(f"Отправка данных в Google Sheets: {values}")
        response = sheets_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="Sheet1!A2:G2",
            valueInputOption="RAW",
            body=body
        ).execute()
        logger.info(f"Ответ от Google API: {response}")
    except Exception as e:
        logger.error(f"Ошибка записи в Google Sheets: {e}")
        raise

    try:
        df = load_client_data()
        new_data = pd.DataFrame([{
            "Client Code": str(client_code),
            "Name": name,
            "Phone": phone,
            "Email": email,
            "Created Date": created_date,
            "Last Visit": last_visit,
            "Activity Status": activity_status
        }])
        df = pd.concat([df, new_data], ignore_index=True)
        df.to_excel(CLIENT_DATA_PATH, index=False)
        logger.info(f"Данные сохранены в ClientData.xlsx: {client_code}, {name}, {phone}, {email}")
    except Exception as e:
        logger.error(f"Ошибка сохранения в локальный файл: {e}")

def update_activity_status():
    try:
        df = load_client_data()
        current_date = datetime.now()
        one_year_ago = current_date - timedelta(days=365)
        df.loc[(pd.to_datetime(df["Last Visit"]) < one_year_ago), "Activity Status"] = "Not Active"
        df = df.sort_values(by=["Activity Status"], ascending=True)
        df.to_excel(CLIENT_DATA_PATH, index=False)
        logger.info("Статус активности клиентов обновлен.")
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса активности: {e}")

def register_or_update_client(data):
    try:
        df = load_client_data()
        email = data.get("email")
        phone = data.get("phone")
        name = data.get("name", "Unknown")
        existing_client = df[(df["Email"] == email) | (df["Phone"] == phone)]
        if not existing_client.empty:
            client_code = existing_client.iloc[0]["Client Code"]
            created_date = existing_client.iloc[0]["Created Date"]
            last_visit = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            activity_status = "Active"
            if email != existing_client.iloc[0]["Email"] or phone != existing_client.iloc[0]["Phone"]:
                save_client_data(
                    client_code=client_code,
                    name=name,
                    phone=phone,
                    email=email,
                    created_date=created_date,
                    last_visit=last_visit,
                    activity_status=activity_status
                )
            else:
                df.loc[df["Client Code"] == client_code, "Last Visit"] = last_visit
                df.to_excel(CLIENT_DATA_PATH, index=False)
            handle_client(client_code)
            return {
                "uniqueCode": client_code,
                "message": f"Добро пожаловать обратно, {name}! Ваш код: {client_code}.",
                "name": name,
                "email": email,
                "phone": phone,
                "isNewClient": False
            }
        client_code = generate_unique_code()
        created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        last_visit = created_date
        activity_status = "Active"
        save_client_data(
            client_code=client_code,
            name=name,
            phone=phone,
            email=email,
            created_date=created_date,
            last_visit=last_visit,
            activity_status=activity_status
        )
        handle_client(client_code)
        update_activity_status()
        return {
            "uniqueCode": client_code,
            "message": f"Добро пожаловать, {name}! Ваш код: {client_code}.",
            "name": name,
            "email": email,
            "phone": phone,
            "isNewClient": True
        }
    except Exception as e:
        logger.error(f"Ошибка при регистрации/обновлении клиента: {e}")
        raise

def verify_client_code(code):
    try:
        df = load_client_data()
        code = str(code)
        client_data = df[df["Client Code"] == code]
        if not client_data.empty:
            return client_data.iloc[0].to_dict()
        return None
    except Exception as e:
        logger.error(f"Ошибка при верификации кода клиента: {e}")
        return None
