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

from auto_filter.filter import (
    create_file_keyboard,
    create_file_list_text,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


PORT = int(os.getenv("PORT", "8000"))

pending_files = {}


# =========================================================
# FORCE SUBSCRIBE
# =========================================================

# നിങ്ങളുടെ private channel invite link ഇവിടെ ഇടുക
FORCE_SUBSCRIBE_LINK = "https://t.me/+TBEZZOyLdPdjODg1"


async def is_subscribed(bot, user_id):
    """
    Check whether the user has joined the required channel.
    Only the first channel in CHANNELS is checked.
    """

    if not CHANNELS:
        return True

    try:
        channel_id = CHANNELS[0]

        member = await bot.get_chat_member(
            chat_id=channel_id,
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
            return getattr(member, "is_member", False)

        return True

    except Exception:
        logger.exception(
            "Force Subscribe check failed"
        )
        return False


def subscription_keyboard(share_token):
    """
    Keyboard shown when user has not joined the channel.
    """

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📢 Join Channel",
                    url=FORCE_SUBSCRIBE_LINK,
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Try Again",
                    callback_data=f"check_subscription:{share_token}",
                )
            ],
        ]
    )


async def send_subscription_message(
    message,
    share_token,
):
    """
    Send Force Subscribe message.
    """

    await message.reply_text(
        "🔒 ഈ ചാനലിൽ Join ചെയ്താലേ നിങ്ങൾക്ക് ഫയൽ ലഭിക്കൂ.\n\n"
        "📢 ആദ്യം Channel-ൽ Join ചെയ്യുക.\n"
        "✅ Join ചെയ്ത ശേഷം Try Again അമർത്തുക.",
        reply_markup=subscription_keyboard(share_token),
    )


# =========================================================
# MONGODB CONNECTION
# =========================================================

mongo_client = MongoClient(DATABASE_URI)

mongo_db = mongo_client["leobot"]

file_groups_collection = mongo_db["file_groups"]

shared_files_collection = mongo_db["shared_files"]


# =========================================================
# HEALTH SERVER
# =========================================================

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


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    file_groups_collection.create_index(
        "share_token",
        unique=True,
    )

    shared_files_collection.create_index(
        "share_token",
    )


# =========================================================
# SAVE FILE GROUP
# =========================================================

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
                "language": file_data.get(
                    "language",
                    "Unknown",
                ),
                "quality": file_data.get(
                    "quality",
                    "Unknown",
                ),
            }
            for file_data in files
        ]
    )

    return share_token


# =========================================================
# GET FILES
# =========================================================

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
                "language": 1,
                "quality": 1,
            },
        )
    )


# =========================================================
# SEND FILES
# =========================================================

