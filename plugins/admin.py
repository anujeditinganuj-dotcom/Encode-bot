# Developed by ARGON telegram: @REACTIVEARGON
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
try:
    from pyrogram.errors.pyromod.listener_timeout import ListenerTimeout
except ImportError:
    from asyncio import TimeoutError as ListenerTimeout

from bot.logger import LOGGER, send_logs
from bot.utils.restart import restart_bot
from bot.utils.shell import shell_command
from bot.config import OWNER_ID
from database import full_userbase, del_user, get_variable, set_variable

log = LOGGER(__name__)


@Client.on_message(filters.command("restart"))
async def handle_restart(client, message):
    try:
        await message.reply_text("Restarting...")
        await restart_bot(client, message)
    except Exception as e:
        log.error(e)
        await message.reply_text(f"Error: {e}")


@Client.on_message(filters.command("log") & filters.private)
async def handle_logs(client, message):
    await send_logs(client, message)


@Client.on_message(filters.command("shell"))
async def handle_shell(client, message):
    await shell_command(client, message)


@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client, message):
    admin = await get_variable("admin", [])
    userid = message.from_user.id
    # If admin list is empty, allow owner (fallback)
    if not admin:
        if userid != OWNER_ID:
            return
    elif userid not in admin:
        return

    if not message.reply_to_message:
        await message.reply_text("Reply to a message to broadcast it.")
        return

    query = await full_userbase()
    broadcast_msg = message.reply_to_message

    total = 0
    successful = 0
    blocked = 0
    deleted = 0
    unsuccessful = 0
    edit = 0

    pls_wait = await message.reply(
        "<i>Select broadcast type</i>",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📢 Normal", callback_data="broadcast_normal"),
                    InlineKeyboardButton("📌 Pin", callback_data="broadcast_pin"),
                ]
            ]
        ),
    )

    try:
        callback = await client.wait_for_callback_query(
            chat_id=message.chat.id,
            filters=filters.user(message.from_user.id),
            timeout=30,
        )
    except asyncio.TimeoutError:
        await pls_wait.edit("<i>⏰ Timed out. Please try again.</i>")
        return

    await callback.answer()  # acknowledge the callback click

    pin = 1 if callback.data == "broadcast_pin" else 0
    await pls_wait.edit("<i>📤 Broadcast started...</i>")

    for chat_id in query:
        try:
            sent = await broadcast_msg.copy(chat_id)
            successful += 1
            if pin:
                try:
                    await sent.pin(both_sides=True)
                except Exception:
                    pass
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                sent = await broadcast_msg.copy(chat_id)
                successful += 1
            except BaseException:
                unsuccessful += 1
        except UserIsBlocked:
            await del_user(chat_id)
            blocked += 1
        except InputUserDeactivated:
            await del_user(chat_id)
            deleted += 1
        except Exception:
            unsuccessful += 1
        total += 1
        edit += 1

        if edit >= 20:
            edit = 0
            status = f"""<b><u>Broadcast in progress</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
            await pls_wait.edit_text(status)

    status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
    await pls_wait.edit_text(status)


@Client.on_message(filters.command("admin") & filters.private)
async def admin(client, message):
    if message.from_user.id != OWNER_ID:
        return

    a = await get_variable("admin", [])
    txt = f"<blockquote expandable>💠 𝐀𝐃𝐌𝐈𝐍 𝐏𝐀𝐍𝐄𝐋  ♻️\n</blockquote>\n<blockquote expandable>🚩 𝐀𝐃𝐌𝐈𝐍 :- {a}\n</blockquote>\n<blockquote expandable>⚠️ 𝐍𝐎𝐓𝐄 - ADMINS CAN USE ALL BOT COMMMANDS EXCEPT FSUB, ADMIN ‼️</blockquote>"
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("𝐀𝐃𝐃 𝐀𝐃𝐌𝐈𝐍", callback_data="admin_add"),
                InlineKeyboardButton("𝐑𝐄𝐌𝐎𝐕𝐄 𝐀𝐃𝐌𝐈𝐍", callback_data="admin_rem"),
            ],
            [
                InlineKeyboardButton("ϲℓοѕє", callback_data="cb_close"),
            ],
        ]
    )
    await message.reply_photo(
        photo="https://i.ibb.co/kVwykh4J/ce566244dba9.jpg",
        caption=txt,
        reply_markup=keyboard,
    )


@Client.on_callback_query(filters.regex("^admin_"))
async def admin2(client, query):
    uid = query.from_user.id
    user_id = uid

    if uid != OWNER_ID:
        await query.answer(
            "❌ ϐακκα!, γου αяє иοτ αℓℓοωє∂ το υѕє τнє ϐυττοи", show_alert=True
        )
        return

    # Extract "add" or "rem" from the callback data
    action = query.data.split("_")[1]

    txt = (
        "<blockquote expandable>⚠️ <b>𝖣𝗈 𝖮𝗇𝖾 𝖡𝖾𝗅𝗈𝗐</b> ⚠️</blockquote>\n"
        "<blockquote expandable><i>🔱 𝖥𝗈𝗋𝗐𝖺𝗋𝖽 𝖠 𝖬𝖾𝗌𝗌𝖺𝗀𝖾 𝖥𝗋𝗈𝗆 𝖠𝖽𝗆𝗂𝗇</i></blockquote>\n"
        "<blockquote expandable><i>💠 𝖲𝖾𝗇𝖽 𝖬𝖾 𝖠𝖽𝗆𝗂𝗇 𝖨𝖣</i></blockquote>"
        "<blockquote>♨️ 𝗠𝗔𝗞𝗘 𝗦𝗨𝗥𝗘 𝗔𝗗𝗠𝗜𝗡 𝗜𝗗 𝗜𝗦 𝗩𝗔𝗟𝗜𝗗 ♨️</blockquote>"
    )

    if action == "add":
        while True:
            b = await client.send_message(
                uid,
                text=txt,
                reply_markup=ReplyKeyboardMarkup(
                    [["❌ Cancel"]], one_time_keyboard=True, resize_keyboard=True
                ),
            )
            try:
                a = await client.listen(chat_id=uid, timeout=30)
            except ListenerTimeout:
                await client.send_message(
                    chat_id=uid,
                    text="⏳ Timeout! Admin Setup cancelled.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                await b.delete()
                break

            if a.text and a.text.lower() == "❌ cancel":
                await client.send_message(
                    chat_id=uid,
                    text="❌ Admin setup cancelled.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                await b.delete()
                break

            chat_id = None
            if a.forward_from:
                chat_id = a.forward_from.id
            elif a.forward_from_chat:
                chat_id = a.forward_from_chat.id
            else:
                try:
                    chat_id = int(a.text.strip())
                except ValueError:
                    await client.send_message(
                        user_id, "Invalid input! Please send a valid user ID."
                    )
                    await b.delete()
                    continue

            admin1 = await get_variable("admin", [])

            if chat_id in admin1:
                await client.send_message(
                    user_id, "User is already admin resend correct id...."
                )
                await b.delete()
                continue
            admin1.append(chat_id)

            await set_variable("admin", admin1)
            await b.delete()
            await client.send_message(
                user_id, f"✅ User {chat_id} added to admins.", reply_markup=ReplyKeyboardRemove()
            )
            # Refresh panel
            await admin(client, query.message)
            await query.message.delete()
            break

    elif action == "rem":
        while True:
            b = await client.send_message(
                uid,
                text=txt,
                reply_markup=ReplyKeyboardMarkup(
                    [["❌ Cancel"]], one_time_keyboard=True, resize_keyboard=True
                ),
            )
            try:
                a = await client.listen(chat_id=uid, timeout=30)
            except ListenerTimeout:
                await client.send_message(
                    chat_id=uid,
                    text="⏳ Timeout! Admin Setup cancelled.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                await b.delete()
                break

            if a.text and a.text.lower() == "❌ cancel":
                await client.send_message(
                    chat_id=uid,
                    text="❌ Admin setup cancelled.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                await b.delete()
                break

            chat_id = None
            if a.forward_from:
                chat_id = a.forward_from.id
            elif a.forward_from_chat:
                chat_id = a.forward_from_chat.id
            else:
                try:
                    chat_id = int(a.text.strip())
                except ValueError:
                    await client.send_message(
                        user_id, "Invalid input! Please send a valid user ID."
                    )
                    await b.delete()
                    continue

            admin1 = await get_variable("admin", [])

            if chat_id not in admin1:
                await client.send_message(
                    user_id, "User is not admin resend correct id...."
                )
                await b.delete()
                continue
            admin1.remove(chat_id)

            await set_variable("admin", admin1)
            await b.delete()
            await client.send_message(
                user_id, f"✅ User {chat_id} removed from admins.", reply_markup=ReplyKeyboardRemove()
            )
            # Refresh panel
            await admin(client, query.message)
            await query.message.delete()
            break

    else:
        await query.answer("Invalid action.", show_alert=True)
