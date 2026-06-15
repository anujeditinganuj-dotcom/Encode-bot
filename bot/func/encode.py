# Developed by ARGON telegram: @REACTIVEARGON
import asyncio
import json
import math
import os
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import psutil
from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.func.download_manager import download_manager
from bot.func.ffmpeg_utils import generate_ffmpeg_cmd
from bot.func.pyroutils.progress import progress_for_pyrogram, humanbytes, TimeFormatter
from bot.func.queue_manager import queue_manager
from bot.func.upload_manager import upload_manager
from bot.logger import LOGGER
from database import get_user_settings

log = LOGGER(__name__)

# Global dictionary to store active encoding processes for callback handling
# Map: job_id -> FFmpegProcess instance
active_encodings = {}





@dataclass
class EncodingStats:
    percent: float = 0.0
    fps: float = 0.0
    bitrate: str = "N/A"
    speed: str = "N/A"
    frame: int = 0
    total_frames: int = 0
    eta: str = "N/A"
    elapsed: str = "0s"
    size: str = "0 B"
    estimated_size: str = "0 B"
    compression: str = "1.0x"


class FFmpegProcess:
    def __init__(
        self,
        cmd: str,
        input_file: str,
        output_file: str,
        total_duration: float,
        original_size: int,
        file_name: str = "Unknown",
        codec: str = "Unknown",
        crf: str = "N/A",
        preset: str = "N/A",
        resolution: str = "N/A",
        current_step: int = 1,
        total_steps: int = 1,
        thumbnail_path: Optional[str] = None,
    ):
        self.cmd = cmd
        self.input_file = input_file
        self.output_file = output_file
        self.total_duration = total_duration
        self.original_size = original_size
        self.file_name = file_name
        self.codec = codec
        self.crf = crf
        self.preset = preset
        self.resolution = resolution
        self.current_step = current_step
        self.total_steps = total_steps
        self.thumbnail_path = thumbnail_path
        self.process: Optional[asyncio.subprocess.Process] = None
        self.start_time = 0
        self.is_paused = False
        self.is_cancelled = False
        self.yield_queue = False  # New flag to indicate yielding
        self.stats = EncodingStats()
        self.job_id = ""  # Set by manager
        self.message: Optional[Message] = None  # Store message for updates
        self.client: Optional[Client] = None
        self.user_id: int = 0
        self.is_viewing_queue = False

    async def start(self):
        self.start_time = time.time()

        # Parse command string into list for exec
        args = shlex.split(self.cmd)

        executable = args[0] if args else "ffmpeg"
        # args[1:] already contains -i <input> ... <output> as built by generate_ffmpeg_cmd
        # We strip the input/output from cmd and rebuild to avoid double -i and wrong output position.
        # Find and remove leading "-i <file>" pair from args[1:]
        cmd_args = args[1:] if len(args) > 1 else []

        # Remove any existing -i <input> flags (there should be exactly one at start)
        filtered_args = []
        skip_next = False
        for arg in cmd_args:
            if skip_next:
                skip_next = False
                continue
            if arg == "-i":
                skip_next = True
                continue
            filtered_args.append(arg)

        # The last element of filtered_args is the output file path — remove it
        if filtered_args:
            filtered_args = filtered_args[:-1]

        # Ensure progress is monitored
        if "-progress" not in filtered_args:
            filtered_args.extend(["-progress", "pipe:1"])

        # Construct final arguments list: input -> encoding options -> output -> overwrite
        final_args = ["-i", self.input_file] + filtered_args + [self.output_file, "-y"]

        log.info(f"Starting FFmpeg: {executable} {' '.join(final_args)}")

        self.process = await asyncio.create_subprocess_exec(
            executable,
            *final_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def pause(self):
        if self.process and not self.is_paused:
            try:
                parent = psutil.Process(self.process.pid)
                # Suspend children first (if any)
                for child in parent.children(recursive=True):
                    try:
                        child.suspend()
                    except BaseException:
                        pass

                # Suspend parent
                parent.suspend()

                self.is_paused = True
                self.yield_queue = True  # Trigger yield
                log.info(f"Process {self.process.pid} and children suspended.")
            except Exception as e:
                log.error(f"Failed to pause process: {e}")

    async def resume(self):
        if self.process and self.is_paused:
            try:
                parent = psutil.Process(self.process.pid)
                # Resume parent
                parent.resume()

                # Resume children
                for child in parent.children(recursive=True):
                    try:
                        child.resume()
                    except BaseException:
                        pass

                self.is_paused = False
                self.yield_queue = False
                log.info(f"Process {self.process.pid} and children resumed.")
            except Exception as e:
                log.error(f"Failed to resume process: {e}")

    async def cancel(self):
        self.is_cancelled = True
        if self.process:
            try:
                self.process.terminate()
            except Exception as e:
                log.error(f"Failed to terminate process: {e}")

    def parse_progress(self, line: str):
        try:
            parts = line.split("=")
            if len(parts) != 2:
                return
            key, value = parts[0].strip(), parts[1].strip()

            if key == "frame":
                self.stats.frame = int(value)
            elif key == "fps":
                self.stats.fps = float(value)
            elif key == "bitrate":
                self.stats.bitrate = value
            elif key == "speed":
                self.stats.speed = value
            elif key == "out_time_us":
                us = int(value)
                current_seconds = us / 1000000
                if self.total_duration > 0:
                    self.stats.percent = min(
                        100.0, (current_seconds / self.total_duration) * 100
                    )

                elapsed = time.time() - self.start_time
                if self.stats.percent > 0:
                    total_estimated = elapsed / (self.stats.percent / 100)
                    eta_seconds = total_estimated - elapsed
                    self.stats.eta = TimeFormatter(eta_seconds * 1000)

                self.stats.elapsed = TimeFormatter(elapsed * 1000)

        except Exception:
            pass

    def get_progress_ui(self) -> str:
        bar_length = 20
        filled = int(self.stats.percent / 100 * bar_length)
        bar = "▰" * filled + "▱" * (bar_length - filled)

        current_size = 0
        if os.path.exists(self.output_file):
            current_size = os.path.getsize(self.output_file)

        self.stats.size = humanbytes(self.original_size)
        current_human = humanbytes(current_size)

        estimated = "0 B"
        comp = 1.0
        if self.stats.percent > 0:
            est_size = current_size / (self.stats.percent / 100)
            estimated = humanbytes(est_size)
            if est_size > 0:
                comp = self.original_size / est_size

        # System Stats
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage(".").percent
        used_disk_gb = psutil.disk_usage(".").used / (1024**3)
        free_disk_gb = psutil.disk_usage(".").free / (1024**3)

        # Queue Info
        queue_pos = "Processing"
        queue_total = queue_manager._queue.qsize() + 1  # +1 for current

        status_icon = "⏸️" if self.is_paused else "🚀"
        status_text = "Paused (Yielded)" if self.is_paused else "Encoding in Progress"

        step_info = ""
        if self.total_steps > 1:
            step_info = f" (Quality {self.current_step}/{self.total_steps})"

        return (
            f"🎬 <b>{status_text}</b> {status_icon}{step_info}\n"
            f"<blockquote>📁 <b>File:</b> <code>{self.file_name}</code></blockquote>\n\n"
            f"<blockquote>📋 <b>Job Info</b>\n"
            f"🆔 <b>ID:</b> <code>{self.job_id}</code>\n"
            f"🔢 <b>Queue:</b> {queue_pos} (Total: {queue_total})\n"
            f"⚙️ <b>Settings:</b> {self.codec} | {self.resolution} | CRF {self.crf} | {self.preset}\n"
            f"🎯 <b>Quality:</b> {self.current_step}/{self.total_steps}</blockquote>\n\n"
            f"<blockquote><code>{bar}</code> <b>{self.stats.percent:.1f}%</b></blockquote>\n\n"
            f"<blockquote>⏱️ <b>Time Information</b>\n"
            f"┣ <b>⏳ ETA:</b> {self.stats.eta}\n"
            f"┣ <b>⏱️ Elapsed:</b> {self.stats.elapsed}\n"
            f"┗ <b>💨 Speed:</b> {self.stats.speed}</blockquote>\n\n"
            f"<blockquote>📊 <b>Performance Stats</b> 🚀\n"
            f"┣ <b>🎥 Video FPS:</b> 24.0 (original)\n"
            f"┣ <b>⚡ Encoding:</b> {self.stats.fps:.1f} fps\n"
            f"┣ <b>✨ Quality:</b> {self.stats.bitrate}\n"
            f"┗ <b>📈 Frames:</b> {self.stats.frame}</blockquote>\n\n"
            f"<blockquote>💾 <b>File Information</b>\n"
            f"┣ <b>📥 Input:</b> {self.stats.size}\n"
            f"┣ <b>📤 Current:</b> {current_human}\n"
            f"┣ <b>🔮 Estimated:</b> {estimated}\n"
            f"┗ <b>🗜️ Compression:</b> {comp:.1f}x</blockquote>\n\n"
            f"<blockquote>🖥️ <b>System Usage</b>\n"
            f"┣ <b>🧠 CPU:</b> {cpu}%\n"
            f"┣ <b>💡 RAM:</b> {ram}%\n"
            f"┣ <b>💿 Disk:</b> {disk}%\n"
            f"┣ <b>📦 Used Storage:</b> {used_disk_gb:.2f} GB\n"
            f"┗ <b>🆓 Free Storage:</b> {free_disk_gb:.2f} GB\n"
            f"</blockquote>\n\n"
            "🔄 <i>Updates every 3 seconds</i>"
        )


async def _monitor_process(process: FFmpegProcess) -> str:
    """
    Monitors the FFmpeg process.
    Returns: 'FINISHED', 'FAILED', 'CANCELLED', or 'YIELDED'
    """
    last_update = 0

    while True:
        # Check if process is yielded (Paused and released from queue)
        if process.yield_queue:
            return "YIELDED"

        if process.process.returncode is not None:
            break

        try:
            # We need to handle the case where it hangs if paused?
            # If paused, stdout might not produce output, but we still need to check yield_queue
            # So we should use wait_for with timeout
            try:
                line = await asyncio.wait_for(
                    process.process.stdout.readline(), timeout=1.0
                )
                if not line:
                    break
                process.parse_progress(line.decode().strip())
            except asyncio.TimeoutError:
                # Timeout is fine, just loop to check yield_queue and update UI
                pass

        except Exception:
            break

        now = time.time()
        # Increased interval to 5.0s to avoid FloodWait
        if now - last_update >= 5.0:
            try:
                if not process.is_viewing_queue:
                    pause_text = "▶️ Resume" if process.is_paused else "⏸️ Pause"
                    buttons = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    pause_text, callback_data=f"enc_pause_{process.job_id}"
                                ),
                                InlineKeyboardButton(
                                    "❌ Cancel",
                                    callback_data=f"enc_cancel_{process.job_id}",
                                ),
                            ],
                            [
                                InlineKeyboardButton(
                                    "📋 Queue", callback_data=f"enc_queue_{process.job_id}"
                                ),
                            ],
                        ]
                    )
                    await process.message.edit(
                        process.get_progress_ui(), reply_markup=buttons
                    )
                last_update = now
            except Exception as e:
                # Handle FloodWait specifically if possible, or just log
                if "FLOOD_WAIT" in str(e):
                    log.warning(f"FloodWait hit, backing off UI updates: {e}")
                    last_update = now + 10 # Backoff for 10s
                else:
                    log.error(f"Failed to update UI: {e}")

    await process.process.wait()

    if process.is_cancelled:
        return "CANCELLED"

    if process.process.returncode == 0:
        return "FINISHED"
    else:
        return "FAILED"


