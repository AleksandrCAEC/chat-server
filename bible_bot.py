import os
import logging
from telegram import Update, Bot
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext
)
from flask import Flask, request

# Состояния для ConversationHandler
ASK_ACTION, ASK_QUESTION, ASK_ANSWER = range(3)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализируем Flask-приложение
app = Flask(__name__)

# Функции-обработчики для диалога /bible

def bible_start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "Введите 'add' для добавления новой пары вопрос-ответ, или 'cancel' для отмены."
    )
    return ASK_ACTION

def ask_action(update: Update, context: CallbackContext) -> int:
    action = update.message.text.strip().lower()
    if action == "add":
        context.user_data['action'] = 'add'
        update.message.reply_text("Введите новый вопрос:")
        return ASK_QUESTION
    else:
        update.message.reply_text("Неверное значение. Введите 'add' или 'cancel'.")
        return ASK_ACTION

def ask_question(update: Update, context: CallbackContext) -> int:
    question = update.message.text.strip()
    context.user_data['question'] = question
    update.message.reply_text("Введите ответ для этого вопроса:")
    return ASK_ANSWER

def ask_answer(update: Update, context: CallbackContext) -> int:
    answer = update.message.text.strip()
    question = context.user_data.get('question')
    # Здесь необходимо вызвать функцию сохранения данных в Bible.xlsx,
    # например: save_bible_pair(question, answer)
    # В данном примере просто логируем полученную пару.
    logger.info(f"Сохраняем пару: Вопрос: {question} | Ответ: {answer}")
    update.message.reply_text("Пара вопрос-ответ сохранена с отметкой 'Check'.")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# Настройка Dispatcher
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("Переменная окружения TELEGRAM_BOT_TOKEN не задана!")
    exit(1)

bot = Bot(TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('bible', bible_start)],
    states={
        ASK_ACTION: [MessageHandler(Filters.text & ~Filters.command, ask_action)],
        ASK_QUESTION: [MessageHandler(Filters.text & ~Filters.command, ask_question)],
        ASK_ANSWER: [MessageHandler(Filters.text & ~Filters.command, ask_answer)],
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)
dispatcher.add_handler(conv_handler)

# Маршрут для приёма вебхуков
@app.route('/webhook', methods=['POST'])
def webhook_handler():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'OK', 200

if __name__ == '__main__':
    PORT = int(os.getenv("PORT", "8080"))
    # Переменная окружения WEBHOOK_URL должна содержать публичный URL вашего сервиса с путём /webhook, например:
    # https://your-cloud-run-url/webhook
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        logger.error("Переменная окружения WEBHOOK_URL не задана!")
        exit(1)
    bot.setWebhook(WEBHOOK_URL)
    logger.info(f"Webhook установлен на {WEBHOOK_URL}")
    app.run(host='0.0.0.0', port=PORT)
