# Developed by ARGON telegram: @REACTIVEARGON
import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.decorator import task
from bot.func.ffmpeg_utils import validate_ffmpeg_command
from bot.logger import LOGGER
from database import get_user_settings, update_user_settings

log = LOGGER(__name__)

# Global state for user inputs
# Format: {user_id: {"type": "setting_key", "message_id": int, "data": any}}
# INPUT_STATE = {}  <-- Removed in favor of client.listen

# Default Settings
DEFAULT_SETTINGS = {
    "video": {"crf": "23", "preset": "medium", "resolution": ["1080p"], "codec": "libx264"},
    "audio": {"bitrate": "128k"},
    "metadata": {
        "global": {"title": "Auto Encoded", "author": "AutoAnimePro"},
        "video": {},
        "audio": {},
        "subtitle": {},
    },
    "custom_ffmpeg": {},
}

METADATA_KEYS = {
    "global": [
        "title", "artist", "album", "album_artist", "genre", "track", "disc", "date",
        "year", "comment", "description", "composer", "performer", "publisher",
        "encoder", "encoded_by", "lyrics", "synopsis", "copyright", "language",
        "creation_time", "software", "tool", "major_brand", "minor_version",
        "compatible_brands", "album-sort", "title-sort", "artist-sort",
        "composer-sort", "show", "season_number", "episode_sort", "network"
    ],
    "video": [
        "title", "language", "handler_name", "encoder", "creation_time", "rotate",
        "comment", "fps", "resolution", "bit_rate", "color_primaries",
        "color_space", "color_transfer"
    ],
    "audio": [
        "title", "artist", "album", "track", "genre", "language", "handler_name",
        "encoder", "creation_time", "comment", "lyrics", "composer",
        "album_artist", "publisher"
    ],
    "subtitle": [
        "title", "language", "handler_name", "encoder", "creation_time", "forced",
        "default", "track_name"
    ]
}


@Client.on_message(filters.command(["settings", "u_setting"]))
@task
async def settings_command(client, message, query=False):
    user_id = message.from_user.id
    settings = await get_user_settings(user_id)

    # Merge with defaults if missing
    if not settings:
        settings = DEFAULT_SETTINGS
        await update_user_settings(user_id, settings)

    # Ensure resolution is a list (migration)
    if "video" in settings and isinstance(settings["video"].get("resolution"), str):
        settings["video"]["resolution"] = [settings["video"]["resolution"]]
        await update_user_settings(user_id, settings)

    res_display = ", ".join(settings.get("video", {}).get("resolution", ["1080p"]))

    text = (
        f"<b>⚙️ User Settings</b>\n\n"
        f"<blockquote><b>Video:</b>\n"
        f"• Codec: <code>{settings.get('video', {}).get('codec', 'mpeg4')}</code>\n"
        f"• CRF: <code>{settings.get('video', {}).get('crf', '23')}</code>\n"
        f"• Preset: <code>{settings.get('video', {}).get('preset', 'medium')}</code>\n"
        f"• Resolution: <code>{res_display}</code>\n\n"
        f"<b>Audio:</b>\n"
        f"• Bitrate: <code>{settings.get('audio', {}).get('bitrate', '128k')}</code>\n\n"
        f"<b>Metadata:</b>\n"
        f"• Global Title: <code>{settings.get('metadata', {}).get('global', {}).get('title', 'N/A')}</code></blockquote>"
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎬 Video", callback_data="set_video"),
                InlineKeyboardButton("🎵 Audio", callback_data="set_audio"),
            ],
            [
                InlineKeyboardButton("📝 Metadata", callback_data="set_meta"),
                InlineKeyboardButton("🛠 Custom FFmpeg", callback_data="set_custom"),
            ],
            [
                InlineKeyboardButton("💧 Watermark", callback_data="set_watermark"),
                InlineKeyboardButton("🖼️ Thumbnail", callback_data="set_thumbnail"),
            ],
            [InlineKeyboardButton("❌ Close", callback_data="cb_close")],
        ]
    )

    if query:
        await message.edit_text(text=text, reply_markup=buttons)
    else:
        await message.reply_text(text=text, reply_markup=buttons)


