import os
import logging
import re
from price import get_ferry_prices  # Импортируем функцию для получения тарифов с сайта
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Функции для извлечения длины и определения категории транспортного средства ---

def extract_length(text):
    """
    Извлекает числовое значение длины (в метрах) из текста.
    Возвращает число или None, если длина не найдена.
    """
    match = re.search(r'(\d+)\s*(м|метров)', text.lower())
    if match:
        return int(match.group(1))
    return None

def determine_vehicle_category(length):
    """
    Определяет категорию транспортного средства на основе длины.
    Допустимые диапазоны:
      - Если длина >17 и <=20, возвращается "Road Train (up to 20 M)"
      - Если длина <=17 и >14, возвращается "Standard truck with trailer (up to 17M)"
      - Если длина <=14 и >10, возвращается "Trailer (up to 14 m)"
      - Если длина <=10 и >8, возвращается "Truck (up to 10M)"
      - Если длина <=8, возвращается "Mini truck (up to 8M)"
    Если длина не попадает ни в один диапазон, возвращается None.
    """
    if length is None:
        return None
    if length > 17 and length <= 20:
        return "Road Train (up to 20 M)"
    elif length <= 17 and length > 14:
        return "Standard truck with trailer (up to 17M)"
    elif length <= 14 and length > 10:
        return "Trailer (up to 14 m)"
    elif length <= 10 and length > 8:
        return "Truck (up to 10M)"
    elif length <= 8:
        return "Mini truck (up to 8M)"
    return None

# --- Функция для получения цены с сайта (без использования данных из price.xlsx) ---

def check_ferry_price_from_site(vehicle_category, direction="Ro_Ge"):
    """
    Получает тариф исключительно с сайта, используя get_ferry_prices() из файла price.py.
    
    direction: 
      - "Ro_Ge" для направления Romania -> Georgia,
      - "Ge_Ro" для направления Georgia -> Romania.
    
    Логика:
      1. Получаем актуальные тарифы с сайта.
      2. Если для заданного типа транспортного средства данные отсутствуют, возвращаем сообщение об отсутствии данных.
      3. Иначе возвращаем цену с сайта (приоритетное значение).
    """
    try:
        website_prices = get_ferry_prices()
        
        if vehicle_category not in website_prices:
            return f"Извините, тариф для '{vehicle_category}' не найден на сайте."
        
        if direction == "Ro_Ge":
            website_price = website_prices[vehicle_category].get("price_Ro_Ge", "")
        else:
            website_price = website_prices[vehicle_category].get("price_Ge_Ro", "")
        
        response_message = f"Цена перевозки для '{vehicle_category}' ({direction.replace('_', ' ')}) составляет {website_price}."
        if website_prices[vehicle_category].get("remark"):
            response_message += f" Примечание: {website_prices[vehicle_category]['remark']}"
        return response_message
    except Exception as e:
        logger.error(f"Ошибка при получении цены с сайта: {e}")
        return "Произошла ошибка при получении цены с сайта. Пожалуйста, попробуйте позже."

# Для обеспечения обратной совместимости с сервером,
# назначаем функцию check_ferry_price как временную обёртку для check_ferry_price_from_site.
check_ferry_price = check_ferry_price_from_site

# --- Функция загрузки данных из файла price.xlsx (пока не используется при отладке) ---
def load_price_data():
    """
    Загружает данные из Google Sheets (Price.xlsx) для тарифов.
    Ожидается, что таблица имеет следующие столбцы:
      A: Type of the vehicle
      B: Price_Ro_Ge (направление: Romania -> Georgia)
      C: Price_Ge_Ro (направление: Georgia -> Romania)
      D: Remark
      E: Condition1
      F: Condition2
      G: Condition3
    Возвращает словарь вида:
      {
         "VehicleType1": {
             "price_Ro_Ge": "...",
             "price_Ge_Ro": "...",
             "remark": "...",
             "conditions": [ "Condition1 текст", "Condition2 текст", "Condition3 текст" ]
         },
         ...
      }
    """
    try:
        service = get_sheets_service()
        range_name = "Sheet1!A2:G"
        result = service.spreadsheets().values().get(
            spreadsheetId=os.getenv("PRICE_SPREADSHEET_ID", "1N4VpU1rBw3_MPx6GJRDiSQ03iHhS24noTq5-i6V01z8"),
            range=range_name
        ).execute()
        values = result.get("values", [])
        price_data = {}
        for row in values:
            if len(row) < 4:
                continue
            vehicle_type = row[0].strip()
            price_Ro_Ge = row[1].strip() if len(row) > 1 else ""
            price_Ge_Ro = row[2].strip() if len(row) > 2 else ""
            remark = row[3].strip() if len(row) > 3 else ""
            conditions = []
            if len(row) > 4 and row[4].strip():
                conditions.append(row[4].strip())
            if len(row) > 5 and row[5].strip():
                conditions.append(row[5].strip())
            if len(row) > 6 and row[6].strip():
                conditions.append(row[6].strip())
            price_data[vehicle_type] = {
                "price_Ro_Ge": price_Ro_Ge,
                "price_Ge_Ro": price_Ge_Ro,
                "remark": remark,
                "conditions": conditions
            }
        logger.info(f"Данные из Price.xlsx загружены: {price_data}")
        return price_data
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из Price.xlsx: {e}")
        raise

def get_sheets_service():
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        credentials = Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        raise

# --- Пример тестирования логики в режиме отладки ---
if __name__ == "__main__":
    sample_text = "Фура 17 метров, Констанца-Поти, без ADR, без водителя"
    length = extract_length(sample_text)
    if length is None:
        print("Пожалуйста, уточните длину вашего транспортного средства (например, до 20, до 17, до 14, до 10 или до 8 метров).")
    else:
        vehicle_category = determine_vehicle_category(length)
        if vehicle_category:
            print(f"Определена категория: {vehicle_category}")
            price_info = check_ferry_price(vehicle_category, direction="Ro_Ge")
            print(price_info)
        else:
            print("Не удалось определить категорию по длине. Пожалуйста, уточните параметры транспортного средства.")
