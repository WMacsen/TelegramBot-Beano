import logging
import os
import json
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ChatMemberStatus

# Assuming features_hashtags is a module with these functions
from features_hashtags import save_hashtag_data, load_hashtag_data

logger = logging.getLogger(__name__)

# --- Constants ---
ADMIN_DATA_FILE = 'admins.json'
ADMIN_NICKNAMES_FILE = 'admin_nicknames.json'
DISABLED_COMMANDS_FILE = 'disabled_commands.json'
OWNER_ID = 7237569475

# --- Data Load/Save ---
def load_admin_data():
    if os.path.exists(ADMIN_DATA_FILE):
        with open(ADMIN_DATA_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
    else: data = {'admins': []}
    data['admins'] = list(set(data.get('admins', []) + [str(OWNER_ID)]))
    data['owner'] = str(OWNER_ID)
    return data

def save_admin_data(data):
    if str(data['owner']) not in data['admins']: data['admins'].append(str(data['owner']))
    with open(ADMIN_DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

def load_admin_nicknames():
    if os.path.exists(ADMIN_NICKNAMES_FILE):
        with open(ADMIN_NICKNAMES_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def save_admin_nicknames(data):
    with open(ADMIN_NICKNAMES_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

def load_disabled_commands():
    if os.path.exists(DISABLED_COMMANDS_FILE):
        with open(DISABLED_COMMANDS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def save_disabled_commands(data):
    with open(DISABLED_COMMANDS_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

# --- Admin Helpers ---
def is_owner(user_id):
    return str(user_id) == str(load_admin_data()['owner'])

def is_admin(user_id):
    data = load_admin_data()
    return str(user_id) in data['admins']

def get_display_name(user_id: int, full_name: str) -> str:
    if not is_admin(user_id): return "fag"
    return load_admin_nicknames().get(str(user_id), full_name)

async def get_user_id_by_username(context: ContextTypes.DEFAULT_TYPE, chat_id: int, username: str) -> str | None:
    try:
        async for member in context.bot.get_chat_administrators(chat_id):
            if member.user.username and member.user.username.lower() == username.lower().lstrip('@'):
                return str(member.user.id)
    except Exception as e:
        logger.error(f"Could not get admins for get_user_id_by_username: {e}")
    return None

# --- Decorator ---
def command_handler_wrapper(admin_only=False):
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user or not update.message: return
            user, chat = update.effective_user, update.effective_chat
            try:
                if chat.type in ['group', 'supergroup']:
                    command_name = func.__name__.replace('_command', '')
                    if command_name in set(load_disabled_commands().get(str(chat.id), [])): return
                if admin_only and not is_admin(user.id):
                    await update.message.reply_text(f"Warning: {user.mention_html()}, you are not authorized.", parse_mode='HTML')
                    return
                await func(update, context, *args, **kwargs)
            finally:
                if chat.type in ['group', 'supergroup'] and not func.__name__ == 'admin_command':
                    try: await context.bot.delete_message(chat.id, update.message.message_id)
                    except Exception: pass
        return wrapper
    return decorator

# --- Command Registration Helper ---
def add_command(app, command: str, handler):
    async def message_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message and update.message.text: context.args = update.message.text.split()[1:]
        await handler(update, context)
    app.add_handler(CommandHandler(command, handler))
    app.add_handler(MessageHandler(filters.Regex(rf'^\.{command}(\s|$)'), message_handler_wrapper))
    app.add_handler(MessageHandler(filters.Regex(rf'^!{command}(\s|$)'), message_handler_wrapper))

# --- Admin & General Commands ---
@command_handler_wrapper(admin_only=True)
async def setnickname_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=True)
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=False)
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=True)
async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=False)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=False)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

async def help_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=False)
async def beowned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=False)
async def command_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed
