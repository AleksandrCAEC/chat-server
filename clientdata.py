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
        logging.FileHandler("app.log"),  # Логи записываются в файл app.log
        logging.StreamHandler()  # Логи выводятся в консоль
    ]
)
logger = logging.getLogger(__name__)

# Путь к папке CAEC_API_Data/BIG_DATA
BIG_DATA_PATH = "./CAEC_API_Data/BIG_DATA"

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
        logger.info(f"Инициализирован новый файл ClientData.xlsx по пути: {CLIENT_DATA_FILE}")

# Загрузка ClientData.xlsx
def load_client_data():
    try:
        logger.info(f"Загрузка данных из файла: {CLIENT_DATA_FILE}")
        df = pd.read_excel(CLIENT_DATA_FILE)
        logger.info(f"Загруженные данные: {df}")
        return df
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        initialize_client_data()
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

# Генерация уникального кода клиента
def generate_unique_code():
    existing_codes = set(load_client_data()["Client Code"].astype(str).str.strip())
    while True:
        code = f"CAEC{str(datetime.now().timestamp()).replace('.', '')[-7:]}"
        if code not in existing_codes:
            return code

# Сохранение данных клиента
def save_client_data(client_code, name, phone, email, created_date, last_visit, activity_status):
    try:
        df = load_client_data()
        existing_client = df[df["Client Code"].astype(str).str.strip() == client_code.strip()]

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
            df.loc[df["Client Code"].astype(str).str.strip() == client_code.strip(), ["Name", "Phone", "Email", "Last Visit", "Activity Status"]] = [name, phone, email, last_visit, activity_status]

        df.to_excel(CLIENT_DATA_FILE, index=False)
        logger.info(f"Данные сохранены в ClientData.xlsx: {client_code}, {name}, {phone}, {email}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")
        raise

# Регистрация или обновление клиента
def register_or_update_client(data):
    try:
        initialize_client_data()
        df = load_client_data()

        email = data.get("email", "").strip()
        phone = data.get("phone", "").strip()
        name = data.get("name", "Unknown").strip()

        # Поиск существующего клиента по email или телефону
        existing_client = df[(df["Email"].astype(str).str.strip() == email) | (df["Phone"].astype(str).str.strip() == phone)]

        if not existing_client.empty:
            # Если клиент уже существует, возвращаем его код
            client_code = existing_client.iloc[0]["Client Code"]
            created_date = existing_client.iloc[0]["Created Date"]
            last_visit = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    except Exception as e:
        logger.error(f"Ошибка при регистрации клиента: {e}")
        raise

# Верификация кода клиента
def verify_client_code(code):
    try:
        logger.info(f"Поиск клиента с кодом: {code}")
        df = load_client_data()

        if "Client Code" not in df.columns:
            logger.error("Столбец 'Client Code' отсутствует в файле ClientData.xlsx")
            return None

        client_data = df[df["Client Code"].astype(str).str.strip() == code.strip()]

        if not client_data.empty:
            logger.info(f"Клиент найден: {client_data.iloc[0].to_dict()}")
            return client_data.iloc[0].to_dict()
        else:
            logger.info(f"Клиент с кодом {code} не найден")
            return None
    except Exception as e:
        logger.error(f"Ошибка при верификации кода: {e}")
        return None

# Инициализация системы при первом запуске
initialize_client_data()
