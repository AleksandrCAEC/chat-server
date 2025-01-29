import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime

# Путь к подпапке BIG_DATA внутри проекта
BIG_DATA_PATH = "./data/BIG_DATA"

# Создаём директорию, если её нет
os.makedirs(BIG_DATA_PATH, exist_ok=True)

# Google Drive Folder ID (ВАЖНО: замените на ID папки CAEC_API_Data)
GOOGLE_DRIVE_FOLDER_ID = "1g1OtN7ID1lM01d0bLswGqLF0m2gQIcqo"

# Путь к файлу ClientData.xlsx
CLIENT_DATA_FILE = os.path.join(BIG_DATA_PATH, "ClientData.xlsx")

# Инициализация ClientData.xlsx
def initialize_client_data():
    if not os.path.exists(CLIENT_DATA_FILE):
        columns = ["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"]
        df = pd.DataFrame(columns=columns)
        df.to_excel(CLIENT_DATA_FILE, index=False)

# Подключение к Google Drive API
def get_drive_service():
    credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    return build('drive', 'v3', credentials=credentials)

# Загрузка ClientData.xlsx
def load_client_data():
    try:
        return pd.read_excel(CLIENT_DATA_FILE)
    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")
        initialize_client_data()
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

# Создание файла клиента и загрузка в Google Drive
def create_client_file(client_code, client_data):
    client_file_path = os.path.join(BIG_DATA_PATH, f"{client_code}.xlsx")

    if not os.path.exists(client_file_path):
        columns = ["Date", "Message", "Interests", "Requests", "Registration Date", "Last Visit"]
        df = pd.DataFrame(columns=columns)

        # Записываем первую строку
        df = df.append({
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Message": "Клиент зарегистрирован",
            "Interests": "",
            "Requests": "",
            "Registration Date": client_data["Created Date"],
            "Last Visit": client_data["Last Visit"]
        }, ignore_index=True)

        df.to_excel(client_file_path, index=False)
        print(f"📁 Файл клиента создан: {client_file_path}")

        # Загружаем файл в Google Drive
        upload_file_to_drive(client_file_path, client_code)

    else:
        # Обновляем дату последнего визита
        df = pd.read_excel(client_file_path)
        df.loc[df.index[-1], "Last Visit"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.to_excel(client_file_path, index=False)
        print(f"✅ Файл клиента обновлён: {client_file_path}")

# Загрузка файла клиента в Google Drive
def upload_file_to_drive(file_path, client_code):
    service = get_drive_service()

    file_metadata = {
        "name": f"{client_code}.xlsx",
        "parents": [GOOGLE_DRIVE_FOLDER_ID],
        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }

    media = {"name": file_path, "mimeType": "application/vnd.ms-excel"}
    
    try:
        uploaded_file = service.files().create(body=file_metadata, media_body=file_path, fields="id").execute()
        print(f"✅ Файл загружен в Google Drive: {uploaded_file.get('id')}")
    except Exception as e:
        print(f"❌ Ошибка загрузки в Google Drive: {e}")

# Генерация уникального кода клиента
def generate_unique_code():
    existing_codes = set(load_client_data()["Client Code"])
    while True:
        code = f"CAEC{str(datetime.now().timestamp()).replace('.', '')[-7:]}"
        if code not in existing_codes:
            return code

# Регистрация клиента
def register_or_update_client(data):
    initialize_client_data()
    df = load_client_data()

    email = data.get("email")
    phone = data.get("phone")
    name = data.get("name", "Unknown")

    existing_client = df[(df["Email"] == email) | (df["Phone"] == phone)]

    if not existing_client.empty:
        client_code = existing_client.iloc[0]["Client Code"]
        df.loc[df["Client Code"] == client_code, "Last Visit"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_client_data(client_code, name, phone, email)
        return {
            "uniqueCode": client_code,
            "message": f"Добро пожаловать обратно, {name}! Ваш код: {client_code}.",
        }

    client_code = generate_unique_code()
    new_client = {
        "Client Code": client_code,
        "Name": name,
        "Phone": phone,
        "Email": email,
        "Created Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Last Visit": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Activity Status": "Active"
    }
    df = pd.concat([df, pd.DataFrame([new_client])], ignore_index=True)
    save_client_data(client_code, name, phone, email)

    # Создаём файл клиента и загружаем в Google Drive
    create_client_file(client_code, new_client)

    return {
        "uniqueCode": client_code,
        "message": f"Добро пожаловать, {name}! Ваш код: {client_code}.",
    }

# Инициализация системы при первом запуске
initialize_client_data()
