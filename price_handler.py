import os
import logging
import re
import string
from price import get_ferry_prices  # Убедитесь, что этот модуль возвращает данные с сайта
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from bible import load_bible_data  # Для получения пояснений из Bible.xlsx

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Spreadsheet ID для файла Price.xlsx
PRICE_SPREADSHEET_ID = "1N4VpU1rBw3_MPx6GJRDiSQ03iHhS24noTq5-i6V01z8"

def get_sheets_service():
    try:
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        return build('sheets', 'v4', credentials=credentials)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets API: {e}")
        raise

def load_price_data():
    """
    Загружает данные из Google Sheets (Price.xlsx).
    Ожидается, что таблица имеет следующие столбцы:
      A: Наименование тарифа (например, "Standard truck with trailer (up to 17M)")
      B: Цена (Констанца-Поти)
      C: Цена (Поти-Констанца)
      D: Round trip
      E и далее: Дополнительные условия (Condition1, Condition2, …) – "1" означает активное условие.
    Возвращает словарь вида:
      {
         "Standard truck with trailer (up to 17M)": {
             "price_Ro_Ge": "2200",
             "price_Ge_Ro": "1090",
             "round_trip": "3060",
             "conditions": [ "1", "0", ... ]
         },
         ...
      }
    """
    try:
        service = get_sheets_service()
        range_name = "Sheet1!A2:G"
        result = service.spreadsheets().values().get(
            spreadsheetId=PRICE_SPREADSHEET_ID,
            range=range_name
        ).execute()
        values = result.get("values", [])
        if not values:
            logger.error("Пустые данные, полученные из Price.xlsx.")
            return {}
        price_data = {}
        for row in values:
            if len(row) < 4:
                continue
            tariff_name = row[0].strip()
            price_Ro_Ge = row[1].strip() if len(row) > 1 else ""
            price_Ge_Ro = row[2].strip() if len(row) > 2 else ""
            round_trip = row[3].strip() if len(row) > 3 else ""
            conditions = []
            for i in range(4, len(row)):
                conditions.append(row[i].strip())
            price_data[tariff_name] = {
                "price_Ro_Ge": price_Ro_Ge,
                "price_Ge_Ro": price_Ge_Ro,
                "round_trip": round_trip,
                "conditions": conditions
            }
        logger.info(f"Данные из Price.xlsx: {price_data}")
        return price_data
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из Price.xlsx: {e}")
        return {}

def send_telegram_notification(message):
    """
    Отправляет уведомление через Telegram, используя переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID.
    """
    try:
        import requests
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if telegram_bot_token and telegram_chat_id:
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "HTML"}
            requests.post(url, json=payload)
    except Exception as ex:
        logger.error(f"Ошибка при отправке уведомления: {ex}")

def extract_numeric(price_str):
    """
    Извлекает числовое значение из строки с ценой, удаляя лишние символы (например, валюту).
    Возвращает float или None, если извлечение не удалось.
    """
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    if cleaned.count(',') > 0 and cleaned.count('.') == 0:
        cleaned = cleaned.replace(',', '.')
    elif cleaned.count(',') > 0 and cleaned.count('.') > 0:
        cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None

def extract_vehicle_size(query):
    """
    Извлекает размер (число метров) из запроса.
    Пример: "17 метров" или "17m" вернет число 17.
    """
    match = re.search(r'(\d{1,2})\s*(m|м|метр)', query.lower())
    if match:
        return int(match.group(1))
    return None

