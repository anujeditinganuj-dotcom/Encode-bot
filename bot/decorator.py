# Developed by ARGON telegram: @REACTIVEARGON
from pyrogram import Client

from .config import LOG_CHANNEL
from .logger import LOGGER


def task(func):
    logger = LOGGER(func.__name__)

    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in '{func.__name__}': {e}", exc_info=True)

            # Extract the bot client instance
            client = args[0] if args else None
            if isinstance(client, Client):
                try:
                    await client.send_message(
                        chat_id=LOG_CHANNEL, text=f"Error in '{func.__name__}': {e}"
                    )
                except Exception as ex:
                    logger.error(f"Failed to send error log to LOG_CHANNEL: {ex}")

    return wrapper