async def send_shared_files(
    update,
    context,
    share_token,
):

    if not update.message:
        return

    files = get_files(share_token)

    if not files:
        await update.message.reply_text(
            "❌ Files not found or link is invalid."
        )
        return

    text = create_file_list_text(
        total_files=len(files),
        page=0,
    )

    keyboard = create_file_keyboard(
        share_token=share_token,
        files=files,
        page=0,
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def send_one_file(
    bot,
    chat_id,
    file_data,
):

    try:

        sent_message = await bot.send_document(
            chat_id=chat_id,
            document=file_data["file_id"],
            caption=(
                f"📁 "
                f"{file_data.get('file_name') or 'Shared File'}"
            ),
        )

        asyncio.create_task(
            delete_file_messages(
                bot=bot,
                chat_id=chat_id,
                message_ids=[
                    sent_message.message_id
                ],
            )
        )

        return True

    except Exception:

        logger.exception(
            "Failed to send one file"
        )

        return False


async def send_all_files(
    bot,
    chat_id,
    files,
):

    sent_message_ids = []

    for file_data in files:

        try:

            sent_message = await bot.send_document(
                chat_id=chat_id,
                document=file_data["file_id"],
                caption=(
                    f"📁 "
                    f"{file_data.get('file_name') or 'Shared File'}"
                ),
            )

            sent_message_ids.append(
                sent_message.message_id
            )

        except Exception:

            logger.exception(
                "Failed to send shared file"
            )

    if sent_message_ids:

        asyncio.create_task(
            delete_file_messages(
                bot=bot,
                chat_id=chat_id,
                message_ids=sent_message_ids,
            )
        )


# =========================================================
# AUTO DELETE FILE MESSAGES
# =========================================================

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


# =========================================================
# START COMMAND
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    # -----------------------------------------------------
    # SHARE FILE LINK
    # -----------------------------------------------------

    if context.args:

        share_token = context.args[0]

        if share_token.startswith("file_"):
            share_token = share_token[5:]

        # -------------------------------------------------
        # FORCE SUBSCRIBE ONLY FOR FILE LINKS
        # -------------------------------------------------

        user = update.effective_user

        if not await is_subscribed(
            context.bot,
            user.id,
        ):

            await send_subscription_message(
                update.message,
                share_token,
            )

            return

        # -------------------------------------------------
        # USER SUBSCRIBED - SEND FILES
        # -------------------------------------------------

        await send_shared_files(
            update,
            context,
            share_token,
        )

        return

    # -----------------------------------------------------
    # NORMAL START
    # -----------------------------------------------------

    user = update.effective_user

    keyboard = [
    [
        InlineKeyboardButton(
            "👥 Join Our Group",
            url="https://t.me/+Ik14BdOewjQzYjI1",
        )
    ],
    [
        InlineKeyboardButton(
            "📢 Join Update Channel",
            url="https://t.me/Clmainchannel",
        )
    ],
    [
        InlineKeyboardButton(
            "ℹ️ About",
            callback_data="about",
        )
    ],
]

    await update.message.reply_text(
    "👋 Welcome to CL File Bot!\n\n"
    "⚡ Fast & Secure\n"
    "📥 Easy File Sharing\n\n"
    "👇 താഴെയുള്ള buttons ഉപയോഗിക്കുക.",
    reply_markup=InlineKeyboardMarkup(keyboard),
)


# =========================================================
# HELP COMMAND
# =========================================================

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


# =========================================================
# BUTTON CALLBACK
# =========================================================

async def button_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

# =====================================================
# FILE FILTER MENUS
# =====================================================

    from auto_filter.filter import (
        filter_files,
        create_language_keyboard,
        create_quality_keyboard,
    )

    if query.data.startswith("langmenu:"):

        share_token = query.data.split(":", 1)[1]

        await query.edit_message_text(
            "🌐 *SELECT LANGUAGE:*",
            parse_mode="Markdown",
            reply_markup=create_language_keyboard(
                share_token
            ),
        )

        return

    if query.data.startswith("qualmenu:"):

        share_token = query.data.split(":", 1)[1]

        await query.edit_message_text(
            "🎚️ *SELECT QUALITY:*",
            parse_mode="Markdown",
            reply_markup=create_quality_keyboard(
                share_token
            ),
        )

        return

    # =====================================================
    # FILE FILTER SELECTION
    # =====================================================

    if (
        query.data.startswith("setlang:")
        or query.data.startswith("setqual:")
        or query.data.startswith("back:")
    ):

        from auto_filter.filter import (
            filter_files,
            create_file_keyboard,
            create_file_list_text,
        )

        parts = query.data.split(":")

        share_token = parts[1]

        filters = context.user_data.setdefault(
            "file_filters",
            {}
        )

        state = filters.setdefault(
            share_token,
            {
                "language": "all",
                "quality": "all",
                "page": 0,
            },
        )

        if query.data.startswith("setlang:"):

            language_code = parts[2]

            state["language"] = language_code
            state["page"] = 0

        elif query.data.startswith("setqual:"):

            quality_code = parts[2]

            state["quality"] = quality_code
            state["page"] = 0

        elif query.data.startswith("back:"):

            pass

        all_files = get_files(
            share_token
        )

        filtered = filter_files(
            all_files,
            language=state["language"],
            quality=state["quality"],
        )

        page = state["page"]

        text = create_file_list_text(
            total_files=len(filtered),
            page=page,
            language=state["language"],
            quality=state["quality"],
        )

        keyboard = create_file_keyboard(
            share_token,
            filtered,
            page=page,
            language=state["language"],
            quality=state["quality"],
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

        return


# =====================================================
# ADMIN UPLOAD - LANGUAGE SELECTION
# =====================================================

if query.data.startswith("upload_lang:"):

    parts = query.data.split(":")

    if len(parts) != 3:
        return

    file_index = int(parts[1])
    language_code = parts[2]

    user_id = query.from_user.id

    if user_id != ADMIN_ID:
        await query.answer(
            "❌ Only admin can use this.",
            show_alert=True,
        )
        return

    user_files = pending_files.get(
        user_id,
        [],
    )

    if file_index < 0 or file_index >= len(user_files):
        await query.answer(
            "❌ Invalid file.",
            show_alert=True,
        )
        return

    language_names = {
        "ml": "Malayalam",
        "ta": "Tamil",
        "en": "English",
        "hi": "Hindi",
        "te": "Telugu",
        "kn": "Kannada",
        "pa": "Punjabi",
        "bn": "Bengali",
        "mr": "Marathi",
        "bho": "Bhojpuri",
        "dual": "Dual Audio",
        "multi": "Multi Audio",
    }

    language_name = language_names.get(
        language_code,
        "Unknown",
    )

    pending_files[user_id][file_index]["language"] = language_name

    quality_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "360p",
                    callback_data=f"upload_quality:{file_index}:360",
                ),
                InlineKeyboardButton(
                    "480p",
                    callback_data=f"upload_quality:{file_index}:480",
                ),
            ],
            [
                InlineKeyboardButton(
                    "720p",
                    callback_data=f"upload_quality:{file_index}:720",
                ),
                InlineKeyboardButton(
                    "1080p",
                    callback_data=f"upload_quality:{file_index}:1080",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎞️ 4K",
                    callback_data=f"upload_quality:{file_index}:2160",
                ),
                InlineKeyboardButton(
                    "🌐 Other",
                    callback_data=f"upload_quality:{file_index}:other",
                ),
            ],
        ]
    )

    await query.edit_message_text(
        f"📁 *File {file_index + 1}*\n\n"
        f"🌐 Language: *{language_name}*\n\n"
        "🎚️ *SELECT QUALITY:*",
        parse_mode="Markdown",
        reply_markup=quality_keyboard,
    )

    return
    
    # =====================================================
    # ADMIN UPLOAD - QUALITY SELECTION
    # =====================================================

    if query.data.startswith("upload_quality:"):

        parts = query.data.split(":")

        if len(parts) != 3:
            return

        file_index = int(parts[1])
        quality_code = parts[2]

        user_id = query.from_user.id

        if user_id != ADMIN_ID:
            await query.answer(
                "❌ Only admin can use this.",
                show_alert=True,
            )
            return

        user_files = pending_files.get(
            user_id,
            [],
        )

        if file_index < 0 or file_index >= len(user_files):
            await query.answer(
                "❌ Invalid file.",
                show_alert=True,
            )
            return

        quality_names = {
            "360": "360p",
            "480": "480p",
            "720": "720p",
            "1080": "1080p",
            "2160": "4K",
            "other": "Other",
        }

        quality_name = quality_names.get(
            quality_code,
            "Other",
        )

        pending_files[user_id][file_index][
            "quality"
        ] = quality_name

        file_name = pending_files[user_id][
            file_index
        ].get("file_name", "Unknown File")

        language_name = pending_files[user_id][
            file_index
        ].get("language", "Unknown")

        await query.edit_message_text(
            f"✅ *File {file_index + 1} ready!*\n\n"
            f"📄 `{file_name}`\n\n"
            f"🌐 Language: *{language_name}*\n"
            f"🎚️ Quality: *{quality_name}*\n\n"
            "📤 Send the next file, or use /done.",
            parse_mode="Markdown",
        )

        return

    # =====================================================
    # HELP
    # =====================================================

    if query.data == "help":

        await query.edit_message_text(
            "📖 Help\n\n"
            "📤 Send your files one by one.\n"
            "✅ After sending all files, use /done.\n"
            "🔗 You will receive one share link."
        )

    # =====================================================
    # ABOUT
    # =====================================================

    elif query.data == "about":

        about_text = (
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "      ✦ *CL FILE BOT* ✦\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"
            "➜ 👤 *Owner:* [Heisenberg 😈]"
            "(https://t.me/heisenbergalready)\n"
            "➜ 🛠️ *Maintained By:* `CL Team`\n"
            "➜ 🐍 *Language:* `Python 3`\n"
            "➜ 📚 *Library:* `python-telegram-bot`\n"
            "➜ 🗄️ *Database:* `MongoDB`\n"
            "➜ ☁️ *Server:* `Koyeb`\n"
            "➜ 🔖 *Version:* `v1.1.0`\n"
            "➜ 🟢 *Status:* `Online`\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "➜ 📂 *Multiple File Sharing*\n"
            "➜ 🔗 *One Link For Multiple Files*\n"
            "➜ 🔍 *File List / Auto Filter*\n"
            "➜ 📦 *Send All Files*\n"
            "➜ 🔒 *Force Subscribe*\n"
            "➜ ⏱️ *Auto File Delete*\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "⚡ *Fast • Simple • Secure*\n\n"
            "        © *CL File Bot*"
        )

        await query.edit_message_text(
            about_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "❌ Close",
                            callback_data="close",
                        )
                    ]
                ]
            ),
        )

    # =====================================================
    # CLOSE
    # =====================================================

    elif query.data == "close":

        await query.message.delete()

    # =====================================================
    # FORCE SUBSCRIBE CHECK
    # =====================================================

    elif query.data.startswith(
        "check_subscription:"
    ):

        share_token = query.data.split(
            ":",
            1,
        )[1]

        user = query.from_user

        subscribed = await is_subscribed(
            context.bot,
            user.id,
        )

        if not subscribed:

            await query.answer(
                "❌ ആദ്യം Channel Join ചെയ്യുക.",
                show_alert=True,
            )

            return

        await query.answer(
            "✅ Subscription verified!"
        )

        files = get_files(
            share_token
        )

        if not files:

            await query.edit_message_text(
                "❌ Files not found or link is invalid."
            )

            return

        text = create_file_list_text(
            total_files=len(files),
            page=0,
        )

        keyboard = create_file_keyboard(
            share_token=share_token,
            files=files,
            page=0,
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    # =====================================================
    # NEXT / PREVIOUS PAGE
    # =====================================================

    elif query.data.startswith(
        "page:"
    ):

        parts = query.data.split(
            ":"
        )

        if len(parts) != 3:
            return

        share_token = parts[1]
        page = int(parts[2])

        files = get_files(
            share_token
        )

        if not files:

            await query.edit_message_text(
                "❌ Files not found."
            )

            return

        text = create_file_list_text(
            total_files=len(files),
            page=page,
        )

        keyboard = create_file_keyboard(
            share_token=share_token,
            files=files,
            page=page,
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    # =====================================================
    # SINGLE FILE
    # =====================================================

    elif query.data.startswith(
        "file:"
    ):

        parts = query.data.split(
            ":"
        )

        if len(parts) != 3:
            return

        share_token = parts[1]
        file_index = int(parts[2])

        files = get_files(
            share_token
        )

        if not files:

            await query.answer(
                "❌ Files not found.",
                show_alert=True,
            )

            return

        if file_index < 0 or file_index >= len(files):

            await query.answer(
                "❌ Invalid file.",
                show_alert=True,
            )

            return

        file_data = files[file_index]

        await query.answer(
            "📥 Sending file..."
        )

        success = await send_one_file(
            bot=context.bot,
            chat_id=query.message.chat_id,
            file_data=file_data,
        )

        if success:

            await query.message.reply_text(
                "✅ File sent successfully!\n"
                "⏳ It will be auto deleted later."
            )

        else:

            await query.message.reply_text(
                "❌ Failed to send file."
            )

    # =====================================================
    # SEND ALL FILES
    # =====================================================

    elif query.data.startswith(
        "all:"
    ):

        share_token = query.data.split(
            ":",
            1,
        )[1]

        files = get_files(
            share_token
        )

        if not files:

            await query.answer(
                "❌ Files not found.",
                show_alert=True,
            )

            return

        await query.answer(
            "📥 Sending all files..."
        )

        await query.message.reply_text(
            f"📦 Sending {len(files)} files...\n"
            "⏳ Please wait."
        )

        await send_all_files(
            bot=context.bot,
            chat_id=query.message.chat_id,
            files=files,
    )
        
# =========================================================
# HANDLE DOCUMENTS
# =========================================================

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
            "language": None,
            "quality": None,
        }
    )

    file_index = len(
        pending_files[user.id]
    ) - 1

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🇮🇳 MALAYALAM",
                    callback_data=f"upload_lang:{file_index}:ml",
                ),
                InlineKeyboardButton(
                    "🇮🇳 TAMIL",
                    callback_data=f"upload_lang:{file_index}:ta",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🇬🇧 ENGLISH",
                    callback_data=f"upload_lang:{file_index}:en",
                ),
                InlineKeyboardButton(
                    "🇮🇳 HINDI",
                    callback_data=f"upload_lang:{file_index}:hi",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🇮🇳 TELUGU",
                    callback_data=f"upload_lang:{file_index}:te",
                ),
                InlineKeyboardButton(
                    "🇮🇳 KANNADA",
                    callback_data=f"upload_lang:{file_index}:kn",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🇮🇳 PUNJABI",
                    callback_data=f"upload_lang:{file_index}:pa",
                ),
                InlineKeyboardButton(
                    "🇮🇳 BENGALI",
                    callback_data=f"upload_lang:{file_index}:bn",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🇮🇳 MARATHI",
                    callback_data=f"upload_lang:{file_index}:mr",
                ),
                InlineKeyboardButton(
                    "🇮🇳 BHOJPURI",
                    callback_data=f"upload_lang:{file_index}:bho",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔊 DUAL AUDIO",
                    callback_data=f"upload_lang:{file_index}:dual",
                ),
                InlineKeyboardButton(
                    "🎵 MULTI AUDIO",
                    callback_data=f"upload_lang:{file_index}:multi",
                ),
            ],
        ]
    )

    await update.message.reply_text(
        f"📁 *File {file_index + 1}*\n\n"
        f"`{document.file_name}`\n\n"
        "🌐 *SELECT YOUR LANGUAGE:*",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# =========================================================
# DONE COMMAND
# =========================================================

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


# =========================================================
# STATS COMMAND
# =========================================================

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


# =========================================================
# MAIN FUNCTION
# =========================================================

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


# =========================================================
# RUN BOT
# =========================================================

if __name__ == "__main__":
    main()