def normalize_text(text):
    """
    Приводит текст к нижнему регистру, удаляет пунктуацию и лишние пробелы.
    """
    text = text.lower()
    text = re.sub(f'[{re.escape(string.punctuation)}]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def select_vehicle_record(query, price_data):
    """
    Определяет, какой тариф из price_data подходит для запроса.
    Использует синонимы для грузовика и анализирует размер транспортного средства.
    Также, если в запросе упоминается "trailer", выбирает тариф, содержащий этот термин.
    Работает с нормализованными строками.
    """
    synonyms = ['truck', 'грузовик', 'фура', 'еврофура', 'трайлер', 'трас']
    trailer_keywords = ['trailer', 'трейлер']
    query_norm = normalize_text(query)
    size = extract_vehicle_size(query)
    
    candidate = None
    best_score = 0
    for key in price_data.keys():
        key_norm = normalize_text(key)
        score = 0
        # Учитываем синонимы: если хотя бы один найден и в запросе, и в тарифе
        for syn in synonyms:
            if syn in query_norm and syn in key_norm:
                score += 1
        # Если запрос содержит "trailer", тариф должен содержать это слово
        if any(t in query_norm for t in trailer_keywords):
            if any(t in key_norm for t in trailer_keywords):
                score += 1
            else:
                continue  # тариф не подходит
        # Учитываем размер
        size_match = re.search(r'(\d+)\s*(m|м)', key_norm)
        if size_match:
            max_size = int(size_match.group(1))
            if size is not None and size <= max_size:
                score += 1
            else:
                continue  # тариф не подходит по размеру
        if score > best_score:
            best_score = score
            candidate = key
    logger.info(f"Выбран тариф: {candidate} для запроса: '{query_norm}', размер: {size}, score: {best_score}")
    return candidate

def get_condition_detail(condition_index):
    """
    Для заданного индекса условия (ConditionX) ищет в Bible.xlsx строку, где в столбце Verification
    содержится точное значение "ConditionX" (например, для condition_index=2 ищется "Condition3").
    Возвращает кортеж (detail_text, extra_cost) из столбца Answers.
    """
    condition_key = f"Condition{condition_index + 1}"
    bible_df = load_bible_data()
    for index, row in bible_df.iterrows():
        verification_val = str(row.get("Verification", "")).strip()
        if verification_val.lower() == condition_key.lower():
            detail_text = row.get("Answers", "").strip()
            extra_cost = extract_numeric(detail_text)
            return detail_text, extra_cost
    return None, None

def check_ferry_price(query, direction="Ro_Ge", client_guiding_answers=None):
    """
    Основная функция расчёта цены.
    1. На основе запроса выбирается тариф из Price.xlsx с учетом синонимов и размера (через select_vehicle_record()).
    2. Получается базовая цена (приоритет – данные с сайта, затем из Price.xlsx).
    3. Если в записи активны дополнительные условия (Condition) и клиент подтвердил их (через guiding answers),
       для каждого активного условия вызывается get_condition_detail() для получения пояснения и возможной доплаты.
    4. Итоговый ответ включает:
         - Базовую цену перевозки (с указанием источника),
         - Перечень дополнительных услуг с пояснениями и их суммарную стоимость,
         - Итоговую стоимость (базовая цена + доплаты).
    """
    try:
        price_data = load_price_data()
        if not price_data:
            return "Ошибка считывания данных из Price.xlsx."
        record_key = select_vehicle_record(query, price_data)
        if not record_key:
            return f"Извините, информация о тарифах для данного запроса отсутствует в нашей базе."
        
        website_prices = get_ferry_prices()
        if not website_prices:
            logger.error("Данные с сайта не получены.")
        website_raw = website_prices.get(record_key, {}).get("price_Ro_Ge", "") if website_prices else ""
        sheet_raw = price_data.get(record_key, {}).get("price_Ro_Ge", "")
        website_price_numeric = extract_numeric(website_raw)
        sheet_price_numeric = extract_numeric(sheet_raw)
        
        if website_price_numeric is not None:
            base_price = website_price_numeric
            source_used = "сайта"
        elif sheet_price_numeric is not None:
            base_price = sheet_price_numeric
            source_used = "базы"
        else:
            send_telegram_notification(f"Ошибка: Нет данных о тарифе для '{record_key}'.")
            return f"Извините, тариф для '{record_key}' недоступен."
        
        if website_price_numeric is not None and sheet_price_numeric is not None:
            if abs(website_price_numeric - sheet_price_numeric) > 0.001:
                send_telegram_notification(f"ВНИМАНИЕ: Для тарифа '{record_key}' цены различаются: сайт {website_raw} и база {sheet_raw}.")
                return f"Тариф для '{record_key}' требует уточнения. Пожалуйста, свяжитесь с менеджером."
            base_price = website_price_numeric
            source_used = "сайта"
        
        remark = price_data.get(record_key, {}).get("remark", "")
        conditions = price_data.get(record_key, {}).get("conditions", [])
        
        additional_total = 0.0
        active_conditions_details = []
        if client_guiding_answers and conditions:
            for i, cond in enumerate(conditions):
                if cond == "1" and i < len(client_guiding_answers):
                    answer = client_guiding_answers[i].strip().lower()
                    if answer:
                        detail_text, extra_cost = get_condition_detail(i)
                        if detail_text:
                            active_conditions_details.append(detail_text)
                        if extra_cost is not None:
                            additional_total += extra_cost
        
        total_price = base_price + additional_total
        
        response_message = f"Базовая цена для '{record_key}' ({direction.replace('_', ' ')}) составляет {base_price} евро (данные из {source_used})."
        if remark:
            response_message += f"\nПримечание: {remark}"
        if active_conditions_details:
            response_message += "\n\nДополнительные услуги:"
            for detail in active_conditions_details:
                response_message += f"\n- {detail}"
            response_message += f"\nСуммарная стоимость дополнительных услуг: {additional_total} евро."
            response_message += f"\n\nИтоговая стоимость перевозки: {total_price} евро."
        else:
            response_message += f"\n\nИтоговая стоимость перевозки: {base_price} евро."
        return response_message
    except Exception as e:
        error_msg = f"Ошибка при расчёте тарифа для запроса '{query}': {e}"
        logger.error(error_msg)
        send_telegram_notification(error_msg)
        return "Произошла ошибка при получении цены. Пожалуйста, попробуйте позже."

def get_price_response(vehicle_query, direction="Ro_Ge", client_guiding_answers=None):
    try:
        response = check_ferry_price(vehicle_query, direction, client_guiding_answers)
        return response
    except Exception as e:
        logger.error(f"Ошибка при получении цены для запроса '{vehicle_query}': {e}")
        return "Произошла ошибка при получении актуальной цены. Пожалуйста, попробуйте позже."

if __name__ == "__main__":
    # Пример тестирования: точный запрос, как указано
    test_query = "Standard truck with trailer (up to 17M)"
    guiding_answers = []  # если дополнительные условия не подтверждены
    message = check_ferry_price(test_query, direction="Ro_Ge", client_guiding_answers=guiding_answers)
    print(message)
