from telegram import InlineKeyboardButton, InlineKeyboardMarkup


FILES_PER_PAGE = 8


def shorten_file_name(name, limit=38):
    if not name:
        return "Shared File"

    if len(name) > limit:
        return name[:limit - 3] + "..."

    return name


def create_file_keyboard(
    share_token,
    files,
    page=0,
):
    """
    Create file list with Previous / Next buttons.
    """

    start = page * FILES_PER_PAGE
    end = start + FILES_PER_PAGE

    page_files = files[start:end]

    buttons = []

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
                    callback_data=(
                        f"file:{share_token}:{index}"
                    ),
                )
            ]
        )

    navigation = []

    # Previous
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data=(
                    f"page:{share_token}:{page - 1}"
                ),
            )
        )

    # Next
    if end < len(files):
        navigation.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=(
                    f"page:{share_token}:{page + 1}"
                ),
            )
        )

    if navigation:
        buttons.append(navigation)

    # Send All
    buttons.append(
        [
            InlineKeyboardButton(
                "📦 Send All Files",
                callback_data=(
                    f"all:{share_token}"
                ),
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)


def create_file_list_text(
    total_files,
    page=0,
):
    """
    Text shown above the file buttons.
    """

    total_pages = (
        (total_files + FILES_PER_PAGE - 1)
        // FILES_PER_PAGE
    )

    return (
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "       📂 *FILE RESULTS*\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"📦 *{total_files} files found*\n"
        f"📄 *Page:* {page + 1}/{total_pages}\n\n"
        "👇 Select a file to download:"
    )


def create_empty_file_text():
    return (
        "❌ *Files not found*\n\n"
        "The share link may be invalid or expired."
    )