@Client.on_callback_query(filters.regex("^set_"))
async def settings_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    message = callback_query.message

    if data == "set_main":
        # Clear state when returning to main menu

        await settings_command(client, message, query=True)
        return

    settings = await get_user_settings(user_id)

    if data == "set_video":
        text = "<b>🎬 Video Settings</b>\n\nSelect a parameter to edit:"
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"Codec ({settings.get('video', {}).get('codec', 'mpeg4')})",
                        callback_data="edit_video_codec",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"CRF ({settings.get('video', {}).get('crf', '23')})",
                        callback_data="edit_video_crf",
                    ),
                    InlineKeyboardButton(
                        f"Preset ({settings.get('video', {}).get('preset', 'medium')})",
                        callback_data="edit_video_preset",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Resolution (Multi)", callback_data="edit_video_res"
                    )
                ],
                [InlineKeyboardButton("🔙 Back", callback_data="set_main")],
            ]
        )
        await message.edit_text(text=text, reply_markup=buttons)

    elif data == "set_audio":
        text = "<b>🎵 Audio Settings</b>\n\nSelect a parameter to edit:"
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"Bitrate ({settings.get('audio', {}).get('bitrate', '128k')})",
                        callback_data="edit_audio_bitrate",
                    )
                ],
                [InlineKeyboardButton("🔙 Back", callback_data="set_main")],
            ]
        )
        await message.edit_text(text=text, reply_markup=buttons)

    elif data == "set_meta":
        text = "<b>📝 Metadata Settings</b>\n\nSelect a category to edit:"
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🌐 Global", callback_data="set_meta_cat_global"),
                    InlineKeyboardButton("🎬 Video", callback_data="set_meta_cat_video"),
                ],
                [
                    InlineKeyboardButton("🎵 Audio", callback_data="set_meta_cat_audio"),
                    InlineKeyboardButton("💬 Subtitle", callback_data="set_meta_cat_subtitle"),
                ],
                [InlineKeyboardButton("🔙 Back", callback_data="set_main")],
            ]
        )
        await message.edit_text(text=text, reply_markup=buttons)

    elif data == "set_custom":
        custom_cmds = settings.get("custom_ffmpeg", {})
        text = "<b>🛠 Custom FFmpeg Commands</b>\n\nSaved Commands:\n"

        cmds_buttons = []
        if custom_cmds:
            for name, cmd in custom_cmds.items():
                text += f"• <b>{name}</b>: <code>{cmd}</code>\n"
                cmds_buttons.append(
                    [
                        InlineKeyboardButton(
                            f"🗑 Delete {name}", callback_data=f"del_custom_{name}"
                        )
                    ]
                )
        else:
            text += "No custom commands saved."

        cmds_buttons.append(
            [InlineKeyboardButton("➕ Add New Command", callback_data="add_custom")]
        )
        cmds_buttons.append([InlineKeyboardButton("🔙 Back", callback_data="set_main")])

        await message.edit_text(
            text=text, reply_markup=InlineKeyboardMarkup(cmds_buttons)
        )

    elif data == "set_watermark":
        await watermark_callback(client, callback_query)
        await callback_query.stop_propagation()

    elif data.startswith("set_thumbnail"):
        await thumbnail_callback(client, callback_query)
        await callback_query.stop_propagation()

    elif data.startswith("set_meta_cat_"):
        category = data.replace("set_meta_cat_", "")
        page = 0
        if "|" in category:
            category, page = category.split("|")
            page = int(page)

        keys = METADATA_KEYS.get(category, [])
        total_keys = len(keys)
        per_page = 10
        total_pages = (total_keys + per_page - 1) // per_page

        start = page * per_page
        end = start + per_page
        current_keys = keys[start:end]

        text = f"<b>📝 {category.capitalize()} Metadata</b>\n\nSelect a key to edit (Page {page+1}/{total_pages}):"

        buttons = []
        # Create 2 columns
        row = []
        for key in current_keys:
            # Check if value is set
            val = settings.get("metadata", {}).get(category, {}).get(key, "")
            icon = "✏️" if val else "➕"
            label = f"{icon} {key}"

            row.append(InlineKeyboardButton(label, callback_data=f"edit_meta_val_{category}|{key}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        # Navigation
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"set_meta_cat_{category}|{page-1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"set_meta_cat_{category}|{page+1}"))

        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="set_meta")])

        await message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("set_meta_cat_"):
        category = data.replace("set_meta_cat_", "")
        page = 0
        if "|" in category:
            category, page = category.split("|")
            page = int(page)

        keys = METADATA_KEYS.get(category, [])
        total_keys = len(keys)
        per_page = 10
        total_pages = (total_keys + per_page - 1) // per_page

        start = page * per_page
        end = start + per_page
        current_keys = keys[start:end]

        text = f"<b>📝 {category.capitalize()} Metadata</b>\n\nSelect a key to edit (Page {page+1}/{total_pages}):"

        buttons = []
        # Create 2 columns
        row = []
        for key in current_keys:
            # Check if value is set
            val = settings.get("metadata", {}).get(category, {}).get(key, "")
            icon = "✏️" if val else "➕"
            label = f"{icon} {key}"

            row.append(InlineKeyboardButton(label, callback_data=f"edit_meta_val_{category}|{key}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        # Navigation
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"set_meta_cat_{category}|{page-1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"set_meta_cat_{category}|{page+1}"))

        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="set_meta")])

        await message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex("^edit_"))
