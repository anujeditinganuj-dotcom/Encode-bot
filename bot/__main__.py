# Developed by ARGON telegram: @REACTIVEARGON
import asyncio

from pyrogram import Client


from bot.config import API_HASH, APP_ID, TG_BOT_TOKEN, TG_BOT_WORKERS
from database import get_variable, set_variable

from .logger import LOGGER, tg_handler

log = LOGGER(__name__)


async def get_session():
    return await get_variable(TG_BOT_TOKEN, None)


class Bot(Client):
    def __init__(self):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        session = loop.run_until_complete(get_session())

        if session:
            # User session
            super().__init__(
                name="user_session",
                session_string=session,
                api_id=APP_ID,
                api_hash=API_HASH,
                plugins={"root": "plugins"},
                workers=TG_BOT_WORKERS,
                max_concurrent_transmissions=8,
            )
        else:
            # Bot session
            super().__init__(
                name="bot_session",
                api_id=APP_ID,
                api_hash=API_HASH,
                bot_token=TG_BOT_TOKEN,
                plugins={"root": "plugins"},
                workers=TG_BOT_WORKERS,
                max_concurrent_transmissions=8,
            )

    async def start(self):
        await super().start()
        tg_handler.client = self

        # Startup Cleanup
        try:
            import shutil
            import os
            if os.path.exists("downloads"):
                shutil.rmtree("downloads")
                os.makedirs("downloads")
                log.info("Cleaned up downloads directory")
        except Exception as e:
            log.error(f"Failed to cleanup downloads: {e}")

        try:
            await self.send_message(
                7024179022,
                text="<b><blockquote>🤖 Bᴏᴛ Rᴇsᴛᴀʀᴛᴇᴅ Sᴜᴄᴄᴇssғᴜʟʟʏ</blockquote></b>",
            )
        except BaseException:
            pass
        log.info(
            r"""
      ___      _____    _____   ____   _   _
     /   \    |  __ \  / ____| / __ \ | \ | |
    /  ^  \   | |__) || |  __ | |  | ||  \| |
   /  /_\  \  |  _  / | | |_ || |  | || . ` |
  /  _____  \ | | \ \ | |__| || |__| || |\  |
 /__/     \__\|_|  \_\ \_____| \____/ |_| \_|
 |__|     |__|

    Developed by ARGON telegram: @REACTIVEARGON
                                                  """
        )
        log.info("Argons Encoder started successfully")

        # Set Bot Commands
        try:
            from pyrogram.types import BotCommand

            await self.set_bot_commands(
                [
                    BotCommand("start", "Start the bot"),
                    BotCommand("settings", "Configure user settings"),
                    BotCommand("queue", "Show current job queue"),
                    BotCommand("stats", "View bot statistics"),
                    BotCommand("ss", "Generate screenshots from video"),
                    BotCommand("cancel", "Cancel a specific job"),
                    BotCommand("clear", "Clear your jobs"),
                    BotCommand("cancelall", "Cancel ALL jobs (Admin Only)"),
                    BotCommand("restart", "Restart the bot (Admin Only)"),
                    BotCommand("shell", "Run shell commands (Admin Only)"),
                    BotCommand("log", "Get logs (Admin Only)"),
                    BotCommand("info", "Get job info (Admin Only)"),
                    BotCommand("broadcast", "Broadcast message (Admin Only)"),
                    BotCommand("admin", "Admin Panel (Owner Only)"),
                    BotCommand("help", "Get help"),
                ]
            )
            log.info("Bot commands set successfully")
        except Exception as e:
            log.error(f"Failed to set bot commands: {e}")

        # Restore Queue
        try:
            from bot.func.queue_manager import queue_manager

            await queue_manager.restore_queue(self)
        except Exception as e:
            log.error(f"Failed to restore queue: {e}")

        session = await self.export_session_string()
        await set_variable(TG_BOT_TOKEN, session)

    async def send_msg(self, chat, text):
        await self.send_message(int(chat), text)


if __name__ == "__main__":
    try:
        import uvloop

        uvloop.install()
    except ImportError:
        pass
    bot = Bot()
    bot.run()
