# bible_bot.py
import os
import logging
from flask import Blueprint, request
from telegram import Update, Bot
from telegram.ext import (
    Dispatcher,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext
)

# Создаем blueprint
bible_bp = Blueprint('bible', __name__)

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
ASK_ACTION, ASK_QUESTION, ASK_ANSWER = range(3)

# Инициализируем бота и диспетчера
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("Переменная окружения TELEGRAM_BOT_TOKEN не задана!")
    raise Exception("TELEGRAM_BOT_TOKEN не задан")
bot = Bot(TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# Обработчики для команды /bible

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
    # Здесь необходимо добавить сохранение пары (question, answer) в Bible.xlsx с Verification="Check"
    logger.info(f"Сохраняем пару: Вопрос: {question} | Ответ: {answer}")
    update.message.reply_text("Пара вопрос-ответ сохранена с отметкой 'Check'.")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

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

# Маршрут для вебхука, по которому Telegram будет отправлять обновления
@bible_bp.route('/webhook', methods=['POST'])
def webhook_handler():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'OK', 200

# Тестовый маршрут, чтобы проверить, что Flask-приложение работает
@bible_bp.route('/webhook_test', methods=['GET'])
def webhook_test():
    return "Webhook endpoint is active", 200