async def edit_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    message = callback_query.message

    settings = await get_user_settings(user_id)

    if data == "edit_video_res":
        current_res = settings.get("video", {}).get("resolution", ["1080p"])
        if isinstance(current_res, str):
            current_res = [current_res]

        all_res = ["4k", "2k", "1080p", "720p", "480p", "360p", "240p", "144p"]

        buttons = []
        row = []
        for res in all_res:
            icon = "☑️" if res in current_res else "⬜"
            row.append(InlineKeyboardButton(f"{icon} {res}", callback_data=f"toggle_res_{res}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="set_video")])

        await message.edit_text(
            text="<b>🎬 Select Resolutions:</b>\n<i>Toggle multiple. 4K=2160p | 2K=1440p</i>",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # Set input state
    # INPUT_STATE[user_id] = {"type": data, "message_id": message.id} # Removed

    prompt = ""
    if data == "edit_video_codec":
        prompt = "<b>Enter new Video Codec:</b>\n<i>Examples: libx264, libx265, libvpx-vp9, libaom-av1, mpeg4</i>"
    elif data == "edit_video_crf":
        prompt = "<b>Enter new CRF value (0-51):</b>\n<i>Lower is better quality. Default: 23</i>"
    elif data == "edit_video_preset":
        prompt = "<b>Enter new Preset:</b>\n<i>(ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow)</i>"
    elif data == "edit_audio_bitrate":
        prompt = "<b>Enter new Audio Bitrate:</b>\n<i>Example: 128k, 192k, 320k</i>"
    elif data.startswith("edit_meta_val_"):
        category, key = data.split("_", 3)[-1].split("|")
        prompt = f"<b>Enter value for {category} metadata '{key}':</b>\n<i>Send 'clear' to remove.</i>"

    # Use client.listen for input
    prompt_msg = await message.edit_text(text=prompt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="cancel_input")]]))

    try:
        input_msg = await client.listen(chat_id=user_id, timeout=60)
        text = input_msg.text
        await input_msg.delete()
    except asyncio.TimeoutError:
        await prompt_msg.delete()
        await message.reply_text("❌ Timed out.")
        return
    except Exception:
        # Cancelled
        await settings_command(client, message, query=True)
        return

    # Process Input
    # Process Input
    if data == "edit_video_codec":
        if "video" not in settings: settings["video"] = {}
        settings["video"]["codec"] = text
        await update_user_settings(user_id, settings)
        await message.reply_text(f"✅ Codec set to <code>{text}</code>")

    elif data == "edit_video_crf":
        if not text.isdigit() or not (0 <= int(text) <= 51):
            await message.reply_text("❌ <b>Invalid CRF!</b>\nPlease enter a number between 0 and 51.")
            return
        if "video" not in settings: settings["video"] = {}
        settings["video"]["crf"] = text
        await update_user_settings(user_id, settings)
        await message.reply_text(f"✅ CRF set to <code>{text}</code>")

    elif data == "edit_video_preset":
        valid_presets = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
        if text.lower() not in valid_presets:
             await message.reply_text(f"❌ <b>Invalid Preset!</b>\nChoose from: {', '.join(valid_presets)}")
             return
        if "video" not in settings: settings["video"] = {}
        settings["video"]["preset"] = text.lower()
        await update_user_settings(user_id, settings)
        await message.reply_text(f"✅ Preset set to <code>{text}</code>")

    elif data == "edit_audio_bitrate":
        if not text.endswith("k") or not text[:-1].isdigit():
             await message.reply_text("❌ <b>Invalid Bitrate!</b>\nFormat: 128k, 192k, etc.")
             return
        if "audio" not in settings: settings["audio"] = {}
        settings["audio"]["bitrate"] = text
        await update_user_settings(user_id, settings)
        await message.reply_text(f"✅ Audio Bitrate set to <code>{text}</code>")

    elif data.startswith("edit_meta_val_"):
        category, key = data.split("_", 3)[-1].split("|")

        if "metadata" not in settings: settings["metadata"] = {}
        if category not in settings["metadata"]: settings["metadata"][category] = {}

        if text.lower() == "clear":
            if key in settings["metadata"][category]:
                del settings["metadata"][category][key]
            await message.reply_text(f"🗑 Cleared {category} metadata <b>{key}</b>")
        else:
            settings["metadata"][category][key] = text
            await message.reply_text(f"✅ Set {category} metadata <b>{key}</b> to <code>{text}</code>")

        await update_user_settings(user_id, settings)

        # Return to category menu
        callback_query.data = f"set_meta_cat_{category}"
        await settings_callback(client, callback_query)
        return

    # Return to main menu
    await settings_command(client, message, query=True)


@Client.on_callback_query(filters.regex("^toggle_res_"))
async def toggle_res_callback(client, callback_query: CallbackQuery):
    res = callback_query.data.replace("toggle_res_", "")
    user_id = callback_query.from_user.id

    settings = await get_user_settings(user_id)
    if "video" not in settings:
        settings["video"] = {}

    current_res = settings["video"].get("resolution", ["1080p"])
    if isinstance(current_res, str):
        current_res = [current_res]

    if res in current_res:
        if len(current_res) > 1:  # Prevent removing the last one
            current_res.remove(res)
    else:
        current_res.append(res)

    settings["video"]["resolution"] = current_res
    await update_user_settings(user_id, settings)

    # Refresh menu
    callback_query.data = "edit_video_res"
    await edit_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^add_custom"))
