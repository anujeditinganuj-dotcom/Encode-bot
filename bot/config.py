# Developed by ARGON telegram: @REACTIVEARGON
import os

from dotenv import load_dotenv

load_dotenv()


# Bot token @Botfather
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
# Your API ID from my.telegram.org
APP_ID = int(os.environ.get("APP_ID", "12345678"))  # Placeholder ID
# Your API Hash from my.telegram.org
API_HASH = os.environ.get("API_HASH", "your_api_hash_here")
# Your db channel Id
LOG_CHANNEL = int(os.environ.get("CHANNEL_ID", "-1001234567890"))  # Placeholder channel ID
# NAMA OWNER
OWNER = os.environ.get("OWNER", "YOUR_OWNER_USERNAME_OR_ID")
# OWNER ID
OWNER_ID = int(os.environ.get("OWNER_ID", "1234567890"))  # Placeholder owner ID
# Port
PORT = os.environ.get("PORT", "8030")
# Database
DB_URI = os.environ.get(
    "DATABASE_URL",
    "mongodb+srv://user:password@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0",  # Placeholder DB URI
)
DB_NAME = os.environ.get("DATABASE_NAME", "Cluster")

TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "50"))
