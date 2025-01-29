import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime

# Путь к подпапке BIG_DATA внутри проекта
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

# Создание индивидуального файла клиента
def create_client_file(client_code, client_data):
    client_file_path = os.path.join(BIG_DATA_PATH, f"{client_code}.xlsx")

    if not os.path.exists(client_file_path):
        columns = ["Date", "Message", "Interests", "Requests", "Registration Date", "Last Visit"]
        df = pd.DataFrame(columns=columns)

        # Добавляем первую строку с информацией о клиенте
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
    else:
        # Обновляем дату последнего визита
        df = pd.read_excel(client_file_path)
        df.loc[df.index[-1], "Last Visit"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.to_excel(client_file_path, index=False)
        print(f"✅ Файл клиента обновлён: {client_file_path}")

# Сохранение изменений в ClientData.xlsx и Google Sheets
def save_client_data(client_code, name, phone, email):
    try:
        print("✅ Подключение к Google Sheets...")
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        sheets_service = build('sheets', 'v4', credentials=credentials)

        spreadsheet_id = "1M-mRD32sQtkvTRcik7jq1n8ZshXhEearsaIBcFlheZk"
        range_name = "Sheet1!A2:G1000"

        current_date = datetime.now().strftime("%Y-%m-%d")
        values = [[client_code, name, phone, email, current_date, current_date, "Active"]]
        body = {'values': values}

        print(f"📤 Отправка данных в Google Sheets: {values}")

        response = sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body=body
        ).execute()

        print(f"✅ Ответ от Google API: {response}")

    except Exception as e:
        print(f"❌ Ошибка записи в Google Sheets: {e}")

    print(f"📝 Локальное сохранение данных: {client_code}, {name}, {phone}, {email}")

    df = load_client_data()
    existing_client = df[df["Client Code"] == client_code]

    if existing_client.empty:
        new_data = pd.DataFrame([{
            "Client Code": client_code,
            "Name": name,
            "Phone": phone,
            "Email": email,
            "Created Date": current_date,
            "Last Visit": current_date,
            "Activity Status": "Active"
        }])
        df = pd.concat([df, new_data], ignore_index=True)
    else:
        df.loc[df["Client Code"] == client_code, "Last Visit"] = current_date

    df.to_excel(CLIENT_DATA_FILE, index=False)

    # Создаём или обновляем файл клиента
    create_client_file(client_code, {
        "Created Date": current_date,
        "Last Visit": current_date
    })

# Генерация уникального кода клиента
def generate_unique_code():
    existing_codes = set(load_client_data()["Client Code"])
    while True:
        code = f"CAEC{str(datetime.now().timestamp()).replace('.', '')[-7:]}"
        if code not in existing_codes:
            return code

# Регистрация или обновление клиента
def register_or_update_client(data):
    initialize_client_data()
    df = load_client_data()

    email = data.get("email")
    phone = data.get("phone")
    name = data.get("name", "Unknown")

    # Проверка на существующего клиента
    existing_client = df[(df["Email"] == email) | (df["Phone"] == phone)]

    if not existing_client.empty:
        client_code = existing_client.iloc[0]["Client Code"]
        df.loc[df["Client Code"] == client_code, "Last Visit"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_client_data(client_code, name, phone, email)
        return {
            "uniqueCode": client_code,
            "message": f"Добро пожаловать обратно, {name}! Ваш код: {client_code}.",
        }

    # Регистрация нового клиента
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

    return {
        "uniqueCode": client_code,
        "message": f"Добро пожаловать, {name}! Ваш код: {client_code}.",
    }

# Инициализация системы при первом запуске
initialize_client_data()