async def add_custom_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    message = callback_query.message

    # 1. Ask for Name
    text = "<b>Enter a NAME for your custom command:</b>\n<i>Example: my_1080p_preset</i>"
    prompt_msg = await message.edit_text(text=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="cancel_input")]]))

    try:
        name_msg = await client.listen(chat_id=user_id, timeout=60)
        name = name_msg.text
        await name_msg.delete()
    except asyncio.TimeoutError:
        await prompt_msg.delete()
        await message.reply_text("❌ Timed out.")
        return
    except Exception:
        # Cancelled
        callback_query.data = "set_custom"
        await settings_callback(client, callback_query)
        return

    # 2. Ask for Command
    text = f"<b>Enter the FFmpeg command for '{name}':</b>\n<i>Example: -c:v libx264 -crf 23</i>"
    await prompt_msg.edit_text(text=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="cancel_input")]]))

    try:
        cmd_msg = await client.listen(chat_id=user_id, timeout=60)
        cmd = cmd_msg.text
        await cmd_msg.delete()
    except asyncio.TimeoutError:
        await prompt_msg.delete()
        await message.reply_text("❌ Timed out.")
        return
    except Exception:
        # Cancelled
        callback_query.data = "set_custom"
        await settings_callback(client, callback_query)
        return

    # Validate
    if not validate_ffmpeg_command(cmd):
        await message.reply_text("❌ <b>Invalid Command!</b>\n\nForbidden flags detected (-i, -y) or empty command.")
        return

    settings = await get_user_settings(user_id)
    if "custom_ffmpeg" not in settings:
        settings["custom_ffmpeg"] = {}
    settings["custom_ffmpeg"][name] = cmd
    await update_user_settings(user_id, settings)

    await message.reply_text(f"✅ Custom command <b>{name}</b> saved!")

    # Return to custom menu
    callback_query.data = "set_custom"
    await settings_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^del_custom_"))
async def del_custom_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    name = callback_query.data.replace("del_custom_", "")

    settings = await get_user_settings(user_id)
    if "custom_ffmpeg" in settings and name in settings["custom_ffmpeg"]:
        del settings["custom_ffmpeg"][name]
        await update_user_settings(user_id, settings)

    # Refresh custom menu
    callback_query.data = "set_custom"
    await settings_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^(set_watermark|wm_(toggle|select|set|preview))"))
