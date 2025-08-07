import logging
import os
import json
import re
import asyncio
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

HASHTAG_DATA_FILE = 'hashtag_data.json'

# Data management
def load_hashtag_data():
    if os.path.exists(HASHTAG_DATA_FILE):
        with open(HASHTAG_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_hashtag_data(data):
    with open(HASHTAG_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Media group handling
media_group_cache = {}
flush_tasks = {}

async def flush_media_group(tag, group_id, chat_id, context):
    await asyncio.sleep(2.0)
    cache_key = (tag, group_id)
    if cache_key not in media_group_cache:
        return
    data = load_hashtag_data()
    group_data = media_group_cache[cache_key]
    entry = {**group_data, 'media_group_id': group_id}
    data.setdefault(tag, []).append(entry)
    save_hashtag_data(data)
    del media_group_cache[cache_key]
    del flush_tasks[cache_key]
    await context.bot.send_message(chat_id, f"Saved media group under: #{tag}")

# Handlers
async def hashtag_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    # In a modular approach, user activity should be handled in a more central way,
    # but for this refactoring, we'll assume it's called from where it's needed.
    # We will need to import `update_user_activity` in Main.py and pass it or handle it there.

    text = message.text or message.caption or ''
    hashtags = re.findall(r'#(\w+)', text)
    if not hashtags:
        return

    if message.media_group_id:
        for tag in hashtags:
            tag = tag.lower()
            cache_key = (tag, message.media_group_id)
            group = media_group_cache.setdefault(cache_key, {'user_id': message.from_user.id, 'username': message.from_user.username, 'text': message.text, 'caption': message.caption, 'message_id': message.message_id, 'chat_id': message.chat_id, 'photos': [], 'videos': []})
            if message.photo:
                file_id = message.photo[-1].file_id
                if file_id not in group['photos']: group['photos'].append(file_id)
            if message.video: group['videos'].append(message.video.file_id)
            if message.document and message.document.mime_type and message.document.mime_type.startswith('video'): group['videos'].append(message.document.file_id)
            if cache_key in flush_tasks: flush_tasks[cache_key].cancel()
            flush_tasks[cache_key] = asyncio.create_task(flush_media_group(tag, message.media_group_id, message.chat_id, context))
        return

    data = load_hashtag_data()
    for tag in hashtags:
        tag = tag.lower()
        entry = {'user_id': message.from_user.id, 'username': message.from_user.username, 'text': message.text, 'caption': message.caption, 'message_id': message.message_id, 'chat_id': message.chat_id, 'media_group_id': None, 'photos': [], 'videos': []}
        if message.photo: entry['photos'] = [message.photo[-1].file_id]
        if message.video: entry['videos'] = [message.video.file_id]
        if message.document and message.document.mime_type and message.document.mime_type.startswith('video'): entry['videos'].append(message.document.file_id)
        data.setdefault(tag, []).append(entry)

    save_hashtag_data(data)
    await message.reply_text(f"Saved under: {', '.join('#'+t for t in hashtags)}")

async def dynamic_hashtag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    command = update.message.text[1:].split()[0].lower()

    # The COMMAND_MAP will be passed via context.bot_data in the main file
    if command in context.bot_data.get("COMMAND_MAP", {}):
        return

    data = load_hashtag_data()
    if command not in data:
        await update.message.reply_text(f"No data found for #{command}.")
        return

    found = False
    for entry in data[command]:
        for photo_id in entry.get('photos', []):
            await update.message.reply_photo(photo_id, caption=entry.get('caption') or entry.get('text') or '')
            found = True
        for video_id in entry.get('videos', []):
            await update.message.reply_video(video_id, caption=entry.get('caption') or entry.get('text') or '')
            found = True
        if not entry.get('photos') and not entry.get('videos') and (entry.get('text') or entry.get('caption')):
            await update.message.reply_text(entry.get('text') or entry.get('caption'))
            found = True
    if not found:
        await update.message.reply_text(f"No saved messages or photos for #{command}.")