# ... (existing imports)

# ... (FFmpegProcess class and methods)


async def _handle_job_completion(
    process: FFmpegProcess, status: str, cleanup_input: bool = True
):
    if status == "YIELDED":
        try:
            # Delete the active progress message to clean up chat
            try:
                await process.message.delete()
            except Exception:
                pass

            pause_text = "▶️ Resume"
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            pause_text, callback_data=f"enc_pause_{process.job_id}"
                        ),
                        InlineKeyboardButton(
                            "❌ Cancel", callback_data=f"enc_cancel_{process.job_id}"
                        ),
                    ]
                ]
            )

            # Send a NEW message for the paused state with detailed info
            user = await process.client.get_users(process.user_id)
            user_link = f"<a href='tg://user?id={process.user_id}'>{user.first_name}</a>"

            pause_msg = await process.client.send_message(
                process.user_id,
                f"<blockquote>⏸️ <b>Job Paused & Yielded</b>\n"
                f"🆔 <b>ID:</b> <code>{process.job_id}</code>\n"
                f"📁 <b>File:</b> <code>{process.file_name}</code>\n"
                f"⚙️ <b>Settings:</b> {process.codec} | {process.resolution} | CRF {process.crf}\n"
                f"👤 <b>User ID:</b> <code>{process.user_id}</code>\n"
                f"🔗 <b>Sent By:</b> {user_link}\n"
                f"🎯 <b>Next Step:</b> Quality {process.current_step}/{process.total_steps}</blockquote>",
                reply_markup=buttons,
            )
            # Update process message reference so resume can use it (or delete it)
            process.message = pause_msg

        except Exception as e:
            log.error(f"Failed to update UI on pause: {e}")
        # Do NOT cleanup files, they are needed for resume
        return

    if status == "CANCELLED":
        await process.message.edit("❌ <b>Encoding Cancelled</b>")
        # Cleanup both input and output files
        _cleanup_files(process, cleanup_input=True)  # Always cleanup on cancel
        if process.job_id in active_encodings:
            del active_encodings[process.job_id]
        return

    if status == "FINISHED":
        # Do NOT edit message to "Queuing Upload..."
        # Instead, just start the upload worker which will send its own message

        async def upload_worker():
            await _upload_video(
                process.client,
                process.user_id,
                process.output_file,
                None, # No progress_msg passed, it will create one
                process.stats,
                process.original_size,
                codec=process.codec,
                crf=process.crf,
                preset=process.preset,
                resolution=process.resolution,
                thumb=process.thumbnail_path,
            )

        await upload_manager.add_upload_job(process.user_id, upload_worker)

        # Cleanup input only if requested
        try:
            if cleanup_input and os.path.exists(process.input_file):
                os.remove(process.input_file)
        except Exception:
            pass

        # Delete progress message if this is the last step
        if process.current_step == process.total_steps:
            try:
                await process.message.delete()
            except Exception:
                pass

        if process.job_id in active_encodings:
            del active_encodings[process.job_id]
        return

    if status == "FAILED":
        stderr = await process.process.stderr.read()
        log.error(f"FFmpeg failed: {stderr.decode()}")
        await process.message.edit(
            f"❌ <b>Encoding Failed</b>\n\n<code>{stderr.decode()[:1000]}</code>"
        )
        _cleanup_files(process, cleanup_input=True)  # Cleanup on fail
        if process.job_id in active_encodings:
            del active_encodings[process.job_id]
        return


