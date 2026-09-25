import asyncio
import logging
import os
import secrets
import threading

from pymongo import MongoClient

from config import (
    BOT_TOKEN,
    API_ID,
    API_HASH,
    CHANNELS,
    CHANNEL_INVITE_LINKS,
    DATABASE_URI,
    LOG_CHANNEL,
    ADMIN_ID,
)

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

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


PORT = int(os.getenv("PORT", "8000"))

pending_files = {}


# MongoDB Connection

mongo_client = MongoClient(DATABASE_URI)

mongo_db = mongo_client["leobot"]

file_groups_collection = mongo_db["file_groups"]

shared_files_collection = mongo_db["shared_files"]


# Health Server

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)

        self.send_header(
            "Content-type",
            "text/plain",
        )

        self.end_headers()

        self.wfile.write(
            b"Bot is running!"
        )

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

    print(
        f"Health server running on port {PORT}"
    )


# Database Initialization

def init_db():

    file_groups_collection.create_index(
        "share_token",
        unique=True,
    )

    shared_files_collection.create_index(
        "share_token",
    )


# Save File Group

def save_file_group(files, owner_id):

    share_token = secrets.token_urlsafe(8)

    file_groups_collection.insert_one(
        {
            "share_token": share_token,
            "owner_id": owner_id,
        }
    )

    shared_files_collection.insert_many(
        [
            {
                "share_token": share_token,
                "file_id": file_data["file_id"],
                "file_name": file_data["file_name"],
            }
            for file_data in files
        ]
    )

    return share_token


# Get Files

def get_files(share_token):

    return list(
        shared_files_collection.find(
            {
                "share_token": share_token,
            },
            {
                "_id": 0,
                "file_id": 1,
                "file_name": 1,
            },
        )
    )


# Auto Delete File Messages

async def delete_file_messages(
    bot,
    chat_id,
    message_ids,
):

    await asyncio.sleep(300)

    for message_id in message_ids:

        try:

            await bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
            )

            logger.info(
                f"Deleted file message: {message_id}"
            )

        except Exception:

            logger.exception(
                "Failed to delete file message"
            )


# Start Command

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

        sent_message_ids = []

        for file_data in files:

            sent_message = (
                await update.message.reply_document(
                    document=file_data["file_id"],
                    caption=(
                        f"📁 "
                        f"{file_data['file_name'] or 'Shared File'}"
                    ),
                )
            )

            sent_message_ids.append(
                sent_message.message_id
            )

        # Delete only bot-sent file messages
        # after 5 minutes

        asyncio.create_task(
            delete_file_messages(
                bot=context.bot,
                chat_id=update.effective_chat.id,
                message_ids=sent_message_ids,
            )
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
            InlineKeyboardButton(
                "📖 Help",
                callback_data="help",
            ),
            InlineKeyboardButton(
                "ℹ️ About",
                callback_data="about",
            ),
        ],
    ]

    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        "🤖 Welcome to Our File Sharing Bot!\n\n"
        "📤 Send multiple documents one by one.\n"
        "✅ Send /done to create one Share Link.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# Help Command

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
        "/done - Create one Share Link\n"
        "/stats - Show database statistics\n\n"
        "📤 Send multiple documents one by one."
    )


# Button Callback

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


# Handle Documents

async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message or not update.message.document:

        return

    document = update.message.document

    user = update.effective_user

    if user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Only admin can upload files."
        )

        return

    if user.id not in pending_files:

        pending_files[user.id] = []

    pending_files[user.id].append(
        {
            "file_id": document.file_id,
            "file_name": document.file_name,
        }
    )

    count = len(
        pending_files[user.id]
    )

    await update.message.reply_text(
        f"✅ File {count} added!\n\n"
        "📤 Send more files or use /done."
    )


# Done Command

async def done_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:

        return

    user = update.effective_user

    user_files = pending_files.get(
        user.id,
        [],
    )

    if user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Only admin can create share links."
        )

        return

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
        f"https://t.me/{bot_username}"
        f"?start=file_{share_token}"
    )

    file_count = len(user_files)

    await update.message.reply_text(
        "🎉 Share Link Created!\n\n"
        f"📦 Total Files: {file_count}\n\n"
        f"🔗 Share Link:\n{share_link}\n\n"
        "Anyone who opens this link can receive "
        "all shared files."
    )

    pending_files.pop(
        user.id,
        None,
    )


# Stats Command

async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:

        return

    user = update.effective_user

    if not user or user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ You are not authorized to use this command."
        )

        return

    try:

        total_files = (
            shared_files_collection.count_documents({})
        )

        total_groups = (
            file_groups_collection.count_documents({})
        )

        await update.message.reply_text(
            "📊 Leobot Database Statistics\n\n"
            f"📁 Total Files: {total_files}\n"
            f"📦 Total File Groups: {total_groups}\n"
            "🗄️ Database: MongoDB"
        )

    except Exception:

        logger.exception(
            "Stats command failed"
        )

        await update.message.reply_text(
            "❌ Unable to fetch database statistics."
        )


# Main Function

def main():

    token = BOT_TOKEN

    if not token:

        raise ValueError(
            "BOT_TOKEN is not set!"
        )

    init_db()

    start_health_server()

    application = (
        Application.builder()
        .token(token)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "done",
            done_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "stats",
            stats_command,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            button_callback,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_document,
        )
    )

    print(
        "🤖 File Sharing Bot is running..."
    )

    application.run_polling()


if __name__ == "__main__":

    main()
