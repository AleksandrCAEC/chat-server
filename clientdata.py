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

# Идентификатор Google Sheets таблицы
SPREADSHEET_ID = "1eGpB0hiRxXPpYN75-UKyXoar7yh-zne8r8ox-hXrS1I"

# Инициализация Google Sheets API
def get_sheets_service():
    credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    return build('sheets', 'v4', credentials=credentials)

# Загрузка данных из Google Sheets
def load_client_data():
    try:
        logger.info("Загрузка данных из Google Sheets...")
        sheets_service = get_sheets_service()
        range_name = "Sheet1!A2:G1000"  # Диапазон для всех столбцов

        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()

        values = result.get('values', [])
        if not values:
            logger.info("Данные не найдены.")
            return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

        # Преобразуем данные в DataFrame
        df = pd.DataFrame(values, columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])
        
        # Преобразуем столбец "Client Code" в строковый тип
        df["Client Code"] = df["Client Code"].astype(str)
        
        logger.info(f"Загружены данные: {df}")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

# Генерация уникального кода клиента
def generate_unique_code():
    existing_codes = set(load_client_data()["Client Code"])
    while True:
        code = f"CAEC{str(datetime.now().timestamp()).replace('.', '')[-7:]}"
        if code not in existing_codes:
            return code

# Сохранение изменений в Google Sheets
def save_client_data(client_code, name, phone, email, created_date, last_visit, activity_status):
    try:
        logger.info("Подключение к Google Sheets...")
        sheets_service = get_sheets_service()

        # Преобразуем client_code в строковый тип
        values = [[str(client_code), name, phone, email, created_date, last_visit, activity_status]]
        body = {'values': values}

        logger.info(f"Отправка данных в Google Sheets: {values}")

        response = sheets_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="Sheet1!A2:G2",  # Диапазон для добавления новой строки
            valueInputOption="RAW",
            body=body
        ).execute()

        logger.info(f"Ответ от Google API: {response}")
    except Exception as e:
        logger.error(f"Ошибка записи в Google Sheets: {e}")
        raise

# Регистрация или обновление клиента
def register_or_update_client(data):
    df = load_client_data()

    email = data.get("email")
    phone = data.get("phone")
    name = data.get("name", "Unknown")

    # Поиск существующего клиента по email или телефону
    existing_client = df[(df["Email"] == email) | (df["Phone"] == phone)]

    if not existing_client.empty:
        # Если клиент уже существует, обновляем его данные
        client_code = existing_client.iloc[0]["Client Code"]
        created_date = existing_client.iloc[0]["Created Date"]
        last_visit = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        activity_status = "Active"

        # Проверяем, изменились ли email или телефон
        if email != existing_client.iloc[0]["Email"] or phone != existing_client.iloc[0]["Phone"]:
            # Если email или телефон изменились, создаем новую запись с тем же кодом
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
            # Если данные не изменились, просто обновляем последний визит
            df.loc[df["Client Code"] == client_code, "Last Visit"] = last_visit
            df.to_excel("ClientData.xlsx", index=False)

        return {
            "uniqueCode": client_code,
            "message": f"Добро пожаловать обратно, {name}! Ваш код: {client_code}.",
            "name": name,
            "email": email,
            "phone": phone
        }

    # Регистрация нового клиента
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

    return {
        "uniqueCode": client_code,
        "message": f"Добро пожаловать, {name}! Ваш код: {client_code}.",
        "name": name,
        "email": email,
        "phone": phone
    }

# Верификация кода клиента
def verify_client_code(code):
    df = load_client_data()
    code = str(code)  # Преобразуем код к строковому типу
    client_data = df[df["Client Code"] == code]
    if not client_data.empty:
        return client_data.iloc[0].to_dict()
    return None