def _cleanup_files(process: FFmpegProcess, cleanup_input: bool = True):
    try:
        if cleanup_input and os.path.exists(process.input_file):
            os.remove(process.input_file)
        if os.path.exists(process.output_file):
            os.remove(process.output_file)
    except Exception as e:
        log.error(f"Cleanup failed: {e}")


async def _run_encoding_job(
    ffmpeg_cmd: str,
    input_file: str,
    output_file: str,
    client: Client,
    message: Message,
    job_id: str,
    user_id: int,
    cleanup_input: bool = True,
    codec: str = "Unknown",
    crf: str = "N/A",
    preset: str = "N/A",
    resolution: str = "N/A",
    current_step: int = 1,
    total_steps: int = 1,
    thumbnail_path: Optional[str] = None,
):
    duration = 0
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            input_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode == 0:
            data = json.loads(out.decode())
            if "format" in data and "duration" in data["format"]:
                duration = float(data["format"]["duration"])
            else:
                for stream in data.get("streams", []):
                    if "duration" in stream:
                        duration = float(stream["duration"])
                        break
    except Exception:
        duration = 100

    if duration == 0:
        duration = 100
    original_size = os.path.getsize(input_file)

    process = FFmpegProcess(
        ffmpeg_cmd,
        input_file,
        output_file,
        duration,
        original_size,
        Path(input_file).name,
        codec=codec,
        crf=crf,
        preset=preset,
        resolution=resolution,
        current_step=current_step,
        total_steps=total_steps,
        thumbnail_path=thumbnail_path,
    )
    process.job_id = job_id
    process.message = message
    process.client = client
    process.user_id = user_id

    active_encodings[job_id] = process

    try:
        await process.start()
        status = await _monitor_process(process)
        await _handle_job_completion(process, status, cleanup_input=cleanup_input)

    except Exception as e:
        log.error(f"Encoding job failed: {e}")
        await message.edit(f"❌ <b>Encoding Failed</b>\n\n<code>{str(e)}</code>")
        _cleanup_files(process, cleanup_input=True)
        if job_id in active_encodings:
            del active_encodings[job_id]


