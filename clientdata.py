import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime

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

# Загрузка ClientData.xlsx
def load_client_data():
    try:
        return pd.read_excel(CLIENT_DATA_FILE)
    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")
        initialize_client_data()
        return pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

# Сохранение изменений в ClientData.xlsx
def save_client_data(client_code, name, phone, email):
    try:
        print("Подключение к Google Sheets...")
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        sheets_service = build('sheets', 'v4', credentials=credentials)

        spreadsheet_id = "1gfAKsnZ9RaZes9ox8BPdZi9mJq1Fyj1W"
