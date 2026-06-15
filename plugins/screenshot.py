# Developed by ARGON telegram: @REACTIVEARGON
import asyncio
import os
import time
import shlex
from pathlib import Path
from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto

from bot.logger import LOGGER
from bot.decorator import task

log = LOGGER(__name__)

@Client.on_message(filters.command("ss"))
@task
async def screenshot_command(client: Client, message: Message, query=False):
    # Check reply
    if not message.reply_to_message:
        await message.reply_text("❌ <b>Reply to a video to generate screenshots.</b>")
        return

    target_msg = message.reply_to_message
    if not (target_msg.video or target_msg.document):
        await message.reply_text("❌ <b>Reply to a valid video file.</b>")
        return

    # Check if document is video (mime type)
    if target_msg.document and "video" not in target_msg.document.mime_type:
        await message.reply_text("❌ <b>File is not a video.</b>")
        return

    status_msg = await message.reply_text("📥 <b>Downloading Video...</b>")

    # Prepare paths
    downloads_dir = Path("downloads")
    downloads_dir.mkdir(exist_ok=True)

    file_name = "ss_input.mp4"
    if target_msg.video:
        file_name = target_msg.video.file_name or "video.mp4"
    elif target_msg.document:
        file_name = target_msg.document.file_name or "video.mp4"

    safe_filename = "".join(c for c in file_name if c.isalnum() or c in (" ", "-", "_", ".")).strip()
    file_path = downloads_dir / f"ss_{int(time.time())}_{safe_filename}"

    try:
        # Download
        # We use direct download here for simplicity, or we could import safe_download_media
        # Let's use direct client.download_media with progress

        start_time = time.time()
        async def progress(current, total):
            now = time.time()
            if now - start_time > 3: # Update every 3s
                try:
                    pct = current * 100 / total
                    await status_msg.edit(f"📥 <b>Downloading...</b> {pct:.1f}%")
                except Exception:
                    pass

        downloaded_path = await client.download_media(
            target_msg,
            file_name=str(file_path),
            progress=progress
        )

        if not downloaded_path:
            await status_msg.edit("❌ <b>Download Failed.</b>")
            return

        await status_msg.edit("📸 <b>Generating Screenshots...</b>")

        # Get duration
        duration = 0
        if target_msg.video:
            duration = target_msg.video.duration

        if not duration:
            # Probe
            cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {shlex.quote(downloaded_path)}"
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            out, _ = await proc.communicate()
            try:
                duration = float(out.decode().strip())
            except Exception:
                duration = 100 # Fallback

        # Generate 5 screenshots
        timestamps = [
            duration * 0.2,
            duration * 0.35,
            duration * 0.5,
            duration * 0.65,
            duration * 0.8
        ]

        screenshots = []
        for i, ts in enumerate(timestamps):
            ss_path = str(file_path.parent / f"ss_{i}_{file_path.stem}.jpg")
            # ffmpeg -ss {ts} -i {input} -frames:v 1 -q:v 2 {output}
            cmd = f"ffmpeg -ss {ts} -i {shlex.quote(downloaded_path)} -frames:v 1 -q:v 2 -y {shlex.quote(ss_path)}"

            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()

            if os.path.exists(ss_path):
                screenshots.append(ss_path)

        if not screenshots:
            await status_msg.edit("❌ <b>Failed to generate screenshots.</b>")
            # Cleanup
            os.remove(downloaded_path)
            return

        await status_msg.edit("📤 <b>Uploading Screenshots...</b>")

        # Upload as album
        media_group = [InputMediaPhoto(ss, caption=f"Timestamp: {timestamps[i]:.1f}s") for i, ss in enumerate(screenshots)]

        # Set caption only on first item
        media_group[0].caption = (
            f"📸 <b>Screenshots Generated</b>\n"
            f"📁 <b>File:</b> {file_name}\n"
            f"⏱️ <b>Duration:</b> {duration:.1f}s"
        )

        await message.reply_media_group(media_group)
        await status_msg.delete()

    except Exception as e:
        log.error(f"Screenshot error: {e}")
        await status_msg.edit(f"❌ <b>Error:</b> {e}")

    finally:
        # Cleanup
        if 'downloaded_path' in locals() and os.path.exists(downloaded_path):
            os.remove(downloaded_path)
        for ss in screenshots:
            if os.path.exists(ss):
                os.remove(ss)