async def resume_encoding_job(job_id: str):
    """Resumes a yielded job from the queue."""
    if job_id not in active_encodings:
        log.warning(f"Attempted to resume non-existent or finished job: {job_id}")
        return

    process = active_encodings[job_id]

    # Resume the process
    await process.resume()

    # Send NEW message for resumed progress
    try:
        # Delete old pause message
        await process.message.delete()
    except Exception:
        pass

    process.message = await process.client.send_message(
        process.user_id, "🔄 <b>Resuming Encoding...</b>"
    )

    # Re-enter monitoring loop
    try:
        status = await _monitor_process(process)
        await _handle_job_completion(process, status)
    except Exception as e:
        log.error(f"Resumed job failed: {e}")
        await process.message.edit(f"❌ <b>Resumed Job Failed</b>\n\n<code>{str(e)}</code>")
        _cleanup_files(process)
        if job_id in active_encodings:
            del active_encodings[job_id]

async def safe_download_media(client: Client, message: Message, file_path: str, progress_msg: Message):
    try:
        await download_manager.acquire()
        downloaded_path = await client.download_media(
            message,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("📥 Downloading...", progress_msg, time.time())
        )

        if not downloaded_path or not os.path.exists(downloaded_path):
            log.error(f"Download reported success but file not found: {downloaded_path}")
            return None

        return downloaded_path
    except Exception as e:
        log.error(f"Download failed: {e}")
        return None
    finally:
        download_manager.release()


