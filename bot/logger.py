# Developed by ARGON telegram: @REACTIVEARGON
import logging
import os
import asyncio
from logging.handlers import RotatingFileHandler
from bot.config import LOG_CHANNEL

LOG_FILE_NAME = "bot.txt"

# Custom formatter with filename & line number
formatter = logging.Formatter(
    fmt="%(asctime)s - %(name)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Basic logging config
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        RotatingFileHandler(LOG_FILE_NAME, maxBytes=50_000_000, backupCount=10),
        logging.StreamHandler(),
    ],
)

class TelegramLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.client = None
        self.queue = asyncio.Queue()
        self.worker_task = None

    def emit(self, record):
        if self.client and record.levelno >= logging.ERROR:
            try:
                msg = self.format(record)
                asyncio.create_task(self.send_log(msg))
            except Exception:
                self.handleError(record)

    async def send_log(self, msg):
        try:
            # Truncate if too long
            if len(msg) > 4000:
                msg = msg[:4000] + "..."

            text = f"❌ <b>Error Log</b>\n\n```python\n{msg}\n```"
            await self.client.send_message(LOG_CHANNEL, text)
        except Exception:
            pass

tg_handler = TelegramLogHandler()
tg_handler.setFormatter(formatter)
logging.getLogger().addHandler(tg_handler)

# Apply formatter to root handlers
for handler in logging.getLogger().handlers:
    handler.setFormatter(formatter)

# Silence Pyrogram debug logs
logging.getLogger("pyrogram").setLevel(logging.ERROR)


def LOGGER(name: str = "App"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    for handler in logger.handlers:
        handler.setFormatter(formatter)

    return logger


# Optional: send log file to user
async def send_logs(client, message):
    log_file = LOG_FILE_NAME
    if os.path.exists(log_file):
        await message.reply_document(log_file, caption="📄 Here are the latest logs.")
    else:
        await message.reply_text("⚠️ No logs found.")
