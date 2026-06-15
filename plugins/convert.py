# Developed by ARGON telegram: @REACTIVEARGON
import asyncio
import os
import shlex
import time
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot.func.download_manager import download_manager
from bot.func.pyroutils.progress import progress_for_pyrogram, humanbytes
from bot.func.upload_manager import upload_manager
from bot.logger import LOGGER

log = LOGGER(__name__)

# Quality options for conversion (re-encode)
QUALITY_OPTIONS = [
    ("4K (2160p)", "2160p", "3840:2160"),
    ("2K (1440p)", "1440p", "2560:1440"),
    ("FHD (1080p)", "1080p", "1920:1080"),
    ("HD (720p)",   "720p",  "1280:720"),
    ("SD (480p)",   "480p",  "854:480"),
    ("360p",        "360p",  "640:360"),
    ("240p",        "240p",  "426:240"),
    ("144p",        "144p",  "256:144"),
]

# In-memory store: {user_id: {msg_id, file_name, chat_id}}
_convert_sessions: dict = {}


def _quality_keyboard(user_id: int, msg_id: int) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(QUALITY_OPTIONS), 2):
        row = []
        for label, key, _ in QUALITY_OPTIONS[i:i+2]:
            row.append(InlineKeyboardButton(
                label,
                callback_data=f"cvt_q:{user_id}:{msg_id}:{key}"
            ))
        rows.append(row)
    rows.append([
        InlineKeyboardButton(
            "⚡ Fast Remux (No Re-encode)",
            callback_data=f"cvt_q:{user_id}:{msg_id}:remux"
        )
    ])
    rows.append([
        InlineKeyboardButton("❌ Cancel", callback_data=f"cvt_cancel:{user_id}")
    ])
    return InlineKeyboardMarkup(rows)


async def show_quality_selection(client: Client, message: Message):
    """
    Called from encode.py handler when a video file is received.
    Shows quality selection buttons to the user.
    """
    doc = message.video if message.video else message.document
    file_name = getattr(doc, "file_name", None) or f"video_{int(time.time())}.mp4"
    user_id = message.from_user.id
    msg_id = message.id

    _convert_sessions[user_id] = {
        "msg_id": msg_id,
        "file_name": file_name,
        "chat_id": message.chat.id,
    }

    await message.reply_text(
        f"🎬 <b>Select Output Quality</b>\n\n"
        f"📁 <b>File:</b> <code>{file_name}</code>\n\n"
        f"📐 <i>Resolution options</i> = re-encode to selected quality\n"
        f"⚡ <i>Fast Remux</i> = no re-encoding (fastest, original quality)",
        reply_markup=_quality_keyboard(user_id, msg_id),
    )


@Client.on_callback_query(filters.regex(r"^cvt_cancel:"))
async def convert_cancel_cb(client: Client, callback_query: CallbackQuery):
    uid_str = callback_query.data.split(":")[1]
    if str(callback_query.from_user.id) != uid_str:
        await callback_query.answer("❌ Not your session!", show_alert=True)
        return
    _convert_sessions.pop(callback_query.from_user.id, None)
    await callback_query.message.edit_text("❌ <b>Conversion cancelled.</b>")