def reconstruct_worker(job, client: Client):
    """
    Reconstructs the worker function for a restored job.
    """

    async def worker(job_id_arg):
        try:
            # 1. Fetch the message
            log.info(
                f"Restoring job {job.job_id}: Fetching message {job.message_id} from chat {job.chat_id}"
            )
            message = await client.get_messages(job.chat_id, job.message_id)

            if not message or (not message.video and not message.document):
                log.error(f"Failed to fetch message for job {job.job_id}")
                return

            # 2. Prepare download path
            downloads_dir = Path("downloads")
            downloads_dir.mkdir(exist_ok=True)

            # Use stored filename or generate one
            file_name = job.file_name
            if not file_name or file_name == "Unknown":
                file_name = f"restored_{job.job_id}.mp4"

            safe_filename = "".join(
                c for c in file_name if c.isalnum() or c in (" ", "-", "_", ".")
            ).strip()
            download_file_path = downloads_dir / safe_filename

            # 3. Send/Update status message
            status_msg = await client.send_message(
                job.user_id, f"🔄 **Restoring Job {job.job_id}...**"
            )

            # 4. Download
            downloaded_path = await safe_download_media(
                client, message, str(download_file_path), status_msg
            )

            if not downloaded_path:
                await status_msg.edit(
                    "❌ **Restoration Failed:** Could not download file."
                )
                return

            # 5. Run Encoding
            # Fetch settings
            settings = await get_user_settings(job.user_id)
            if not settings:
                settings = {}  # Use defaults handled in utils

            # Restore watermark assets if needed
            from bot.func.ffmpeg_utils import prepare_watermark_assets, prepare_thumbnail
            prepare_watermark_assets(job.user_id, settings)
            thumbnail_path = prepare_thumbnail(job.user_id, settings, input_file=downloaded_path)

            # Generate commands
            # We don't have a specific output base name here, so we derive it
            output_base = str(Path(downloaded_path).parent / f"encoded_{safe_filename}")
            # Remove extension for base
            output_base = os.path.splitext(output_base)[0]

            commands = generate_ffmpeg_cmd(settings, downloaded_path, output_base, thumbnail_path)

            # Extract settings for UI
            video_settings = settings.get("video", {})
            codec = video_settings.get("codec", "libx264")
            crf = video_settings.get("crf", "23")
            preset = video_settings.get("preset", "medium")

            for i, cmd_info in enumerate(commands):
                is_last = i == len(commands) - 1
                resolution = cmd_info.get("suffix", "1080p")

                await _run_encoding_job(
                    cmd_info["cmd"],
                    downloaded_path,
                    cmd_info["output_file"],
                    client,
                    status_msg,
                    job_id_arg,
                    job.user_id,
                    cleanup_input=is_last,
                    codec=codec,
                    crf=str(crf),
                    preset=preset,
                    resolution=resolution,
                    current_step=i + 1,
                    total_steps=len(commands),
                    thumbnail_path=thumbnail_path,
                )

        except Exception as e:
            log.error(f"Error in restored worker for job {job.job_id}: {e}")

    return worker


