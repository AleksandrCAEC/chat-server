import os
import logging
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext
from flask import Flask, request

# Инициализация Flask-приложения
app = Flask(__name__)

# Добавляем тестовый маршрут
@app.route('/webhook_test', methods=['GET'])
def webhook_test():
    return "Webhook endpoint is active", 200

# Здесь размещается остальной код (обработчики, настройка Dispatcher, маршруты и т.д.)

# Пример маршрута вебхука:
@app.route('/webhook', methods=['POST'])
def webhook_handler():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'OK', 200

# Основной блок запуска
if __name__ == '__main__':
    PORT = int(os.getenv("PORT", "8080"))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logging.error("Переменная окружения WEBHOOK_URL не задана!")
        exit(1)
    bot.setWebhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен на {WEBHOOK_URL}")
    app.run(host='0.0.0.0', port=PORT)