async def watermark_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    message = callback_query.message
    log.info(f"Watermark Callback: {data} for user {user_id}")

    settings = await get_user_settings(user_id)
    wm = settings.get("watermark", {})

    # Defaults
    if "enabled" not in wm: wm["enabled"] = False
    if "type" not in wm: wm["type"] = "text" # Default to text if enabled
    if "position" not in wm: wm["position"] = "top-right"
    if "opacity" not in wm: wm["opacity"] = "0.5"
    if "text" not in wm: wm["text"] = "AutoAnimePro"
    if "font_size" not in wm: wm["font_size"] = "24"
    if "border_opacity" not in wm: wm["border_opacity"] = "0.5"
    if "timing_mode" not in wm: wm["timing_mode"] = "always"
    if "margins" not in wm: wm["margins"] = {"top": 10, "bottom": 10, "left": 10, "right": 10}

    if data == "set_watermark":
        status_icon = "🟢 Enabled" if wm['enabled'] else "🔴 Disabled"

        text = (
            f"<b>💧 Watermark Configuration</b>\n\n"
            f"<blockquote><b>Status:</b> {status_icon}\n"
            f"<b>Type:</b> {wm['type'].upper()}\n"
            f"<b>Position:</b> {wm['position'].replace('-', ' ').title()}\n"
            f"<b>Opacity:</b> {wm['opacity']}\n"
            f"<b>Timing:</b> {wm['timing_mode'].title()}</blockquote>\n\n"
        )

        if wm['type'] == 'text':
            has_font = "✅ Custom" if os.path.exists(f"watermarks/fonts/{user_id}.ttf") else "🤖 Default"
            text += (
                f"📝 <b>Text Settings:</b>\n"
                f"<blockquote>• <b>Content:</b> <code>{wm['text']}</code>\n"
                f"• <b>Size:</b> {wm['font_size']}\n"
                f"• <b>Border Opacity:</b> {wm['border_opacity']}\n"
                f"• <b>Font:</b> {has_font}</blockquote>"
            )
        elif wm['type'] == 'image':
            has_img = "✅ Uploaded" if wm.get("image_path") else "❌ Not Set"
            text += f"🖼 <b>Image Settings:</b>\n<blockquote>• <b>File:</b> {has_img}\n• <b>Scale:</b> {wm.get('scale', '0.1')}</blockquote>"

        # Toggle Button
        toggle_text = "🔴 Disable" if wm['enabled'] else "🟢 Enable"
        toggle_btn = InlineKeyboardButton(toggle_text, callback_data="wm_toggle_enable")

        buttons = [
            [
                toggle_btn,
                InlineKeyboardButton(f"Type: {wm['type'].upper()}", callback_data="wm_select_type"),
                InlineKeyboardButton(f"Pos: {wm['position'].title()}", callback_data="wm_select_pos"),
            ],
            [
                InlineKeyboardButton(f"Opacity: {wm['opacity']}", callback_data="wm_edit_opacity"),
                InlineKeyboardButton(f"Timing: {wm['timing_mode'].title()}", callback_data="wm_toggle_timing"),
                InlineKeyboardButton("📏 Margins", callback_data="wm_select_margins")
            ]
        ]

        # Dynamic Buttons based on Type
        if wm['type'] == 'text':
            buttons.append([
                InlineKeyboardButton("✏️ Text", callback_data="wm_edit_text"),
                InlineKeyboardButton("📏 Size", callback_data="wm_edit_size"),
                InlineKeyboardButton("🔲 Border", callback_data="wm_edit_border_opacity"),
            ])
            buttons.append([InlineKeyboardButton("🔤 Custom Font", callback_data="wm_upload_font")])
        elif wm['type'] == 'image':
            buttons.append([
                InlineKeyboardButton("📤 Upload Image", callback_data="wm_upload_img"),
                InlineKeyboardButton("📐 Scale", callback_data="wm_edit_scale"),
            ])

        # Timing Config
        if wm['timing_mode'] != 'always':
            buttons.append([
                InlineKeyboardButton("⏱ Config Timing", callback_data="wm_config_timing"),
                InlineKeyboardButton("❓ Tutorial", callback_data="wm_timing_tutorial")
            ])

        buttons.append([
            InlineKeyboardButton("👁 Preview", callback_data="wm_preview"),
            InlineKeyboardButton("🔙 Back", callback_data="set_main")
        ])

        await message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "wm_toggle_enable":
        wm['enabled'] = not wm['enabled']
        if "watermark" not in settings: settings["watermark"] = {}
        settings["watermark"]["enabled"] = wm['enabled']
        await update_user_settings(user_id, settings)
        await callback_query.answer("✅ Updated", show_alert=False)

        callback_query.data = "set_watermark"
        await watermark_callback(client, callback_query)

    elif data == "wm_select_type":
        text = "<b>Select Watermark Type:</b>"
        buttons = [
            [InlineKeyboardButton("📝 Text", callback_data="wm_set_type_text")],
            [InlineKeyboardButton("🖼 Image", callback_data="wm_set_type_image")],
            [InlineKeyboardButton("🔙 Back", callback_data="set_watermark")]
        ]
        await message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("wm_set_type_"):
        new_type = data.split("_")[-1]
        if "watermark" not in settings: settings["watermark"] = {}
        settings["watermark"]["type"] = new_type
        await update_user_settings(user_id, settings)
        await callback_query.answer("✅ Type Updated", show_alert=False)

        callback_query.data = "set_watermark"
        await watermark_callback(client, callback_query)

    elif data == "wm_select_pos":
        text = "<b>Select Watermark Position:</b>"
        buttons = [
            [InlineKeyboardButton("↖️ Top-Left", callback_data="wm_set_pos_top-left"), InlineKeyboardButton("↗️ Top-Right", callback_data="wm_set_pos_top-right")],
            [InlineKeyboardButton("↙️ Bottom-Left", callback_data="wm_set_pos_bottom-left"), InlineKeyboardButton("↘️ Bottom-Right", callback_data="wm_set_pos_bottom-right")],
            [InlineKeyboardButton("🔙 Back", callback_data="set_watermark")]
        ]
        await message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("wm_set_pos_"):
        new_pos = data.replace("wm_set_pos_", "")
        if "watermark" not in settings: settings["watermark"] = {}
        settings["watermark"]["position"] = new_pos
        await update_user_settings(user_id, settings)

        callback_query.data = "set_watermark"
        await watermark_callback(client, callback_query)

    elif data == "wm_toggle_timing":
        modes = ["always", "range", "interval"]
        current = wm.get("timing_mode", "always")
        new_mode = modes[(modes.index(current) + 1) % len(modes)]

        if "watermark" not in settings: settings["watermark"] = {}
        settings["watermark"]["timing_mode"] = new_mode
        await update_user_settings(user_id, settings)

        callback_query.data = "set_watermark"
        await watermark_callback(client, callback_query)

    elif data == "wm_select_margins":
        margins = wm.get("margins", {"top": 10, "bottom": 10, "left": 10, "right": 10})
        text = "<b>Select Margin to Edit:</b>"
        buttons = [
            [
                InlineKeyboardButton(f"⬆️ Top: {margins.get('top', 10)}", callback_data="wm_edit_margin_top"),
                InlineKeyboardButton(f"⬇️ Bottom: {margins.get('bottom', 10)}", callback_data="wm_edit_margin_bottom")
            ],
            [
                InlineKeyboardButton(f"⬅️ Left: {margins.get('left', 10)}", callback_data="wm_edit_margin_left"),
                InlineKeyboardButton(f"➡️ Right: {margins.get('right', 10)}", callback_data="wm_edit_margin_right")
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="set_watermark")]
        ]
        await message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "wm_preview":
        await message.reply_text("⏳ Generating Preview...")

        from bot.func.preview import generate_preview
        preview_path = await generate_preview(user_id, settings)

        if preview_path and os.path.exists(preview_path):
            await message.reply_photo(
                photo=preview_path,
                caption="<b>💧 Watermark Preview</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Delete", callback_data="cb_close")]])
            )
            os.remove(preview_path)
        else:
            await message.reply_text("❌ <b>Preview Failed!</b>\nCheck logs or ensure settings are valid.")


