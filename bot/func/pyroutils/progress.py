# Developed by ARGON telegram: @REACTIVEARGON
import math
import time

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.logger import LOGGER

log = LOGGER(__name__)


# Global state for rate limiting
_progress_state = {}


async def progress_for_pyrogram(
    current, total, ud_type, message, start, last_update_time=None
):
    # Use global state for rate limiting
    unique_id = f"{message.chat.id}_{message.id}"
    last_time = _progress_state.get(unique_id, 0)

    now = time.time()
    diff = now - start

    if now - last_time >= 3 or current == total:
        if total == 0:
            percentage = 0
        else:
            percentage = current * 100 / total

        speed = current / diff if diff > 0 else 0
        elapsed_time = round(diff) * 1000
        time_to_completion = round((total - current) / speed) * 1000 if speed > 0 else 0
        estimated_total_time = elapsed_time + time_to_completion

        elapsed_time_str = TimeFormatter(milliseconds=elapsed_time)
        estimated_total_time_str = TimeFormatter(milliseconds=estimated_total_time)

        # Enhanced progress bar
        filled = math.floor(percentage / 5)  # 20 blocks
        progress_bar = "▰" * filled + "▱" * (20 - filled)

        if percentage == 100:
            status_emoji = "✅"
        elif percentage >= 75:
            status_emoji = "🔥"
        elif percentage >= 50:
            status_emoji = "⏳"
        elif percentage >= 25:
            status_emoji = "🚀"
        else:
            status_emoji = "▶️"

        progress_text = f"""{status_emoji} <b>{ud_type}</b>
<blockquote>
📊 <b>Progress:</b> {percentage:.1f}%
<code>{progress_bar}</code>

📈 <b>Stats:</b>
 ├ <b>Processed:</b> {humanbytes(current)}
 ├ <b>Total:</b> {humanbytes(total)}
 ├ <b>Speed:</b> {humanbytes(speed)}/s
 ├ <b>Elapsed:</b> {elapsed_time_str}
 └ <b>ETA:</b> {estimated_total_time_str if estimated_total_time_str else "calculating..."}
</blockquote>"""

        try:
            await message.edit(
                text=progress_text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="cb_close")]]
                ),
            )
            if current == total:
                if unique_id in _progress_state:
                    del _progress_state[unique_id]
            else:
                _progress_state[unique_id] = now
        except Exception as e:
            if "MESSAGE_ID_INVALID" in str(e):
                # Message was deleted, stop updating
                if unique_id in _progress_state:
                    del _progress_state[unique_id]
            else:
                log.error(f"Error updating progress: {e}")


def humanbytes(size):
    if not size or size == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size)
    i = 0

    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1

    return f"{size:.2f} {units[i]}"


def TimeFormatter(milliseconds: int) -> str:
    if milliseconds <= 0:
        return "0s"

    seconds, ms = divmod(int(milliseconds), 1000)
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    days, hrs = divmod(hours, 24)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hrs > 0:
        parts.append(f"{hrs}h")
    if mins > 0:
        parts.append(f"{mins}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)
