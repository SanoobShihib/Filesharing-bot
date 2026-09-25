import logging
import os
import secrets
import sqlite3

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "files.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                share_token TEXT UNIQUE NOT NULL,
                file_id TEXT NOT NULL,
                file_name TEXT,
                owner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save_file(file_id, file_name, owner_id):
    share_token = secrets.token_urlsafe(8)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO files (
                share_token,
                file_id,
                file_name,
                owner_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                share_token,
                file_id,
                file_name,
                owner_id,
            ),
        )
        conn.commit()

    return share_token


def get_file(share_token):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT file_id, file_name
            FROM files
            WHERE share_token = ?
            """,
            (share_token,),
        ).fetchone()

    return row


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    if context.args:
        share_token = context.args[0]

        if share_token.startswith("file_"):
            share_token = share_token[5:]

        file_data = get_file(share_token)

        if not file_data:
            await update.message.reply_text(
                "❌ File not found or link is invalid."
            )
            return

        await update.message.reply_document(
            document=file_data["file_id"],
            caption=(
                f"📁 {file_data['file_name'] or 'Shared File'}"
            ),
        )
        return

    user = update.effective_user

    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        "🤖 Welcome to Our File Sharing Bot!\n\n"
        "📤 Send me a document to create a share link.\n"
        "📥 Open a share link to receive a file."
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    await update.message.reply_text(
        "ℹ️ Available Commands:\n\n"
        "/start - Start the bot\n"
        "/help - Show help\n\n"
        "📤 Send a document to create a share link."
    )


async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.document:
        return

    document = update.message.document
    user = update.effective_user

    share_token = save_file(
        file_id=document.file_id,
        file_name=document.file_name,
        owner_id=user.id,
    )

    bot_username = context.bot.username

    share_link = (
        f"https://t.me/{bot_username}?start=file_{share_token}"
    )

    await update.message.reply_text(
        "✅ File uploaded successfully!\n\n"
        f"📁 Name: {document.file_name or 'Unknown'}\n\n"
        f"🔗 Share Link:\n{share_link}\n\n"
        "Anyone who opens this link through Telegram "
        "can receive the file."
    )


def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise ValueError("BOT_TOKEN is not set!")

    init_db()

    application = Application.builder().token(token).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_document,
        )
    )

    print("🤖 File Sharing Bot is running...")

    application.run_polling()


if __name__ == "__main__":
    main()
