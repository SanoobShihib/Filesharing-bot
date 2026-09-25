import os

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Database Configuration
DB_PATH = os.getenv("DB_PATH", "files.db")

# Server Configuration
PORT = int(os.getenv("PORT", "8000"))

# Channel Configuration
UPDATE_CHANNEL = os.getenv(
    "UPDATE_CHANNEL",
    "https://t.me/Clmainchannel"
)
