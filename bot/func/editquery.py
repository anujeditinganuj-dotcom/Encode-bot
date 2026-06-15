# Developed by ARGON telegram: @REACTIVEARGON
from pyrogram import Client
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.func.encode import active_encodings
from bot.func.queue_manager import queue_manager
from bot.logger import LOGGER

log = LOGGER(__name__)


async def handle_encoding_callback(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    parts = data.split("_")
    if len(parts) < 3:
        return

    action = parts[1]
    job_id = parts[2]

    if job_id not in active_encodings:
        await callback_query.answer("⚠️ Job not found or finished.", show_alert=True)
        return

    process = active_encodings[job_id]

    if action == "pause":
        if process.is_paused:
            # Check if job was yielded
            if process.yield_queue:
                # Job was yielded, need to re-queue it
                from bot.func.encode import resume_encoding_job

                try:
                    buttons = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "❌ Cancel", callback_data=f"enc_cancel_{job_id}"
                                )
                            ]
                        ]
                    )
                except Exception as e:
                    log.error(f"Failed to update UI in callback: {e}")
                    return

                async def resume_worker(jid):
                    await resume_encoding_job(jid)

                await queue_manager.add_job(
                    process.user_id, resume_worker, process.job_id
                )

                q_pos = queue_manager._queue.qsize()
                await callback_query.answer(
                    f"⏳ Queued at position {q_pos}", show_alert=True
                )
                try:
                    await process.message.edit(
                        f"<blockquote>⏳ <b>Resume Queued</b>\n"
                        f"Job ID: <code>{process.job_id}</code>\n"
                        f"Position: {q_pos}</blockquote>",
                        reply_markup=buttons,
                    )
                except Exception as e:
                    log.error(f"Failed to edit message in callback: {e}")

            else:
                # Not yielded, just resume immediately
                await process.resume()
                await callback_query.answer("▶️ Resumed")
        else:
            await process.pause()
            await callback_query.answer("⏸️ Paused")

            # Update UI to show paused state

    elif action == "cancel":
        await process.cancel()
        await callback_query.answer("❌ Cancelled")

    elif action == "queue":
        process.is_viewing_queue = True
        jobs = queue_manager.get_all_jobs()

        text = "<blockquote>📋 <b>Current Queue</b></blockquote>\n\n"
        if not jobs:
            text += "📭 <b>Queue is empty.</b>"
        else:
            for i, job in enumerate(jobs, 1):
                status_icon = "⏳" if job.status == "pending" else "🏃"
                file_size = job.file_size if hasattr(job, "file_size") else "Unknown"
                text += (
                    f"<b>{i}.</b> <code>{job.job_id}</code> {status_icon}\n"
                    f"   ├ 📄 <code>{job.file_name}</code>\n"
                    f"   └ 📦 {file_size}\n\n"
                )

        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🔙 Back", callback_data=f"enc_back_{job_id}")
                ]
            ]
        )
        await process.message.edit(text, reply_markup=buttons)
        await callback_query.answer()

    elif action == "back":
        process.is_viewing_queue = False
        # Immediately restore progress UI
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
        await process.message.edit(process.get_progress_ui(), reply_markup=buttons)
        await callback_query.answer()