async def _upload_video(
    client: Client,
    user_id: int,
    file_path: str,
    progress_msg: Optional[Message], # Made optional
    stats: EncodingStats,
    original_size: int,
    codec: str = "Unknown",
    crf: str = "N/A",
    preset: str = "N/A",
    resolution: str = "N/A",
    thumb: Optional[str] = None,
):
    upload_msg = None
    try:
        file_name = Path(file_path).name
        file_size = os.path.getsize(file_path)

        comp = 1.0
        if file_size > 0:
            comp = original_size / file_size

        bot_username = (await client.get_me()).username

        caption = (
            f"🎬 <b>Encoding Completed Successfully!</b>\n\n"
            f"<blockquote>📁 <b>File:</b> <code>{file_name}</code>\n"
            f"⚙️ <b>Settings:</b> {codec} | {resolution} | CRF {crf} | {preset}</blockquote>\n\n"
            f"<blockquote>📊 <b>Stats</b>\n"
            f"📁 <b>Original:</b> `{stats.size}`\n"
            f"📤 <b>Encoded:</b> `{humanbytes(file_size)}`\n"
            f"⏱️ <b>Time:</b> `{stats.elapsed}`\n"
            f"🗜️ <b>Compression:</b> `{comp:.1f}x`</blockquote>\n\n"
            f"🤖 <b>Encoded by:</b> @{bot_username}\n"
            "👨‍💻 <b>Dev:</b> <a href='tg://user?id=7024179022'>Owner</a>"
        )

        # Send new upload message
        upload_msg = await client.send_message(user_id, "📤 <b>Starting Upload...</b>")

        await client.send_document(
            chat_id=user_id,
            document=file_path,
            caption=caption,
            thumb=thumb,
            progress=progress_for_pyrogram,
            progress_args=("📤 Uploading encoded video...", upload_msg, time.time())
        )

        # Delete upload progress message
        await upload_msg.delete()

        # Log to Channel
        try:
            log_channel = -1002252580234
            user = await client.get_users(user_id)
            user_link = f"<a href='tg://user?id={user_id}'>{user.first_name}</a>"

            log_caption = (
                f"<b>🎬 New Encode Completed</b>\n\n"
                f"👤 <b>User:</b> {user_link} (<code>{user_id}</code>)\n"
                f"📁 <b>File:</b> <code>{file_name}</code>\n"
                f"⚙️ <b>Settings:</b> {codec} | {resolution} | CRF {crf}\n"
                f"📊 <b>Size:</b> {humanbytes(file_size)}\n\n"
                f"🤖 <b>Encoded by:</b> @{bot_username}"
            )

            await client.send_document(
                chat_id=log_channel,
                document=file_path,
                caption=log_caption
            )
        except Exception as log_error:
            log.error(f"Failed to send log to channel: {log_error}")

    except Exception as e:
        log.error(f"Upload failed: {e}")
        if upload_msg:
            await upload_msg.edit(f"❌ <b>Upload Failed</b>\n\n<code>{str(e)}</code>")
    finally:
        # Cleanup output file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            log.error(f"Cleanup failed: {e}")