@Client.on_callback_query(filters.regex("^wm_edit_"))
async def wm_edit_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    message = callback_query.message
    log.info(f"WM Edit Callback: {data} for user {user_id}")

    settings = await get_user_settings(user_id)

    prompt = ""
    if data == "wm_edit_text":
        prompt = "<b>Enter Watermark Text:</b>"
    elif data == "wm_edit_size":
        prompt = "<b>Enter Font Size (10-100):</b>"
    elif data == "wm_edit_opacity":
        prompt = "<b>Enter Opacity (0.1 - 1.0):</b>"
    elif data == "wm_edit_border_opacity":
        prompt = "<b>Enter Border Opacity (0.0 - 1.0):</b>\n<i>0.0 = Invisible Border</i>"
    elif data == "wm_edit_scale":
        prompt = "<b>Enter Image Scale (0.1 - 1.0):</b>\n<i>Relative to video width.</i>"
    elif data.startswith("wm_edit_margin_"):
        side = data.split("_")[-1].title()
        prompt = f"<b>Enter {side} Margin (px):</b>"

    prompt_msg = await message.edit_text(text=prompt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="cancel_input")]]))

    try:
        input_msg = await client.listen(chat_id=user_id, timeout=60)
        text = input_msg.text
        await input_msg.delete()
        log.info(f"WM Edit Input: {text}")
    except asyncio.TimeoutError:
        await prompt_msg.delete()
        await message.reply_text("❌ Timed out.")
        return
    except Exception:
        # Cancelled or other error
        callback_query.data = "set_watermark"
        await watermark_callback(client, callback_query)
        return

    if "watermark" not in settings: settings["watermark"] = {}

    if data == "wm_edit_text":
        settings["watermark"]["text"] = text
    elif data == "wm_edit_size":
        if not text.isdigit() or not (10 <= int(text) <= 100):
            await message.reply_text("❌ <b>Invalid Size!</b>\nPlease enter a number between 10 and 100.")
            return
        settings["watermark"]["font_size"] = text
    elif data == "wm_edit_opacity":
        try:
            val = float(text)
            if not (0.1 <= val <= 1.0): raise ValueError
        except ValueError:
            await message.reply_text("❌ <b>Invalid Opacity!</b>\nPlease enter a number between 0.1 and 1.0.")
            return
        settings["watermark"]["opacity"] = text
    elif data == "wm_edit_border_opacity":
        try:
            val = float(text)
            if not (0.0 <= val <= 1.0): raise ValueError
        except ValueError:
            await message.reply_text("❌ <b>Invalid Opacity!</b>\nPlease enter a number between 0.0 and 1.0.")
            return
        settings["watermark"]["border_opacity"] = text
    elif data == "wm_edit_scale":
        try:
            val = float(text)
            if not (0.1 <= val <= 1.0): raise ValueError
        except ValueError:
            await message.reply_text("❌ <b>Invalid Scale!</b>\nPlease enter a number between 0.1 and 1.0.")
            return
        settings["watermark"]["scale"] = text
    elif data.startswith("wm_edit_margin_"):
        side = data.split("_")[-1]
        if not text.isdigit():
             await message.reply_text("❌ <b>Invalid Number!</b>\nPlease enter a valid integer.")
             return
        if "margins" not in settings["watermark"]: settings["watermark"]["margins"] = {}
        settings["watermark"]["margins"][side] = int(text)

        await update_user_settings(user_id, settings)
        await message.reply_text(f"✅ {side.title()} Margin updated!")

        # Return to margin menu
        callback_query.data = "wm_select_margins"
        await watermark_callback(client, callback_query)
        return

    await update_user_settings(user_id, settings)
    await message.reply_text("✅ Setting updated!")

    # Return
    callback_query.data = "set_watermark"
    await watermark_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^wm_upload_img"))
