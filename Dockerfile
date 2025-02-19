FROM python:3.10

WORKDIR /app

# Копирование файла с учётными данными
COPY service_account.json /app/service_account.json

# Установка переменной окружения
ENV GOOGLE_APPLICATION_CREDENTIALS="/app/service_account.json"

# Копирование requirements.txt и установка зависимостей
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Установка nltk и загрузка необходимых ресурсов
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet')"

# Копирование остальных файлов
COPY . .

EXPOSE 8080

CMD ["python", "server.py"]
