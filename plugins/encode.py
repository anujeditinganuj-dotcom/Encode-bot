# Developed by ARGON telegram: @REACTIVEARGON
import os
import time

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.logger import LOGGER

log = LOGGER(__name__)


async def check_and_process_video_document(message: Message) -> dict:
    """
    Enhanced function that returns detailed information about the video document
    """
    result = {
        "is_video_document": False,
        "is_encodable": False,
        "file_info": {},
        "encoding_ready": False,
    }

    # Check if message has video or document
    if not message.document and not message.video:
        log.info("Message has no document or video attachment")
        return result

    # Get the media object (prioritize video over document)
    doc = message.video if message.video else message.document
    result["is_video_document"] = True

    log.info(f"Processing media: type={'video' if message.video else 'document'}")

    # Collect file information
    result["file_info"] = {
        "file_name": getattr(doc, "file_name", None) or f"video_{int(time.time())}.mp4",
        "file_size": getattr(doc, "file_size", 0),
        "mime_type": getattr(doc, "mime_type", ""),
        "file_id": getattr(doc, "file_id", ""),
        "duration": getattr(doc, "duration", 0),
        "width": getattr(doc, "width", 0),
        "height": getattr(doc, "height", 0),
    }

    log.info(f"File info: {result['file_info']}")

    # Check if it's encodable
    encodable_formats = {
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".3gp",
        ".ogv",
        ".ts",
        ".mts",
        ".m2ts",
        ".vob",
        ".asf",
        ".rm",
        ".rmvb",
    }

    # Check by extension
    file_name = result["file_info"]["file_name"]
    if file_name:
        ext = os.path.splitext(file_name)[1].lower()
        if ext in encodable_formats:
            result["is_encodable"] = True
            log.info(f"File is encodable by extension: {ext}")

    # Check by MIME type
    mime_type = result["file_info"]["mime_type"]
    if mime_type and mime_type.startswith("video/"):
        result["is_encodable"] = True
        log.info(f"File is encodable by MIME type: {mime_type}")

    # Additional checks for encoding readiness
    if result["is_encodable"]:
        # Check file size (reasonable limits for encoding)
        max_size = 2 * 1024 * 1024 * 1024  # 2GB limit
        file_size = result["file_info"]["file_size"]
        if 0 < file_size <= max_size:
            result["encoding_ready"] = True
            log.info(
                f"File is ready for encoding (size: {file_size / (1024*1024):.2f} MB)"
            )

    return result


@Client.on_message(
    (filters.private) & (filters.document | filters.video)
)
async def enhanced_document_handler(client: Client, message: Message):
    """
    Auto-detect video files and show quality selection for MP4 conversion.
    """
    from plugins.convert import show_quality_selection

    user_id = message.from_user.id
    log.info(f"Processing document/video from user {user_id}")

    # Log to Channel
    try:
        from bot.config import LOG_CHANNEL
        user = message.from_user
        user_link = f"<a href='tg://user?id={user_id}'>{user.first_name}</a>"
        await client.send_message(
            LOG_CHANNEL,
            f"📥 <b>File Received</b>\n\n"
            f"👤 <b>User:</b> {user_link} (<code>{user_id}</code>)\n"
            f"📄 <b>File:</b> <code>{getattr(message.document or message.video, 'file_name', 'Unknown')}</code>"
        )
    except Exception as e:
        log.error(f"Failed to send log to channel: {e}")

    # Check if it's a video file
    video_info = await check_and_process_video_document(message)
    log.info(f"Video analysis result: {video_info}")

    if not video_info["is_video_document"] or not video_info["is_encodable"]:
        # Not a video — ignore silently (audio, unknown docs, etc.)
        return

    if not video_info["encoding_ready"]:
        await message.reply_text(
            "❌ <b>File too large or unsupported.</b>\n"
            "Max supported size is 2GB."
        )
        return

    # Video detected — show quality selection
    await show_quality_selection(client, message)
