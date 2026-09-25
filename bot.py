import asyncio
import logging
import os
import secrets
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


# =========================
# MongoDB
# =========================

mongo_client = MongoClient(DATABASE_URI)

mongo_db = mongo_client["leobot"]

file_groups_collection = mongo_db["file_groups"]

shared_files_collection = mongo_db["shared_files"]


def init_db():
    file_groups_collection.create_index("share_token", unique=True)
    shared_files_collection.create_index("share_token")


def save_file_group(files, owner_id):
    share_token = secrets.token_urlsafe(8)

    file_groups_collection.insert_one(
        {
            "share_token": share_token,
            "owner_id": owner_id,
            "files": files,
        }
    )

    return share_token


def get_files(share_token):
    group = file_groups_collection.find_one(
        {"share_token": share_token}
    )

    if not group:
        return []

    return group.get("files", [])


# =========================
# Health Server
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Leobot is running")

    def log_message(self, format, *args):
        return


def run_health_server():
    server = ThreadingHTTPServer(
        ("0.0.0.0", PORT),
        HealthHandler,
    )

    server.serve_forever()


# =========================
# Force Subscribe
# =========================

async def is_subscribed(bot, user_id):
    """
    Check whether the user joined all required channels.
    """

    if not CHANNELS:
        return True

    for channel_id in CHANNELS:
        try:
            member = await bot.get_chat_member(
                chat_id=int(channel_id),
                user_id=user_id,
            )

            logger.info(
                "Channel %s | User %s | Status: %s",
                channel_id,
                user_id,
                member.status,
            )

            if member.status in ["left", "kicked"]:
                return False

            if member.status == "restricted":
                if not getattr(member, "is_member", False):
                    return False

        except Exception:
            logger.exception(
                "Subscription check failed for channel %s",
                channel_id,
            )
            return False

    return True

def subscription_keyboard(share_token):

    keyboard = []

    for index, invite_link in enumerate(
        CHANNEL_INVITE_LINKS,
        start=1,
    ):

        if invite_link:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"📢 Join Channel {index}",
                        url=invite_link,
                    )
                ]
            )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔄 Try Again",
                callback_data=f"check_sub:{share_token}",
            )
        ]
    )

    return InlineKeyboardMarkup(keyboard)


async def send_subscription_message(
    message,
    share_token,
):

    await message.reply_text(
        "🔒 ആദ്യം ഞങ്ങളുടെ രണ്ട് ചാനലുകളിലും join ചെയ്യുക.\n\n"
        "Join ചെയ്ത ശേഷം താഴെയുള്ള Try Again അമർത്തുക.",
        reply_markup=subscription_keyboard(share_token),
    )


# =========================
# Delete Sent Files
# =========================

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

        except Exception:
            logger.exception(
                "Could not delete message %s",
                message_id,
            )


# =========================
# Send Shared Files
# =========================

async def send_shared_files(
    bot,
    chat_id,
    files,
):

    sent_message_ids = []

    intro_message = await bot.send_message(
        chat_id=chat_id,
        text="📂 നിങ്ങളുടെ files ഇതാ:",
    )

    sent_message_ids.append(
        intro_message.message_id
    )

    for file_data in files:

        try:

            sent_message = await bot.send_document(
                chat_id=chat_id,
                document=file_data["file_id"],
                caption=file_data.get("caption", ""),
            )

            sent_message_ids.append(
                sent_message.message_id
            )

        except Exception:
            logger.exception("File sending failed")

    asyncio.create_task(
        delete_file_messages(
            bot,
            chat_id,
            sent_message_ids,
        )
    )


