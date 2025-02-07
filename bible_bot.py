import os
import logging
from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext
)

# Состояния для ConversationHandler
ASK_ACTION, ASK_QUESTION, ASK_ANSWER = range(3)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
        update.message.reply_text("Неверное значение. Введите 'add' для добавления или 'cancel' для отмены.")
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

def main():
    # Чтение токена из переменной окружения ELEGRAM_BOT_TOKEN
    TELEGRAM_BOT_TOKEN = os.getenv("ELEGRAM_BOT_TOKEN")
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Переменная окружения ELEGRAM_BOT_TOKEN не задана!")
        return

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

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
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