async def wm_upload_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    message = callback_query.message
    log.info(f"WM Upload Callback for user {user_id}")

    prompt_msg = await message.edit_text(
        text="<b>📤 Send your Watermark Image:</b>\n<i>(PNG/JPG supported)</i>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="cancel_input")]])
    )

    try:
        input_msg = await client.listen(chat_id=user_id, timeout=60)
        if not input_msg.photo and not input_msg.document:
             await message.reply_text("❌ Not an image!")
             return

        # Download
        save_path = os.path.join(os.getcwd(), "watermarks", f"{user_id}.png")
        path = await input_msg.download(file_name=save_path)
        await input_msg.delete()

        # Read binary data
        with open(path, "rb") as f:
            image_data = f.read()

        settings = await get_user_settings(user_id)
        if "watermark" not in settings: settings["watermark"] = {}
        settings["watermark"]["image_path"] = path
        settings["watermark"]["image_data"] = image_data # Save to DB
        await update_user_settings(user_id, settings)

        await message.reply_text("✅ Watermark Image Saved!")

    except asyncio.TimeoutError:
        await prompt_msg.delete()
        await message.reply_text("❌ Timed out.")
        return
    except Exception as e:
        if "ListenerCanceled" in str(e) or isinstance(e, asyncio.CancelledError):
             callback_query.data = "set_watermark"
             await watermark_callback(client, callback_query)
             return
        log.error(f"WM Upload Error: {e}")
        await prompt_msg.delete()
        return

    # Return
    callback_query.data = "set_watermark"
    await watermark_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^wm_config_timing"))
async def wm_timing_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    message = callback_query.message
    log.info(f"WM Timing Callback for user {user_id}")
    settings = await get_user_settings(user_id)
    mode = settings.get("watermark", {}).get("timing_mode", "always")

    prompt = ""
    if mode == "range":
        prompt = "<b>Enter Start and End time (seconds):</b>\n<i>Format: start end (e.g., 10 20)</i>"
    elif mode == "interval":
        prompt = "<b>Enter Duration and Period (seconds):</b>\n<i>Format: duration period (e.g., 5 30 -> Show for 5s every 30s)</i>"
    else:
        await message.reply_text("❌ Mode is 'Always'. No config needed.")
        return

    prompt_msg = await message.edit_text(text=prompt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="cancel_input")]]))

    try:
        input_msg = await client.listen(chat_id=user_id, timeout=60)
        text = input_msg.text
        await input_msg.delete()

        # Validate and Save
        parts = text.split()
        if len(parts) != 2:
             await message.reply_text("❌ Invalid Format! Need 2 numbers.")
             return

        try:
            v1, v2 = float(parts[0]), float(parts[1])
        except ValueError:
             await message.reply_text("❌ Invalid Numbers!")
             return

        if "watermark" not in settings: settings["watermark"] = {}

        if mode == "range":
            settings["watermark"]["start_time"] = v1
            settings["watermark"]["end_time"] = v2
        elif mode == "interval":
            settings["watermark"]["interval_duration"] = v1
            settings["watermark"]["interval_period"] = v2

        await update_user_settings(user_id, settings)
        await message.reply_text("✅ Timing Updated!")

    except asyncio.TimeoutError:
        await prompt_msg.delete()
        await message.reply_text("❌ Timed out.")
        return
    except Exception:
        # Cancelled
        callback_query.data = "set_watermark"
        await watermark_callback(client, callback_query)
        return

    # Return
    callback_query.data = "set_watermark"
    await watermark_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^wm_upload_font"))
async def wm_upload_font_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    message = callback_query.message
    log.info(f"WM Font Upload Callback for user {user_id}")

    prompt_msg = await message.edit_text(
        text="<b>🔤 Send your Font File:</b>\n<i>(TTF/OTF supported)</i>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="cancel_input")]])
    )

    try:
        input_msg = await client.listen(chat_id=user_id, timeout=60)
        if not input_msg.document or not input_msg.document.file_name.lower().endswith(('.ttf', '.otf')):
             await message.reply_text("❌ Not a valid font file (TTF/OTF)!")
             return

        # Ensure directory
        if not os.path.exists("watermarks/fonts"):
            os.makedirs("watermarks/fonts")

        # Download
        path = await input_msg.download(file_name=f"watermarks/fonts/{user_id}.ttf")
        await input_msg.delete()

        # Read binary data
        with open(path, "rb") as f:
            font_data = f.read()

        settings = await get_user_settings(user_id)
        if "watermark" not in settings: settings["watermark"] = {}
        settings["watermark"]["font_data"] = font_data # Save to DB
        await update_user_settings(user_id, settings)

        await message.reply_text("✅ Custom Font Saved!")

    except asyncio.TimeoutError:
        await prompt_msg.delete()
        await message.reply_text("❌ Timed out.")
        return
    except Exception as e:
        if "ListenerCanceled" in str(e) or isinstance(e, asyncio.CancelledError):
             callback_query.data = "set_watermark"
             await watermark_callback(client, callback_query)
             return
        log.error(f"WM Font Upload Error: {e}")
        await prompt_msg.delete()
        return

    # Return
    callback_query.data = "set_watermark"
    await watermark_callback(client, callback_query)


