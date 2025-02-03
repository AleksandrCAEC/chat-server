import os
import pandas as pd
from openpyxl import Workbook, load_workbook
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("client_caec.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Функция для добавления сообщения в файл клиента
def add_message_to_client_file(client_code, message, is_assistant=False):
    try:
        file_name = f"./CAEC_API_Data/Data_CAEC_Client/Client_{client_code}.xlsx"

        # Открываем существующий файл или создаем новый, если он не существует
        if os.path.exists(file_name):
            wb = load_workbook(file_name)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            # Записываем заголовки, если файл новый
            ws.append(["Timestamp", "Message", "is_assistant"])

        # Добавляем новое сообщение
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append([timestamp, message, is_assistant])

        # Сохраняем файл
        wb.save(file_name)

        logger.info(f"Сообщение добавлено в файл клиента {client_code}.")
    except Exception as e:
        logger.error(f"Ошибка при добавлении сообщения в файл клиента: {e}")
        raise
