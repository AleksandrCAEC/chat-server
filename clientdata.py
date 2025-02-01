import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta
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

# Сохранение изменений в Google Sheets и локальном файле
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

    # Сохранение в локальный файл ClientData.xlsx
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
        df.to_excel("ClientData.xlsx", index=False)
        logger.info(f"Данные сохранены в ClientData.xlsx: {client_code}, {name}, {phone}, {email}")
    except Exception as e:
        logger.error(f"Ошибка сохранения в локальный файл: {e}")

# Отправка email клиенту
def send_email(to_email, client_code, name):
    try:
        # Настройки SMTP
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        smtp_username = "office@caec.bz"
        smtp_password = os.getenv("EMAIL_TOKEN")  # Пароль из переменной окружения

        # Создаем сообщение
        subject = "Регистрация в базе данных CAEC GmbH"
        body = f"""
        Уважаемый(ая) {name},

        Благодарим вас за регистрацию в базе данных компании CAEC GmbH. Вам присвоен уникальный код: {client_code}.

        Этот код облегчит ваш вход в систему и позволит нам поддерживать с вами связь согласно вашим текущим интересам.

        Пожалуйста, сохраните этот код для дальнейшего использования.

        С уважением,
        Команда CAEC GmbH
        """

        msg = MIMEMultipart()
        msg["From"] = smtp_username
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # Подключаемся к SMTP-серверу и отправляем письмо
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, to_email, msg.as_string())

        logger.info(f"Письмо успешно отправлено на {to_email}")
    except Exception as e:
        logger.error(f"Ошибка при отправке письма: {e}")

# Обновление статуса активности клиентов
def update_activity_status():
    try:
        df = load_client_data()
        current_date = datetime.now()
        one_year_ago = current_date - timedelta(days=365)

        # Обновляем статус для клиентов, которые не активны более года
        df.loc[(pd.to_datetime(df["Last Visit"]) < one_year_ago), "Activity Status"] = "Not Active"

        # Сортируем таблицу: неактивные клиенты на первых строках
        df = df.sort_values(by=["Activity Status"], ascending=True)

        # Сохраняем обновленные данные
        df.to_excel("ClientData.xlsx", index=False)
        logger.info("Статус активности клиентов обновлен.")
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса активности: {e}")

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
            "phone": phone,
            "isNewClient": False  # Указываем, что клиент не новый
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

    # Отправляем email клиенту
    send_email(email, client_code, name)

    # Обновляем статус активности клиентов
    update_activity_status()

    return {
        "uniqueCode": client_code,
        "message": f"Добро пожаловать, {name}! Ваш код: {client_code}.",
        "name": name,
        "email": email,
        "phone": phone,
        "isNewClient": True  # Указываем, что клиент новый
    }

# Верификация кода клиента
def verify_client_code(code):
    df = load_client_data()
    code = str(code)  # Преобразуем код к строковому типу
    client_data = df[df["Client Code"] == code]
    if not client_data.empty:
        return client_data.iloc[0].to_dict()
    return None
