# Developed by ARGON telegram: @REACTIVEARGON
import os

from dotenv import load_dotenv

load_dotenv()


# Bot token @Botfather
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
# Your API ID from my.telegram.org
APP_ID = int(os.environ.get("APP_ID", "37476811"))  # Placeholder ID
# Your API Hash from my.telegram.org
API_HASH = os.environ.get("API_HASH", "7aa60670b871050820086c6267371ee6")
# Your db channel Id
LOG_CHANNEL = int(os.environ.get("CHANNEL_ID", "-1003824246703"))  # Placeholder channel ID
# NAMA OWNER
OWNER = os.environ.get("OWNER", "8730393744")
# OWNER ID
OWNER_ID = int(os.environ.get("OWNER_ID", "8730393744"))  # Placeholder owner ID
# Port
PORT = os.environ.get("PORT", "5000")
# Database
DB_URI = os.environ.get(
    "DATABASE_URL",
    "mongodb+srv://Anujedit:Anujedit@cluster0.7cs2nhd.mongodb.net/?appName=Cluster0",  # Placeholder DB URI
)
DB_NAME = os.environ.get("DATABASE_NAME", "Anujedit")

TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "50"))