async def encode(
    ffmpeg_cmd: str,  # Legacy/Override argument
    input_file: str,
    client: Client,
    user_id: int,
    custom_output_name: Optional[str] = None,
    display_mode: str = "rich",
    update_interval: float = 3.0,
    message: Optional[Message] = None,
    chat_id: int = 0,
    message_id: int = 0,
) -> Dict[str, Any]:

    if not custom_output_name:
        custom_output_name = f"encoded_{Path(input_file).name}"

    # Base output path without extension
    output_base = str(Path(input_file).parent / os.path.splitext(custom_output_name)[0])

    # Delete the download message
    if message:
        try:
            await message.delete()
        except Exception:
            pass

    # Send NEW message for encoding start
    message = await client.send_message(user_id, "⏳ <b>Adding to Queue...</b>")

    async def worker(job_id_arg):
        # Fetch settings
        settings = await get_user_settings(user_id)
        if not settings:
            settings = {}

        # Restore watermark assets if needed
        from bot.func.ffmpeg_utils import prepare_watermark_assets, prepare_thumbnail
        prepare_watermark_assets(user_id, settings)
        thumbnail_path = prepare_thumbnail(user_id, settings, input_file=input_file)

        # Inject user_id for watermark font lookup
        settings["user_id"] = user_id

        # Generate commands
        commands = generate_ffmpeg_cmd(settings, input_file, output_base, thumbnail_path)

        # If commands is empty (shouldn't happen with defaults), fallback?
        if not commands:
            # Fallback to simple default
            commands = [
                {
                    "cmd": "ffmpeg -i {} -c:v libx264 -crf 23 -c:a aac -b:a 128k -y {}".format(
                        shlex.quote(input_file), shlex.quote(output_base + ".mp4")
                    ),
                    "output_file": output_base + ".mp4",
                }
            ]

        # Extract settings for UI
        video_settings = settings.get("video", {})
        codec = video_settings.get("codec", "libx264")
        crf = video_settings.get("crf", "23")
        preset = video_settings.get("preset", "medium")

        for i, cmd_info in enumerate(commands):
            is_last = i == len(commands) - 1
            resolution = cmd_info.get("suffix", "1080p")

            await _run_encoding_job(
                cmd_info["cmd"],
                input_file,
                cmd_info["output_file"],
                client,
                message,
                job_id_arg,
                user_id,
                cleanup_input=is_last,
                codec=codec,
                crf=str(crf),
                preset=preset,
                resolution=resolution,
                current_step=i + 1,
                total_steps=len(commands),
                thumbnail_path=thumbnail_path,
            )

    file_size_str = humanbytes(os.path.getsize(input_file))
    file_name = Path(input_file).name

    job_id = await queue_manager.add_job(
        user_id,
        worker,
        "PLACEHOLDER",
        file_size=file_size_str,
        file_name=file_name,
        chat_id=chat_id,
        message_id=message_id,
        task_type="encode",
        input_file=input_file,
        output_file=output_base,  # This is just for reference now
    )

    if job_id is None:
        await message.edit(
            "⚠️ <b>Duplicate Job Detected</b>\n\nYou already have this file in the queue."
        )
        return {"success": False, "error": "Duplicate job"}

    if job_id in queue_manager._jobs:
        queue_manager._jobs[job_id].args = (job_id,)

    await message.edit(
        f"⏳ <b>Job Queued</b>\n"
        f"🆔 Job ID: <code>{job_id}</code>\n"
        f"🔢 Position: {queue_manager._queue.qsize()}"
    )

    return {"success": True, "job_id": job_id, "output_file": output_base}
