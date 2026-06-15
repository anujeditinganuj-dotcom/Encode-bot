# Developed by ARGON telegram: @REACTIVEARGON
import time

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from bot.func.editquery import handle_encoding_callback

# Store last interaction time for each user
user_last_interaction = {}


@Client.on_callback_query(filters.regex(r"^enc_"))
async def encoding_callback_handler(client: Client, callback_query: CallbackQuery):
    """Handler for encoding callbacks with rate limiting"""
    user_id = callback_query.from_user.id
    current_time = time.time()

    if user_id in user_last_interaction:
        if current_time - user_last_interaction[user_id] < 2.0:
            await callback_query.answer(
                "⚠️ Please wait 2 seconds between actions.", show_alert=True
            )
            return

    user_last_interaction[user_id] = current_time
    await handle_encoding_callback(client, callback_query)
