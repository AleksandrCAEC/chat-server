 1  import os
 2  from google.oauth2.service_account import Credentials
 3  from googleapiclient.discovery import build
 4  import pandas as pd
 5  from datetime import datetime
 6  import logging
 7  import uuid
 8  
 9  # Настройка логирования
10  logging.basicConfig(level=logging.INFO)
11  logger = logging.getLogger(__name__)
12  
13  # Путь к подпапке BIG_DATA внутри проекта
14  BIG_DATA_PATH = "./data/BIG_DATA"
15  
16  # Убедимся, что директория BIG_DATA существует
17  os.makedirs(BIG_DATA_PATH, exist_ok=True)
18  
19  # Путь к файлу ClientData.xlsx
20  CLIENT_DATA_FILE = os.path.join(BIG_DATA_PATH, "ClientData.xlsx")
21  
22  # Инициализация ClientData.xlsx, если файл не существует
23  def initialize_client_data():
24      if not os.path.exists(CLIENT_DATA_FILE):
25          columns = ["Client Code", "Name", "Phone", "Email", "Created Date", "Last Visit", "Activity Status"]
26          df = pd.DataFrame(columns=columns)
27          df.to_excel(CLIENT_DATA_FILE, index=False)
28          logger.info("Инициализирован новый файл ClientData.xlsx")
29  
30  # Загрузка ClientData.xlsx
31  def load_client_data():
32      try:
33          if not os.path.exists(CLIENT_DATA_FILE):
34              initialize_client_data()
35          return pd.read_excel(CLIENT_DATA_FILE)
36      except Exception as e:
37          logger.error(f"Ошибка загрузки данных: {e}")
38          initialize_client_data()
39          return load_client_data()
40  
41  # Сохранение изменений в ClientData.xlsx и Google Sheets
42  def save_client_data(client_code, name, phone, email, created_date, last_visit, activity_status):
43      try:
44          logger.info("Подключение к Google Sheets...")
45          credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
46          sheets_service = build('sheets', 'v4', credentials=credentials)
47  
48          spreadsheet_id = "1M-mRD32sQtkvTRcik7jq1n8ZshXhEearsaIBcFlheZk"
49          range_name = "Sheet1!A2:G1000"
50  
51          values = [[client_code, name, phone, email, created_date, last_visit, activity_status]]
52          body = {'values': values}
53  
54          logger.info(f"Отправка данных в Google Sheets: {values}")
55  
56          response = sheets_service.spreadsheets().values().append(
57              spreadsheetId=spreadsheet_id,
58              range=range_name,
59              valueInputOption="RAW",
60              body=body
61          ).execute()
62  
63          logger.info(f"Ответ от Google API: {response}")
64      except Exception as e:
65          logger.error(f"Ошибка записи в Google Sheets: {e}")
66  
67      # Сохранение в локальный файл ClientData.xlsx
68      df = load_client_data()
69      existing_client = df[df["Client Code"] == client_code]
70  
71      if existing_client.empty:
72          new_data = pd.DataFrame([{ 
73              "Client Code": client_code,
74              "Name": name,
75              "Phone": phone,
76              "Email": email,
77              "Created Date": created_date,
78              "Last Visit": last_visit,
79              "Activity Status": activity_status
80          }])
81          df = pd.concat([df, new_data], ignore_index=True)
82      else:
83          df.loc[df["Client Code"] == client_code, ["Name", "Phone", "Email", "Last Visit", "Activity Status"]] = [name, phone, email, last_visit, activity_status]
84  
85      df.to_excel(CLIENT_DATA_FILE, index=False)
86      logger.info(f"Данные сохранены в ClientData.xlsx: {client_code}, {name}, {phone}, {email}")
87  
88  # Генерация уникального кода клиента
89  def generate_unique_code():
90      existing_codes = set(load_client_data()["Client Code"])
91      while True:
92          code = f"CAEC{uuid.uuid4().hex[:7].upper()}"
93          if code not in existing_codes:
94              return code
95  
96  # Регистрация или обновление клиента
97  def register_or_update_client(data):
98      initialize_client_data()
99      df = load_client_data()
100 
101     email = data.get("email")
102     phone = data.get("phone")
103     name = data.get("name", "Unknown")
104 
105     # Проверка на существующего клиента
106     existing_client = df[(df["Email"] == email) | (df["Phone"] == phone)]
107 
108     if not existing_client.empty:
109         client_code = existing_client.iloc[0]["Client Code"]
110         last_visit = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
111         save_client_data(client_code, name, phone, email, existing_client.iloc[0]["Created Date"], last_visit, "Active")
112         return {
113             "uniqueCode": client_code,
114             "message": f"Добро пожаловать обратно, {name}! Ваш код: {client_code}.",
115         }
116 
117     # Регистрация нового клиента
118     client_code = generate_unique_code()
119     created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
120     last_visit = created_date
121     activity_status = "Active"
122 
123     new_client = {
124         "Client Code": client_code,
125         "Name": name,
126         "Phone": phone,
127         "Email": email,
128         "Created Date": created_date,
129         "Last Visit": last_visit,
130         "Activity Status": activity_status
131     }
132     df = pd.concat([df, pd.DataFrame([new_client])], ignore_index=True)
133     save_client_data(client_code, name, phone, email, created_date, last_visit, activity_status)
134 
135     # Создание файла клиента
136     create_client_file(client_code, new_client)
137 
138     return {
139         "uniqueCode": client_code,
140         "message": f"Добро пожаловать, {name}! Ваш код: {client_code}.",
141     }
142 
143 # Создание индивидуального файла клиента
144 def create_client_file(client_code, client_data):
145     client_file_path = os.path.join(BIG_DATA_PATH, f"{client_code}.xlsx")
146     columns = ["Date", "Message"]
147     df = pd.DataFrame(columns=columns)
148     df.to_excel(client_file_path, index=False)
149     logger.info(f"Создан файл клиента: {client_file_path}")
150 
151 # Инициализация системы при первом запуске
152 initialize_client_data()
