import logging
import os
import secrets
import sqlite3
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "files.db")
PORT = int(os.getenv("PORT", "8000"))

pending_files = {}


class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def log_message(self, format, *args):
        return


def start_health_server():
    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler,
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )

    thread.start()

    print(f"Health server running on port {PORT}")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                share_token TEXT UNIQUE NOT NULL,
                owner_id INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS shared_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                share_token TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_name TEXT
            )
        """)

        conn.commit()


def save_file_group(files, owner_id):
    share_token = secrets.token_urlsafe(8)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO file_groups (
                share_token,
                owner_id
            )
            VALUES (?, ?)
            """,
            (share_token, owner_id),
        )

        for file_data in files:
            conn.execute(
                """
                INSERT INTO shared_files (
                    share_token,
                    file_id,
                    file_name
                )
                VALUES (?, ?, ?)
                """,
                (
                    share_token,
                    file_data["file_id"],
                    file_data["file_name"],
                ),
            )

        conn.commit()

    return share_token


def get_files(share_token):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT file_id, file_name
            FROM shared_files
            WHERE share_token = ?
            """,
            (share_token,),
        ).fetchall()

    return rows


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

        files = get_files(share_token)

        if not files:
            await update.message.reply_text(
                "❌ Files not found or link is invalid."
            )
            return

        await update.message.reply_text(
            f"📦 {len(files)} files found.\n"
            "📥 Sending your files..."
        )

        for file_data in files:
            await update.message.reply_document(
                document=file_data["file_id"],
                caption=(
                    f"📁 {file_data['file_name'] or 'Shared File'}"
                ),
            )

        return

    user = update.effective_user

    keyboard = [
        [
            InlineKeyboardButton(
                "📢 Join Update Channel",
                url="https://t.me/Clmainchannel",
            )
        ],
        [
            InlineKeyboardButton("📖 Help", callback_data="help"),
            InlineKeyboardButton("ℹ️ About", callback_data="about"),
        ],
    ]

    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        "🤖 Welcome to Our File Sharing Bot!\n\n"
        "📤 Send multiple documents one by one.\n"
        "✅ Send /done to create one Share Link.",
        reply_markup=InlineKeyboardMarkup(keyboard),
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
        "/help - Show help\n"
        "/done - Create one Share Link\n\n"
        "📤 Send multiple documents one by one."
    )

async def button_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        await query.edit_message_text(
            "📖 Help\n\n"
            "📤 Send your files one by one.\n"
            "✅ After sending all files, use /done.\n"
            "🔗 You will receive one share link."
        )

    elif query.data == "about":
        await query.edit_message_text(
            "ℹ️ About\n\n"
            "🤖 File Sharing Bot\n"
            "📁 Share multiple files using one link."
        )
async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.document:
        return

    document = update.message.document
    user = update.effective_user

    if user.id not in pending_files:
        pending_files[user.id] = []

    pending_files[user.id].append(
        {
            "file_id": document.file_id,
            "file_name": document.file_name,
        }
    )

    count = len(pending_files[user.id])

    await update.message.reply_text(
        f"✅ File {count} added!\n\n"
        "📤 Send more files or use /done."
    )


async def done_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    user = update.effective_user
    user_files = pending_files.get(user.id, [])

    if not user_files:
        await update.message.reply_text(
            "❌ No files added yet.\n"
            "Please send some documents first."
        )
        return

    share_token = save_file_group(
        files=user_files,
        owner_id=user.id,
    )

    bot_username = context.bot.username

    share_link = (
        f"https://t.me/{bot_username}?start=file_{share_token}"
    )

    file_count = len(user_files)

    await update.message.reply_text(
        "🎉 Share Link Created!\n\n"
        f"📦 Total Files: {file_count}\n\n"
        f"🔗 Share Link:\n{share_link}\n\n"
        "Anyone who opens this link can receive "
        "all shared files."
    )

    pending_files.pop(user.id, None)


def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise ValueError("BOT_TOKEN is not set!")

    init_db()
    start_health_server()

    application = Application.builder().token(token).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("done", done_command)
    )
    
    application.add_handler(
        CallbackQueryHandler(button_callback)
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