# =========================
# Start Command
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user = update.effective_user

    if context.args:

        share_token = context.args[0]

        if share_token.startswith("file_"):

            share_token = share_token[5:]

        files = get_files(share_token)

        if not files:

            await update.message.reply_text(
                "❌ ഈ share link സാധുവല്ല അല്ലെങ്കിൽ files ലഭ്യമല്ല."
            )

            return

        subscribed = await is_subscribed(
            context.bot,
            user.id,
        )

        if not subscribed:

            await send_subscription_message(
                update.message,
                share_token,
            )

            return

        await send_shared_files(
            context.bot,
            update.effective_chat.id,
            files,
        )

        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📢 Update Channel",
                url="https://t.me/Clmainchannel",
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ Help",
                callback_data="help",
            ),
            InlineKeyboardButton(
                "About",
                callback_data="about",
            ),
        ],
    ]

    await update.message.reply_text(
        "👋 Welcome to Leobot!\n\n"
        "Send a valid share link to receive files.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# Help Command
# =========================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "📖 Help\n\n"
        "Use a valid share link to receive files.\n"
        "Only the admin can upload files.\n\n"
        "Admin command: /stats"
    )


# =========================
# Button Callback
# =========================

async def button_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query:
        return

    data = query.data or ""

    if data.startswith("check_sub:"):

        share_token = data.split(":", 1)[1]

        subscribed = await is_subscribed(
            context.bot,
            query.from_user.id,
        )

        if not subscribed:

            await query.answer(
                "ആദ്യം രണ്ട് ചാനലുകളിലും join ചെയ്യുക.",
                show_alert=True,
            )

            return

        files = get_files(share_token)

        if not files:

            await query.answer(
                "❌ Share link invalid ആണ്.",
                show_alert=True,
            )

            return

        await query.answer()

        try:
            await query.edit_message_text(
                "✅ Subscription verified!\n"
                "📂 Files അയക്കുന്നു..."
            )
        except Exception:
            pass

        await send_shared_files(
            context.bot,
            query.message.chat_id,
            files,
        )

        return

    await query.answer()

    if data == "help":

        await query.edit_message_text(
            "📖 Help\n\n"
            "Share link open ചെയ്ത് files ലഭിക്കാം.\n"
            "ആവശ്യമെങ്കിൽ രണ്ട് channels-ലും join ചെയ്യണം."
        )

    elif data == "about":

        await query.edit_message_text(
            "🤖 Leobot\n\n"
            "A Telegram file-sharing bot."
        )


# =========================
# Admin Document Upload
# =========================

async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user = update.effective_user

    if user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ നിങ്ങൾക്ക് upload permission ഇല്ല."
        )

        return

    document = update.message.document

    if not document:
        return

    user_id = user.id

    if user_id not in pending_files:

        pending_files[user_id] = []

    pending_files[user_id].append(
        {
            "file_id": document.file_id,
            "file_name": document.file_name or "",
            "caption": update.message.caption or "",
        }
    )

    await update.message.reply_text(
        "✅ File saved.\n"
        "കൂടുതൽ files അയക്കാം.\n\n"
        "എല്ലാം കഴിഞ്ഞാൽ /done അയക്കുക."
    )


# =========================
# Done Command
# =========================

async def done_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user = update.effective_user

    if user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Admin മാത്രം ഉപയോഗിക്കാവുന്ന command ആണ്."
        )

        return

    files = pending_files.get(user.id, [])

    if not files:

        await update.message.reply_text(
            "❌ Pending files ഒന്നുമില്ല."
        )

        return

    share_token = save_file_group(
        files,
        user.id,
    )

    pending_files[user.id] = []

    bot_username = context.bot.username

    share_link = (
        f"https://t.me/{bot_username}?start=file_{share_token}"
    )

    await update.message.reply_text(
        "✅ Share link created!\n\n"
        f"{share_link}"
    )


# =========================
# Stats Command
# =========================

async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user = update.effective_user

    if user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Admin only."
        )

        return

    groups_count = file_groups_collection.count_documents({})

    files_count = 0

    for group in file_groups_collection.find({}):

        files_count += len(
            group.get("files", [])
        )

    await update.message.reply_text(
        f"📊 Bot Statistics\n\n"
        f"Share Groups: {groups_count}\n"
        f"Files: {files_count}"
    )


# =========================
# Main
# =========================

def main():

    init_db()

    health_thread = threading.Thread(
        target=run_health_server,
        daemon=True,
    )

    health_thread.start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

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
        CommandHandler("stats", stats_command)
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

    application.run_polling()


if __name__ == "__main__":

    main()