@Client.on_callback_query(filters.regex(r"^cvt_q:"))
async def convert_quality_cb(client: Client, callback_query: CallbackQuery):
    parts = callback_query.data.split(":")
    # cvt_q:{user_id}:{msg_id}:{quality_key}
    if len(parts) < 4:
        await callback_query.answer("Invalid data", show_alert=True)
        return

    _, uid_str, msg_id_str, quality_key = parts[0], parts[1], parts[2], parts[3]
    requester_id = callback_query.from_user.id

    if str(requester_id) != uid_str:
        await callback_query.answer("❌ Not your session!", show_alert=True)
        return

    session = _convert_sessions.pop(requester_id, None)
    if not session:
        await callback_query.answer("Session expired. Send file again.", show_alert=True)
        await callback_query.message.edit_text("⚠️ <b>Session expired.</b> Please send the file again.")
        return

    file_name = session["file_name"]
    chat_id = session["chat_id"]
    orig_msg_id = int(msg_id_str)

    # Resolve quality
    quality_label = "Fast Remux"
    scale_filter = None
    if quality_key != "remux":
        for label, key, scale in QUALITY_OPTIONS:
            if key == quality_key:
                quality_label = label
                scale_filter = scale
                break

    status_msg = await callback_query.message.edit_text(
        f"📥 <b>Downloading...</b>\n\n"
        f"🎯 <b>Target Quality:</b> {quality_label}"
    )

    # Download original message
    downloads_dir = Path("downloads")
    downloads_dir.mkdir(exist_ok=True)

    safe_name = "".join(
        c for c in file_name if c.isalnum() or c in (" ", "-", "_", ".")
    ).strip() or f"video_{int(time.time())}.mp4"

    download_path = str(downloads_dir / safe_name)

    try:
        orig_msg = await client.get_messages(chat_id, orig_msg_id)
    except Exception as e:
        await status_msg.edit(f"❌ <b>Failed to get file:</b> <code>{e}</code>")
        return

    try:
        await download_manager.acquire()
        downloaded = await client.download_media(
            orig_msg,
            file_name=download_path,
            progress=progress_for_pyrogram,
            progress_args=("📥 Downloading...", status_msg, time.time()),
        )
    except Exception as e:
        await status_msg.edit(f"❌ <b>Download Failed:</b> <code>{e}</code>")
        return
    finally:
        download_manager.release()

    if not downloaded or not os.path.exists(downloaded):
        await status_msg.edit("❌ <b>Download Failed: File not found.</b>")
        return

    stem = Path(downloaded).stem
    output_path = str(downloads_dir / f"{stem}_converted.mp4")

    # Build FFmpeg command
    if scale_filter:
        await status_msg.edit(
            f"⚙️ <b>Converting → MP4 ({quality_label})...</b>\n\n"
            f"📐 Re-encoding to {quality_key}, please wait..."
        )
        cmd = [
            "ffmpeg",
            "-i", downloaded,
            "-map", "0:v?",
            "-map", "0:a?",
            "-vf", f"scale={scale_filter}:force_original_aspect_ratio=decrease,"
                   f"pad={scale_filter}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "medium",
            "-c:a", "aac",
            "-b:a", "128k",
            "-y",
            output_path,
        ]
    else:
        await status_msg.edit("⚙️ <b>Converting → MP4...</b>\n\n⚡ Fast remux (no re-encoding)")
        cmd = [
            "ffmpeg",
            "-i", downloaded,
            "-map", "0:v?",
            "-map", "0:a?",
            "-c:v", "copy",
            "-c:a", "copy",
            "-y",
            output_path,
        ]

    log.info(f"Convert cmd: {shlex.join(cmd)}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode()[:1000]
            log.error(f"FFmpeg convert failed: {err}")
            await status_msg.edit(f"❌ <b>Conversion Failed</b>\n\n<code>{err}</code>")
            _cleanup(downloaded, output_path)
            return

    except Exception as e:
        await status_msg.edit(f"❌ <b>Conversion Error:</b> <code>{e}</code>")
        _cleanup(downloaded, output_path)
        return

    # Upload
    file_size = os.path.getsize(output_path)
    orig_size = os.path.getsize(downloaded)
    output_name = Path(output_path).name
    bot_username = (await client.get_me()).username
    method_str = f"Re-encoded ({quality_label})" if scale_filter else "Fast Remux (No Re-encoding)"

    # Extract thumbnail from original video (user custom thumbnail takes priority)
    from database import get_user_settings
    from bot.func.ffmpeg_utils import prepare_thumbnail
    user_settings = await get_user_settings(requester_id) or {}
    thumb_path = prepare_thumbnail(requester_id, user_settings, input_file=downloaded)

    caption = (
        f"✅ <b>Video → MP4 Done!</b>\n\n"
        f"<blockquote>📁 <b>File:</b> <code>{output_name}</code>\n"
        f"📥 <b>Original:</b> {humanbytes(orig_size)}\n"
        f"📤 <b>Output:</b> {humanbytes(file_size)}\n"
        f"🎯 <b>Quality:</b> {quality_label}\n"
        f"⚡ <b>Method:</b> {method_str}</blockquote>\n\n"
        f"🤖 <b>By:</b> @{bot_username}"
    )

    async def upload_worker():
        upload_msg = await client.send_message(chat_id, "📤 <b>Uploading...</b>")
        try:
            await client.send_document(
                chat_id=chat_id,
                document=output_path,
                caption=caption,
                thumb=thumb_path,
                progress=progress_for_pyrogram,
                progress_args=("📤 Uploading...", upload_msg, time.time()),
            )
            await upload_msg.delete()
        except Exception as e:
            await upload_msg.edit(f"❌ <b>Upload Failed:</b> <code>{e}</code>")
        finally:
            _cleanup(downloaded, output_path, thumb_path)

    await status_msg.delete()
    await upload_manager.add_upload_job(requester_id, upload_worker)


def _cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception as e:
            log.error(f"Cleanup error: {e}")
