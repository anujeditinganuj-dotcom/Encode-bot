# Developed by ARGON telegram: @REACTIVEARGON
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import OWNER_ID
from bot.func.encode import active_encodings
from bot.func.queue_manager import queue_manager
from bot.logger import LOGGER

log = LOGGER(__name__)


@Client.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    try:
        args = message.command
        user_id = message.from_user.id

        if len(args) < 2:
            await message.reply_text("⚠️ Usage: `/cancel <job_id>`")
            return

        job_id = args[1]
        job = queue_manager.get_job(job_id)

        if not job:
            await message.reply_text("⚠️ Job not found.")
            return

        # Permission check
        if job.user_id != user_id and user_id != OWNER_ID:
            await message.reply_text("❌ You can only cancel your own jobs.")
            return

        # Cancel logic
        if job.status == "running":
            if job_id in active_encodings:
                process = active_encodings[job_id]
                await process.cancel()
                await message.reply_text(
                    f"✅ Job `{job_id}` cancelled (Process terminated)."
                )
            else:
                # Should not happen if status is running, but fallback
                await queue_manager.cancel_job(job_id)
                await message.reply_text(f"✅ Job `{job_id}` marked for cancellation.")
        else:
            if await queue_manager.cancel_job(job_id):
                await message.reply_text(f"✅ Job `{job_id}` removed from queue.")
            else:
                await message.reply_text(f"⚠️ Could not cancel job `{job_id}`.")

    except Exception as e:
        log.error(f"Error in cancel command: {e}")
        await message.reply_text("❌ An error occurred.")


@Client.on_message(filters.command("queue"))
async def queue_command(client: Client, message: Message):
    jobs = queue_manager.get_all_jobs()
    if not jobs:
        await message.reply_text("📭 <b>Queue is empty.</b>")
        return

    text = "<blockquote>📋 <b>Current Queue</b></blockquote>\n\n"
    for i, job in enumerate(jobs, 1):
        status_icon = "⏳" if job.status == "pending" else "🏃"
        user_link = f"<a href='tg://user?id={job.user_id}'>{job.user_id}</a>"
        file_size = job.file_size if hasattr(job, "file_size") else "Unknown"

        text += (
            f"<b>{i}.</b> <code>{job.job_id}</code> {status_icon}\n"
            f"   ├ 👤 {user_link}\n"
            f"   ├ 📄 <code>{job.file_name}</code>\n"
            f"   └ 📦 {file_size}\n\n"
        )

    await message.reply_text(text)


@Client.on_message(filters.command("info") & filters.user(OWNER_ID))
async def info_command(client: Client, message: Message):
    try:
        args = message.command
        if len(args) < 2:
            await message.reply_text("⚠️ Usage: `/info <job_id>`")
            return

        job_id = args[1]
        job = queue_manager.get_job(job_id)

        if not job:
            await message.reply_text("⚠️ Job not found.")
            return

        # Get user info
        try:
            user = await client.get_users(job.user_id)
            user_text = f"{user.mention} (`{user.id}`)"
            username = f"@{user.username}" if user.username else "N/A"
        except BaseException:
            user_text = f"User ID: `{job.user_id}`"
            username = "Unknown"

        status_map = {
            "pending": "⏳ Pending",
            "running": "🏃 Running",
            "completed": "✅ Completed",
            "failed": "❌ Failed",
            "cancelled": "🚫 Cancelled",
        }
        status = status_map.get(job.status, job.status)

        text = (
            f"<blockquote>ℹ️ <b>Job Information</b></blockquote>\n\n"
            f"🆔 <b>Job ID:</b> <code>{job.job_id}</code>\n"
            f"📊 <b>Status:</b> {status}\n\n"
            f"<blockquote>👤 <b>User Details</b>\n"
            f"├ <b>Name:</b> {user_text}\n"
            f"└ <b>Username:</b> {username}</blockquote>\n\n"
            f"<blockquote>📁 <b>File Details</b>\n"
            f"├ <b>Name:</b> {job.file_name}\n"
            f"└ <b>Size:</b> {job.file_size}</blockquote>"
        )

        await message.reply_text(text)

    except Exception as e:
        log.error(f"Error in info command: {e}")
        await message.reply_text("❌ An error occurred.")


@Client.on_message(filters.command(["clear", "cancelall"]))
async def clear_command(client: Client, message: Message):
    user_id = message.from_user.id

    if user_id == OWNER_ID:
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "👤 Clear My Jobs", callback_data="queue_clear_mine"
                    ),
                    InlineKeyboardButton(
                        "🌐 Clear All Jobs", callback_data="queue_clear_all"
                    ),
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="queue_cancel")],
            ]
        )
        await message.reply_text(
            "⚙️ <b>Admin Queue Control</b>\nChoose an action:", reply_markup=buttons
        )
    else:
        # User can only clear their own
        count = await _cancel_user_jobs(user_id)
        await message.reply_text(f"✅ Cleared {count} of your jobs.")


@Client.on_callback_query(filters.regex(r"^queue_"))
async def queue_callback_handler(client: Client, callback_query: CallbackQuery):
    action = callback_query.data
    user_id = callback_query.from_user.id

    if action == "queue_cancel":
        await callback_query.message.delete()
        return

    if user_id != OWNER_ID:
        await callback_query.answer("❌ Admin only.", show_alert=True)
        return

    if action == "queue_clear_mine":
        count = await _cancel_user_jobs(user_id)
        await callback_query.message.edit(f"✅ Cleared {count} of your jobs.")

    elif action == "queue_clear_all":
        count = await _cancel_all_jobs()
        await callback_query.message.edit(f"✅ Cleared ALL jobs ({count}).")


async def _cancel_user_jobs(user_id: int) -> int:
    jobs = queue_manager.get_user_jobs(user_id)
    count = 0
    for job in jobs:
        if await _cancel_single_job(job.job_id):
            count += 1
    return count


async def _cancel_all_jobs() -> int:
    # Get count before clearing
    count = len(queue_manager.get_all_jobs())

    # Cancel running jobs first
    for job_id in list(active_encodings.keys()):
        await active_encodings[job_id].cancel()

    # Clear queue (cancels pending and cleans files)
    await queue_manager.clear_queue()

    return count


async def _cancel_single_job(job_id: str) -> bool:
    # If running, kill process
    if job_id in active_encodings:
        await active_encodings[job_id].cancel()
        return True

    # If pending, remove from queue
    return await queue_manager.cancel_job(job_id)


@Client.on_message(filters.command("cancelall") & filters.user(OWNER_ID))
async def cancel_all_command(client: Client, message: Message):
    count = await _cancel_all_jobs()
    await message.reply_text(f"✅ Cleared ALL jobs ({count}).")
