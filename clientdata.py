import os
import pandas as pd
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("clientdata.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Путь к файлу ClientData.xlsx
CLIENT_DATA_PATH = "./CAEC_API_Data/BIG_DATA/ClientData.xlsx"

# Генерация уникального кода
def generate_unique_code():
    if not os.path.exists(CLIENT_DATA_PATH):
        return f"CAEC{str(datetime.now().timestamp()).replace('.', '')[-7:]}"

    df = pd.read_excel(CLIENT_DATA_PATH)
    existing_codes = set(df["Client Code"])

    while True:
        code = f"CAEC{str(datetime.now().timestamp()).replace('.', '')[-7:]}"
        if code not in existing_codes:
            return code

# Регистрация или обновление клиента
def register_or_update_client(data):
    try:
        name = data.get("name")
        phone = data.get("phone")
        email = data.get("email")
        code = data.get("code", "")

        # Если код не указан, генерируем новый
        if not code:
            code = generate_unique_code()

        # Загружаем данные клиентов
        if os.path.exists(CLIENT_DATA_PATH):
            df = pd.read_excel(CLIENT_DATA_PATH)
        else:
            df = pd.DataFrame(columns=["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"])

        # Проверяем, существует ли клиент
        client_data = df[df["Client Code"] == code]
        if not client_data.empty:
            # Обновляем данные существующего клиента
            df.loc[df["Client Code"] == code, "Last Visit"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            is_new_client = False
        else:
            # Добавляем нового клиента
            new_data = {
                "Client Code": code,
                "Name": name,
                "Phone": phone,
                "Email": email,
                "Created Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Last Visit": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Activity Status": "Active"
            }
            df = df.append(new_data, ignore_index=True)
            is_new_client = True

        # Сохраняем данные
        df.to_excel(CLIENT_DATA_PATH, index=False)

        return {
            "uniqueCode": code,
            "name": name,
            "email": email,
            "phone": phone,
            "isNewClient": is_new_client
        }
    except Exception as e:
        logger.error(f"Ошибка при регистрации клиента: {e}")
        raise

# Верификация кода клиента
def verify_client_code(code):
    try:
        if not os.path.exists(CLIENT_DATA_PATH):
            return None

        df = pd.read_excel(CLIENT_DATA_PATH)
        client_data = df[df["Client Code"] == code]

        if not client_data.empty:
            return client_data.iloc[0].to_dict()
        return None
    except Exception as e:
        logger.error(f"Ошибка при верификации кода клиента: {e}")
        return None
