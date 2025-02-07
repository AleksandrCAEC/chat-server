import os
import logging
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext
from flask import Flask, request

# Инициализация Flask-приложения
app = Flask(__name__)

# Добавляем тестовый маршрут для проверки
@app.route('/webhook_test', methods=['GET'])
def webhook_test():
    return "Webhook endpoint is active", 200

# Инициализируем бота и диспетчера
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logging.error("Переменная окружения TELEGRAM_BOT_TOKEN не задана!")
    exit(1)
bot = Bot(TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# Пример обработки команды /bible через ConversationHandler
# Состояния для ConversationHandler
ASK_ACTION, ASK_QUESTION, ASK_ANSWER = range(3)

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
    # Здесь можно вызвать функцию для сохранения данных в Bible.xlsx,
    # например, save_bible_pair(question, answer)
    logging.info(f"Сохраняем пару: Вопрос: {question} | Ответ: {answer}")
    update.message.reply_text("Пара вопрос-ответ сохранена с отметкой 'Check'.")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# Регистрируем ConversationHandler
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

# Определяем маршрут для вебхука
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
