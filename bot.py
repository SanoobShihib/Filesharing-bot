
import os
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        "🤖 Welcome to Our File Sharing Bot!\n\n"
        "📁 File sharing features coming soon."
    )


# /help command
async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "ℹ️ Available Commands:\n\n"
        "/start - Start the bot\n"
        "/help - Show help"
    )


def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise ValueError("BOT_TOKEN is not set!")

    application = Application.builder().token(token).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    print("🤖 Bot is running...")

    application.run_polling()


if __name__ == "__main__":
    main()
