import os

# Telegram Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Telegram API Configuration
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")

# Required Channels
CHANNELS = os.getenv("CHANNELS", "").split()

# Database Configuration
DATABASE_URI = os.getenv("DATABASE_URI")

# Logging Channel
LOG_CHANNEL = os.getenv("LOG_CHANNEL")

# Admin Configuration
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
