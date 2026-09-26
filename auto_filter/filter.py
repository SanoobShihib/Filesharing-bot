from telegram import InlineKeyboardButton, InlineKeyboardMarkup


FILES_PER_PAGE = 8


LANGUAGE_NAMES = {
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


QUALITY_NAMES = {
    "360": "360p",
    "480": "480p",
    "720": "720p",
    "1080": "1080p",
    "2160": "4K",
    "other": "Other",
}


def shorten_file_name(name, limit=38):

    if not name:
        return "Shared File"

    if len(name) > limit:
        return name[:limit - 3] + "..."

    return name


def filter_files(
    files,
    language="all",
    quality="all",
):

    filtered = files

    if language != "all":

        language_name = LANGUAGE_NAMES.get(
            language,
            language,
        )

        filtered = [
            file_data
            for file_data in filtered
            if file_data.get("language") == language_name
        ]

    if quality != "all":

        quality_name = QUALITY_NAMES.get(
            quality,
            quality,
        )

        filtered = [
            file_data
            for file_data in filtered
            if file_data.get("quality") == quality_name
        ]

    return filtered


def create_file_keyboard(
    share_token,
    files,
    page=0,
    language="all",
    quality="all",
):

    start = page * FILES_PER_PAGE
    end = start + FILES_PER_PAGE

    page_files = files[start:end]

    buttons = []

    # FILTER BUTTONS
    buttons.append(
        [
            InlineKeyboardButton(
                "🌐 LANGUAGE",
                callback_data=f"langmenu:{share_token}",
            ),
            InlineKeyboardButton(
                "🎚️ QUALITY",
                callback_data=f"qualmenu:{share_token}",
            ),
        ]
    )

    # FILE BUTTONS
    for index, file_data in enumerate(
        page_files,
        start=start,
    ):

        file_name = shorten_file_name(
            file_data.get("file_name")
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    f"📄 {file_name}",
                    callback_data=f"file:{share_token}:{index}",
                )
            ]
        )

    # PAGINATION
    navigation = []

    if page > 0:

        navigation.append(
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data=f"page:{share_token}:{page - 1}",
            )
        )

    if end < len(files):

        navigation.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=f"page:{share_token}:{page + 1}",
            )
        )

    if navigation:
        buttons.append(navigation)

    # SEND ALL
    buttons.append(
        [
            InlineKeyboardButton(
                "📦 Send All Files",
                callback_data=f"all:{share_token}",
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)


def create_file_list_text(
    total_files,
    page=0,
    language="all",
    quality="all",
):

    total_pages = max(
        1,
        (total_files + FILES_PER_PAGE - 1)
        // FILES_PER_PAGE,
    )

    language_text = (
        "All Languages"
        if language == "all"
        else LANGUAGE_NAMES.get(
            language,
            language,
        )
    )

    quality_text = (
        "All Qualities"
        if quality == "all"
        else QUALITY_NAMES.get(
            quality,
            quality,
        )
    )

    return (
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "       📂 *FILE RESULTS*\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"📦 *{total_files} files found*\n"
        f"🌐 *Language:* {language_text}\n"
        f"🎚️ *Quality:* {quality_text}\n"
        f"📄 *Page:* {page + 1}/{total_pages}\n\n"
        "👇 Select a file to download:"
    )


def create_language_keyboard(share_token):

    buttons = [
        [
            InlineKeyboardButton(
                "🇮🇳 MALAYALAM",
                callback_data=f"setlang:{share_token}:ml",
            ),
            InlineKeyboardButton(
                "🇮🇳 TAMIL",
                callback_data=f"setlang:{share_token}:ta",
            ),
        ],
        [
            InlineKeyboardButton(
                "🇬🇧 ENGLISH",
                callback_data=f"setlang:{share_token}:en",
            ),
            InlineKeyboardButton(
                "🇮🇳 HINDI",
                callback_data=f"setlang:{share_token}:hi",
            ),
        ],
        [
            InlineKeyboardButton(
                "🇮🇳 TELUGU",
                callback_data=f"setlang:{share_token}:te",
            ),
            InlineKeyboardButton(
                "🇮🇳 KANNADA",
                callback_data=f"setlang:{share_token}:kn",
            ),
        ],
        [
            InlineKeyboardButton(
                "🇮🇳 PUNJABI",
                callback_data=f"setlang:{share_token}:pa",
            ),
            InlineKeyboardButton(
                "🇮🇳 BENGALI",
                callback_data=f"setlang:{share_token}:bn",
            ),
        ],
        [
            InlineKeyboardButton(
                "🇮🇳 MARATHI",
                callback_data=f"setlang:{share_token}:mr",
            ),
            InlineKeyboardButton(
                "🇮🇳 BHOJPURI",
                callback_data=f"setlang:{share_token}:bho",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔊 DUAL AUDIO",
                callback_data=f"setlang:{share_token}:dual",
            ),
            InlineKeyboardButton(
                "🎵 MULTI AUDIO",
                callback_data=f"setlang:{share_token}:multi",
            ),
        ],
        [
            InlineKeyboardButton(
                "🌐 ALL LANGUAGES",
                callback_data=f"setlang:{share_token}:all",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 BACK TO PAGE",
                callback_data=f"back:{share_token}",
            )
        ],
    ]

    return InlineKeyboardMarkup(buttons)


def create_quality_keyboard(share_token):

    buttons = [
        [
            InlineKeyboardButton(
                "360p",
                callback_data=f"setqual:{share_token}:360",
            ),
            InlineKeyboardButton(
                "480p",
                callback_data=f"setqual:{share_token}:480",
            ),
        ],
        [
            InlineKeyboardButton(
                "720p",
                callback_data=f"setqual:{share_token}:720",
            ),
            InlineKeyboardButton(
                "1080p",
                callback_data=f"setqual:{share_token}:1080",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎞️ 4K",
                callback_data=f"setqual:{share_token}:2160",
            ),
            InlineKeyboardButton(
                "🌐 Other",
                callback_data=f"setqual:{share_token}:other",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎚️ ALL QUALITIES",
                callback_data=f"setqual:{share_token}:all",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 BACK TO PAGE",
                callback_data=f"back:{share_token}",
            )
        ],
    ]

    return InlineKeyboardMarkup(buttons)


def create_empty_file_text():

    return (
        "❌ *Files not found*\n\n"
        "The share link may be invalid or expired."
    )