@Client.on_callback_query(filters.regex("^wm_timing_tutorial"))
async def wm_timing_tutorial_callback(client, callback_query: CallbackQuery):
    text = (
        "<b>⏱ Watermark Timing Tutorial</b>\n\n"
        "<b>1. Range Mode:</b>\n"
        "Show watermark only between specific times.\n"
        "• <i>Format:</i> <code>start end</code>\n"
        "• <i>Example:</i> <code>10 60</code> (Shows from 10s to 60s)\n\n"
        "<b>2. Interval Mode:</b>\n"
        "Flash the watermark periodically.\n"
        "• <i>Format:</i> <code>duration period</code>\n"
        "• <i>Example:</i> <code>5 30</code>\n"
        "• Shows for <b>5 seconds</b>.\n"
        "• Repeats every <b>30 seconds</b>.\n"
        "• (e.g., 0-5s, 30-35s, 60-65s...)\n\n"
        "<b>3. Always:</b>\n"
        "Watermark is always visible."
    )
    await callback_query.message.edit_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="set_watermark")]])
    )


@Client.on_callback_query(filters.regex("^cancel_input"))
async def cancel_input_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        # Try stopping the listener
        await client.stop_listening(chat_id=user_id)
    except Exception as e:
        log.error(f"Error stopping listener for {user_id}: {e}")

    await callback_query.answer("Cancelled")


@Client.on_callback_query(filters.regex(r"^set_thumbnail"))
async def thumbnail_callback(client, callback_query):
    user_id = callback_query.from_user.id
    settings = await get_user_settings(user_id)
    if not settings:
        settings = {}

    data = callback_query.data

    if data == "set_thumbnail":
        thumb_exists = "thumbnail" in settings
        status = "✅ Set" if thumb_exists else "❌ Not Set"

        text = (
            f"<b>🖼️ Custom Thumbnail</b>\n\n"
            f"Current Status: {status}\n\n"
            "Upload a custom thumbnail to be embedded in your videos."
        )

        buttons_list = [
            [InlineKeyboardButton("📤 Upload New", callback_data="set_thumbnail_upload")],
            [InlineKeyboardButton("🔙 Back", callback_data="settings")]
        ]

        if thumb_exists:
            buttons_list.insert(0, [
                InlineKeyboardButton("👁️ View Current", callback_data="set_thumbnail_view"),
                InlineKeyboardButton("🗑️ Delete", callback_data="set_thumbnail_delete")
            ])

        buttons = InlineKeyboardMarkup(buttons_list)
        await callback_query.message.edit(text, reply_markup=buttons)

    elif data == "set_thumbnail_view":
        if "thumbnail" not in settings:
            await callback_query.answer("No thumbnail set!", show_alert=True)
            return

        # Save temp file to send
        import io
        thumb_data = settings["thumbnail"]
        f = io.BytesIO(thumb_data)
        f.name = "thumbnail.jpg"

        try:
            await client.send_photo(
                chat_id=user_id,
                photo=f,
                caption="<b>🖼️ Your Current Thumbnail</b>"
            )
            await callback_query.answer()
        except Exception as e:
            log.error(f"Failed to send thumbnail: {e}")
            await callback_query.answer("Failed to send thumbnail.", show_alert=True)

    elif data == "set_thumbnail_delete":
        if "thumbnail" in settings:
            del settings["thumbnail"]
            await update_user_settings(user_id, settings)
            await callback_query.answer("Thumbnail deleted!", show_alert=True)

            # Refresh menu
            # Better to just trigger base menu logic again
            callback_query.data = "set_thumbnail"
            await thumbnail_callback(client, callback_query)
        else:
            await callback_query.answer("No thumbnail to delete!", show_alert=True)

    elif data == "set_thumbnail_upload":
        await callback_query.message.edit(
            "<b>📤 Upload Thumbnail</b>\n\n"
            "Please send me the <b>Photo</b> you want to set as thumbnail.\n"
            "<i>Send /cancel to abort.</i>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]
            )
        )

        # Listen for photo
        try:
            input_msg = await client.listen(user_id, filters=filters.photo, timeout=300)

            # Download photo
            # We want the highest quality photo
            photo = input_msg.photo

            # Download to memory
            file_path = await client.download_media(input_msg, file_name=f"thumbs/{user_id}.jpg")

            if file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    thumb_data = f.read()

                # Save to settings
                settings["thumbnail"] = thumb_data
                await update_user_settings(user_id, settings)

                # Cleanup
                os.remove(file_path)

                await input_msg.reply_text("<b>✅ Thumbnail Saved!</b>")

                # Return to menu
                callback_query.data = "set_thumbnail"
                await thumbnail_callback(client, callback_query)
            else:
                await input_msg.reply_text("❌ Failed to download photo.")

        except asyncio.TimeoutError:
            await callback_query.message.edit("❌ Timeout. Please try again.")
        except Exception as e:
            if "ListenerCanceled" in str(e):
                 await callback_query.message.edit("❌ Cancelled.")
            else:
                log.error(f"Thumbnail upload error: {e}")
                await callback_query.message.edit(f"❌ Error: {e}")


