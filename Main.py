# =========================
# Imports and Configuration
# =========================
import os
import json
import re
from typing import Final
import uuid
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext, CallbackQueryHandler, ConversationHandler
from telegram.constants import ChatMemberStatus

# Debug: Print all environment variables at startup
print("[DEBUG] Environment variables:", os.environ)

# Load the Telegram bot token from environment variable
TOKEN = os.environ.get('TELEGRAM_TOKEN')
BOT_USERNAME: Final = '@MasterBeanoBot'  # Bot's username (update if needed)

# File paths for persistent data storage
HASHTAG_DATA_FILE = 'hashtag_data.json'  # Stores hashtagged messages/media
ADMIN_DATA_FILE = 'admins.json'          # Stores admin/owner info
OWNER_ID = 7237569475  # Your Telegram ID (change to your actual Telegram user ID)

# =============================
# Admin/Owner Data Management
# =============================
def load_admin_data():
    """Load admin and owner data from file. Ensures owner is always in admin list."""
    if os.path.exists(ADMIN_DATA_FILE):
        with open(ADMIN_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Always ensure owner is in admin list
            if str(OWNER_ID) not in data.get('admins', []):
                data['admins'] = list(set(data.get('admins', []) + [str(OWNER_ID)]))
            data['owner'] = str(OWNER_ID)
            print(f"[DEBUG] Loaded admin data: {data}")
            return data
    # Default: owner is admin
    print("[DEBUG] No admin data file found, using default owner as admin.")
    return {'owner': str(OWNER_ID), 'admins': [str(OWNER_ID)]}

def save_admin_data(data):
    """Save admin and owner data to file. Ensures owner is always in admin list."""
    # Always ensure owner is in admin list
    if str(data['owner']) not in data['admins']:
        data['admins'].append(str(data['owner']))
    with open(ADMIN_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[DEBUG] Saved admin data: {data}")

def is_owner(user_id):
    """Check if the user is the owner."""
    data = load_admin_data()
    result = str(user_id) == str(data['owner'])
    print(f"[DEBUG] is_owner({user_id}) -> {result}")
    return result

def is_admin(user_id):
    """Check if the user is an admin or the owner."""
    data = load_admin_data()
    result = str(user_id) in data['admins'] or str(user_id) == str(data['owner'])
    print(f"[DEBUG] is_admin({user_id}) -> {result}")
    return result

async def get_user_id_by_username(context, chat_id, username) -> str:
    """Get a user's Telegram ID by their username in a chat."""
    async for member in context.bot.get_chat_administrators(chat_id):
        if member.user.username and member.user.username.lower() == username.lower().lstrip('@'):
            print(f"[DEBUG] Found user ID {member.user.id} for username {username}")
            return str(member.user.id)
    print(f"[DEBUG] Username {username} not found in chat {chat_id}")
    return None

# =============================
# Hashtag Data Management
# =============================
def load_hashtag_data():
    """Load hashtagged message/media data from file."""
    if os.path.exists(HASHTAG_DATA_FILE):
        with open(HASHTAG_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"[DEBUG] Loaded hashtag data: {list(data.keys())}")
            return data
    print("[DEBUG] No hashtag data file found, returning empty dict.")
    return {}

def save_hashtag_data(data):
    """Save hashtagged message/media data to file."""
    with open(HASHTAG_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[DEBUG] Saved hashtag data: {list(data.keys())}")

import asyncio
import time

# =============================
# Reward System Storage & Helpers
# =============================
REWARDS_DATA_FILE = 'rewards.json'  # Stores rewards per group

DEFAULT_REWARD = {"name": "Other", "cost": 0}

def load_rewards_data():
    if os.path.exists(REWARDS_DATA_FILE):
        with open(REWARDS_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_rewards_data(data):
    with open(REWARDS_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_rewards_list(group_id):
    data = load_rewards_data()
    group_id = str(group_id)
    rewards = data.get(group_id, [])
    # Always include the default "Other" reward at the end
    if not any(r["name"].lower() == "other" for r in rewards):
        rewards.append(DEFAULT_REWARD)
    return rewards

def add_reward(group_id, name, cost):
    if name.strip().lower() == "other":
        return False
    data = load_rewards_data()
    group_id = str(group_id)
    if group_id not in data:
        data[group_id] = []
    # Prevent duplicates
    for r in data[group_id]:
        if r["name"].lower() == name.strip().lower():
            return False
    data[group_id].append({"name": name.strip(), "cost": int(cost)})
    save_rewards_data(data)
    print(f"[DEBUG] Added reward '{name}' with cost {cost} to group {group_id}")
    return True

def remove_reward(group_id, name):
    if name.strip().lower() == "other":
        return False
    data = load_rewards_data()
    group_id = str(group_id)
    if group_id not in data:
        return False
    before = len(data[group_id])
    data[group_id] = [r for r in data[group_id] if r["name"].lower() != name.strip().lower()]
    after = len(data[group_id])
    save_rewards_data(data)
    print(f"[DEBUG] Removed reward '{name}' from group {group_id}")
    return before != after

# =============================
# Point System Storage & Helpers
# =============================
POINTS_DATA_FILE = 'points.json'  # Stores user points per group

def load_points_data():
    if os.path.exists(POINTS_DATA_FILE):
        with open(POINTS_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_points_data(data):
    with open(POINTS_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_points(group_id, user_id):
    data = load_points_data()
    group_id = str(group_id)
    user_id = str(user_id)
    return data.get(group_id, {}).get(user_id, 0)

def set_user_points(group_id, user_id, points):
    data = load_points_data()
    group_id = str(group_id)
    user_id = str(user_id)
    if group_id not in data:
        data[group_id] = {}
    data[group_id][user_id] = points
    save_points_data(data)
    print(f"[DEBUG] Set points for user {user_id} in group {group_id} to {points}")

async def check_for_punishment(group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    punishments_data = load_punishments_data()
    group_id_str = str(group_id)

    if group_id_str not in punishments_data:
        return

    group_punishments = punishments_data[group_id_str]
    user_points = get_user_points(group_id, user_id)
    triggered_punishments = get_triggered_punishments_for_user(group_id, user_id)

    for punishment in group_punishments:
        threshold = punishment.get("threshold")
        message = punishment.get("message")

        if threshold is None or message is None:
            continue

        if user_points < threshold:
            if message not in triggered_punishments:
                # Punish the user
                user = await context.bot.get_chat_member(group_id, user_id)
                await context.bot.send_message(
                    chat_id=group_id,
                    text=f"🚨 <b>Punishment Issued!</b> 🚨\n{user.user.mention_html()} has fallen below {threshold} points. Punishment: {message}",
                    parse_mode='HTML'
                )

                chat = await context.bot.get_chat(group_id)
                admins = await context.bot.get_chat_administrators(group_id)
                for admin in admins:
                    try:
                        await context.bot.send_message(
                            chat_id=admin.user.id,
                            text=f"User @{user.user.username or user.user.full_name} (ID: {user_id}) in group {chat.title} (ID: {group_id}) triggered punishment '{message}' by falling below {threshold} points."
                        )
                    except Exception as e:
                        print(f"Failed to notify admin {admin.user.id} about punishment: {e}")

                add_triggered_punishment_for_user(group_id, user_id, message)
        else:
            # If user is above threshold, reset their status for this punishment
            if message in triggered_punishments:
                remove_triggered_punishment_for_user(group_id, user_id, message)

async def add_user_points(group_id, user_id, delta, context: ContextTypes.DEFAULT_TYPE):
    points = get_user_points(group_id, user_id) + delta
    set_user_points(group_id, user_id, points)
    print(f"[DEBUG] Added {delta} points for user {user_id} in group {group_id} (new total: {points})")
    await check_for_punishment(group_id, user_id, context)

# =============================
# Game System Storage & Helpers
# =============================
GAMES_DATA_FILE = 'games.json'

def load_games_data():
    if os.path.exists(GAMES_DATA_FILE):
        with open(GAMES_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_games_data(data):
    with open(GAMES_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# =============================
# Punishment System Storage & Helpers
# =============================
PUNISHMENTS_DATA_FILE = 'punishments.json'
PUNISHMENT_STATUS_FILE = 'punishment_status.json'

def load_punishments_data():
    if os.path.exists(PUNISHMENTS_DATA_FILE):
        with open(PUNISHMENTS_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_punishments_data(data):
    with open(PUNISHMENTS_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_punishment_status_data():
    if os.path.exists(PUNISHMENT_STATUS_FILE):
        with open(PUNISHMENT_STATUS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_punishment_status_data(data):
    with open(PUNISHMENT_STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_triggered_punishments_for_user(group_id, user_id) -> list:
    data = load_punishment_status_data()
    group_id = str(group_id)
    user_id = str(user_id)
    return data.get(group_id, {}).get(user_id, [])

def add_triggered_punishment_for_user(group_id, user_id, punishment_message: str):
    data = load_punishment_status_data()
    group_id = str(group_id)
    user_id = str(user_id)
    if group_id not in data:
        data[group_id] = {}
    if user_id not in data[group_id]:
        data[group_id][user_id] = []

    if punishment_message not in data[group_id][user_id]:
        data[group_id][user_id].append(punishment_message)
        save_punishment_status_data(data)
        print(f"[DEBUG] Added triggered punishment '{punishment_message}' for user {user_id} in group {group_id}")

def remove_triggered_punishment_for_user(group_id, user_id, punishment_message: str):
    data = load_punishment_status_data()
    group_id = str(group_id)
    user_id = str(user_id)
    if group_id in data and user_id in data[group_id]:
        if punishment_message in data[group_id][user_id]:
            data[group_id][user_id].remove(punishment_message)
            save_punishment_status_data(data)
            print(f"[DEBUG] Removed triggered punishment '{punishment_message}' for user {user_id} in group {group_id}")

# =============================
# Reward System Commands
# =============================
REWARD_STATE = 'awaiting_reward_choice'
ADDREWARD_STATE = 'awaiting_addreward_name'
ADDREWARD_COST_STATE = 'awaiting_addreward_cost'
REMOVEREWARD_STATE = 'awaiting_removereward_name'
ADDPOINTS_STATE = 'awaiting_addpoints_value'
REMOVEPOINTS_STATE = 'awaiting_removepoints_value'

async def reward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /reward: Show reward list, ask user to choose, handle purchase or 'Other'.
    """
    group_id = str(update.effective_chat.id)
    rewards = get_rewards_list(group_id)
    msg = "<b>Available Rewards:</b>\n"
    for r in rewards:
        msg += f"• <b>{r['name']}</b> — {r['cost']} points\n"
    msg += "\nReply with the name of the reward you want to buy, or type /cancel to abort."
    context.user_data[REWARD_STATE] = {'group_id': group_id}
    await update.message.reply_text(msg, parse_mode='HTML')

async def conversation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles all conversation-based interactions after a command has been issued.
    This acts as a router based on the state stored in context.user_data.
    """
    # Update user activity to prevent being kicked for inactivity during a conversation
    if update.effective_user and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        update_user_activity(update.effective_user.id, update.effective_chat.id)

    # === Add Reward Flow: Step 2 (Cost) ===
    if ADDREWARD_COST_STATE in context.user_data:
        state = context.user_data[ADDREWARD_COST_STATE]
        try:
            cost = int(update.message.text.strip())
            if cost < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Please reply with a valid positive integer for the cost.")
            return
        group_id = state['group_id']
        name = state['name']
        if add_reward(group_id, name, cost):
            await update.message.reply_text(f"Reward '{name}' added with cost {cost} points.")
        else:
            await update.message.reply_text(f"Could not add reward '{name}'. It may already exist or is not allowed.")
        context.user_data.pop(ADDREWARD_COST_STATE, None)
        return

    # === Add Reward Flow: Step 1 (Name) ===
    if ADDREWARD_STATE in context.user_data:
        state = context.user_data[ADDREWARD_STATE]
        name = update.message.text.strip()
        if name.lower() == "other":
            await update.message.reply_text("You cannot add the reward 'Other'.")
            context.user_data.pop(ADDREWARD_STATE, None)
            return
        state['name'] = name
        context.user_data[ADDREWARD_COST_STATE] = state
        context.user_data.pop(ADDREWARD_STATE, None)
        await update.message.reply_text(f"What is the cost (in points) for the reward '{name}'?")
        return

    # === Remove Reward Flow ===
    if REMOVEREWARD_STATE in context.user_data:
        state = context.user_data[REMOVEREWARD_STATE]
        name = update.message.text.strip()
        if name.lower() == "other":
            await update.message.reply_text("You cannot remove the reward 'Other'.")
            context.user_data.pop(REMOVEREWARD_STATE, None)
            return
        group_id = state['group_id']
        if remove_reward(group_id, name):
            await update.message.reply_text(f"Reward '{name}' removed.")
        else:
            await update.message.reply_text(f"Could not remove reward '{name}'. It may not exist or is not allowed.")
        context.user_data.pop(REMOVEREWARD_STATE, None)
        return

    # === User Reward Choice Flow ===
    if REWARD_STATE in context.user_data:
        state = context.user_data[REWARD_STATE]
        group_id = state['group_id']
        user_id = update.effective_user.id
        choice = update.message.text.strip()
        rewards = get_rewards_list(group_id)
        reward = next((r for r in rewards if r['name'].lower() == choice.lower()), None)
        if not reward:
            await update.message.reply_text("That reward does not exist. Please reply with a valid reward name or type /cancel.")
            return
        if reward['name'].lower() == 'other':
            await update.message.reply_text("Communicate with either your owner or the beta to discuss what you want your reward to be and what it would cost you.")
            admins = await context.bot.get_chat_administrators(update.effective_chat.id)
            for admin in admins:
                try:
                    await context.bot.send_message(
                        chat_id=admin.user.id,
                        text=f"User @{update.effective_user.username or ''} (ID: {user_id}) selected the reward 'Other'. Instruct them to discuss their reward and cost with you.",
                    )
                except Exception:
                    pass
            context.user_data.pop(REWARD_STATE, None)
            return
        user_points = get_user_points(group_id, user_id)
        if user_points < reward['cost']:
            await update.message.reply_text(f"You do not have enough points for this reward. You have {user_points}, but it costs {reward['cost']}.")
            context.user_data.pop(REWARD_STATE, None)
            return
        await add_user_points(group_id, user_id, -reward['cost'], context)

        # Public announcement
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🎁 <b>{update.effective_user.full_name}</b> just bought the reward: <b>{reward['name']}</b>! 🎉",
            parse_mode='HTML'
        )

        # Private message to admins
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        for admin in admins:
            try:
                await context.bot.send_message(
                    chat_id=admin.user.id,
                    text=f"User @{update.effective_user.username or update.effective_user.full_name} (ID: {user_id}) in group {update.effective_chat.title} (ID: {group_id}) just bought the reward: '{reward['name']}' for {reward['cost']} points."
                )
            except Exception as e:
                print(f"Failed to notify admin {admin.user.id} about reward purchase: {e}")

        context.user_data.pop(REWARD_STATE, None)
        return

    # === Add/Remove Points Flow ===
    if ADDPOINTS_STATE in context.user_data:
        state = context.user_data[ADDPOINTS_STATE]
        try:
            value = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Please reply with a valid integer number of points to add.")
            return
        await add_user_points(state['group_id'], state['target_id'], value, context)
        await update.message.reply_text(f"Added {value} points.")
        context.user_data.pop(ADDPOINTS_STATE, None)
        return

    if REMOVEPOINTS_STATE in context.user_data:
        state = context.user_data[REMOVEPOINTS_STATE]
        try:
            value = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Please reply with a valid integer number of points to remove.")
            return
        await add_user_points(state['group_id'], state['target_id'], -value, context)
        await update.message.reply_text(f"Removed {value} points.")
        context.user_data.pop(REMOVEPOINTS_STATE, None)
        return

    # === Admin Help Flow ===
    if ADMIN_HELP_STATE in context.user_data:
        if update.effective_chat.type == "private":
            await update.message.reply_text("This command can only be used in group chats.")
            return
        message = update.message
        if not message:
            return
        reason = message.text
        help_data = context.user_data.get('admin_help', {})
        help_data['reason'] = reason
        user = message.from_user
        chat = message.chat
        replied_message = help_data.get('replied_message')
        help_text = f"🚨 <b>Admin Help Request</b> 🚨\n" \
                    f"<b>User:</b> {user.mention_html()} (ID: {user.id})\n" \
                    f"<b>Group:</b> {getattr(chat, 'title', chat.id)} (ID: {chat.id})\n" \
                    f"<b>Reason:</b> {reason}\n"
        if replied_message:
            rep_user = replied_message.get('from', {})
            rep_text = replied_message.get('text', '') or replied_message.get('caption', '')
            has_photo = 'photo' in replied_message and replied_message['photo']
            has_video = 'video' in replied_message and replied_message['video']
            has_voice = 'voice' in replied_message and replied_message['voice']
            if has_photo and not rep_text and not has_video and not has_voice:
                help_text += f"<b>Replied to:</b> [media: image only]\n"
            elif has_video and not rep_text and not has_photo and not has_voice:
                help_text += f"<b>Replied to:</b> [media: video only]\n"
            elif has_voice and not rep_text and not has_photo and not has_video:
                help_text += f"<b>Replied to:</b> [media: voice note only]\n"
            else:
                help_text += f"<b>Replied to:</b> {rep_user.get('username', 'Unknown')} (ID: {rep_user.get('id', 'N/A')})\n"
                if rep_text:
                    help_text += f"<b>Message:</b> {rep_text}\n"
        admins = await context.bot.get_chat_administrators(chat.id)
        for admin in admins:
            try:
                await context.bot.send_message(
                    chat_id=admin.user.id,
                    text=help_text,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                if replied_message:
                    if 'photo' in replied_message and replied_message['photo']:
                        file_id = replied_message['photo'][-1]['file_id']
                        await context.bot.send_photo(chat_id=admin.user.id, photo=file_id, caption="[Forwarded from help request]")
                    if 'video' in replied_message and replied_message['video']:
                        file_id = replied_message['video']['file_id']
                        await context.bot.send_video(chat_id=admin.user.id, video=file_id, caption="[Forwarded from help request]")
                    if 'voice' in replied_message and replied_message['voice']:
                        file_id = replied_message['voice']['file_id']
                        await context.bot.send_voice(chat_id=admin.user.id, voice=file_id, caption="[Forwarded from help request]")
            except Exception as e:
                print(f"Failed to notify admin {admin.user.id}: {e}")
        await message.reply_text("Your help request has been sent to all group admins.")
        context.user_data.pop(ADMIN_HELP_STATE, None)
        context.user_data.pop('admin_help', None)
        return

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cancel: Cancel any pending reward selection.
    """
    if REWARD_STATE in context.user_data:
        context.user_data.pop(REWARD_STATE, None)
        await update.message.reply_text("Reward selection cancelled.")
    else:
        await update.message.reply_text("No reward selection in progress.")

async def addreward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addreward (admin only): Start add reward process
    """
    if update.effective_chat.type == "private":
        await update.message.reply_text("This command can only be used in group chats.")
        return
    user = update.effective_user
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin_user = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    if not is_admin_user:
        await update.message.reply_text("Only admins can use this command.")
        return
    context.user_data[ADDREWARD_STATE] = {'group_id': str(update.effective_chat.id)}
    await update.message.reply_text("What is the name of the reward you want to add?")

async def addpunishment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addpunishment <threshold> <message> (admin only): Adds a new punishment.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
        return

    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await update.message.reply_text("Only admins can use this command.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addpunishment <threshold> <message>")
        return

    try:
        threshold = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Threshold must be a number.")
        return

    message = " ".join(context.args[1:])
    group_id = str(update.effective_chat.id)
    punishments_data = load_punishments_data()

    if group_id not in punishments_data:
        punishments_data[group_id] = []

    # Check for duplicates
    for p in punishments_data[group_id]:
        if p["message"].lower() == message.lower():
            await update.message.reply_text("A punishment with this message already exists.")
            return

    punishments_data[group_id].append({"threshold": threshold, "message": message})
    save_punishments_data(punishments_data)

    await update.message.reply_text(f"Punishment added: '{message}' at {threshold} points.")

async def removepunishment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /removepunishment <message> (admin only): Removes a punishment.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
        return

    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await update.message.reply_text("Only admins can use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removepunishment <message>")
        return

    message_to_remove = " ".join(context.args)
    group_id = str(update.effective_chat.id)
    punishments_data = load_punishments_data()

    if group_id not in punishments_data:
        await update.message.reply_text("No punishments found for this group.")
        return

    initial_len = len(punishments_data[group_id])
    punishments_data[group_id] = [p for p in punishments_data[group_id] if p["message"].lower() != message_to_remove.lower()]

    if len(punishments_data[group_id]) == initial_len:
        await update.message.reply_text("Punishment not found.")
    else:
        save_punishments_data(punishments_data)
        await update.message.reply_text("Punishment removed.")

async def newgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /newgame (group only): Starts the process of setting up a new game.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
        return

    user = update.effective_user
    game_id = str(uuid.uuid4())
    games_data = load_games_data()

    games_data[game_id] = {
        "group_id": update.effective_chat.id,
        "challenger_id": user.id,
        "opponent_id": None,
        "game_type": None,
        "challenger_stake": None,
        "opponent_stake": None,
        "status": "pending_game_selection"
    }
    save_games_data(games_data)

    # Public message
    await update.message.reply_text(f"{user.mention_html()}, please check your private messages to set up the game.", parse_mode='HTML')

    # Private message with button
    try:
        keyboard = [[InlineKeyboardButton("Start Game Setup", callback_data=f"start_game_setup_{game_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=user.id,
            text="Let's set up your game! Click the button below to begin.",
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Failed to send private message to user {user.id}: {e}")
        await update.message.reply_text("I couldn't send you a private message. Please make sure you have started a chat with me privately first.")

async def loser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /loser <user> (admin only): Enacts the loser condition for the specified user.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
        return

    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await update.message.reply_text("Only admins can use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /loser <@username or user_id>")
        return

    loser_username = context.args[0]
    loser_id = await get_user_id_by_username(context, update.effective_chat.id, loser_username)
    if not loser_id:
        try:
            loser_id = int(loser_username)
        except ValueError:
            await update.message.reply_text(f"Could not find user {loser_username}.")
            return

    games_data = load_games_data()

    latest_game_id = None
    for game_id, game in games_data.items():
        if str(game.get('group_id')) == str(update.effective_chat.id) and \
           game.get('status') == 'active' and \
           (str(game.get('challenger_id')) == str(loser_id) or str(game.get('opponent_id')) == str(loser_id)):
            latest_game_id = game_id

    if not latest_game_id:
        await update.message.reply_text(f"No active game found for user {loser_username}.")
        return

    game = games_data[latest_game_id]

    if str(game['challenger_id']) == str(loser_id):
        winner_id = game['opponent_id']
        loser_stake = game['challenger_stake']
    else:
        winner_id = game['challenger_id']
        loser_stake = game['opponent_stake']

    if loser_stake['type'] == 'points':
        await add_user_points(game['group_id'], winner_id, loser_stake['value'], context)
        await add_user_points(game['group_id'], loser_id, -loser_stake['value'], context)
        await context.bot.send_message(game['group_id'], f"The loser has paid their stake of {loser_stake['value']} points to the winner.")
    else:
        caption = "The loser's stake has been exposed!"
        if loser_stake['type'] == 'photo':
            await context.bot.send_photo(game['group_id'], loser_stake['value'], caption=caption)
        elif loser_stake['type'] == 'video':
            await context.bot.send_video(game['group_id'], loser_stake['value'], caption=caption)
        elif loser_stake['type'] == 'voice':
            await context.bot.send_voice(game['group_id'], loser_stake['value'], caption=caption)

    game['status'] = 'complete'
    save_games_data(games_data)

async def cleangames_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cleangames (admin only): Clears out completed or stale game data.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
        return

    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await update.message.reply_text("Only admins can use this command.")
        return

    games_data = load_games_data()
    games_to_keep = {
        game_id: game for game_id, game in games_data.items()
        if game.get('status') != 'complete'
    }

    if len(games_to_keep) == len(games_data):
        await update.message.reply_text("No completed games to clean up.")
    else:
        save_games_data(games_to_keep)
        await update.message.reply_text("Cleaned up completed games.")

async def punishment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /punishment (admin only): Lists all punishments for the group.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
        return

    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await update.message.reply_text("Only admins can use this command.")
        return

    group_id = str(update.effective_chat.id)
    punishments_data = load_punishments_data()
    group_punishments = punishments_data.get(group_id, [])

    if not group_punishments:
        await update.message.reply_text("No punishments have been set for this group.")
        return

    msg = "<b>Configured Punishments:</b>\n"
    for p in sorted(group_punishments, key=lambda x: x['threshold'], reverse=True):
        msg += f"• Below <b>{p['threshold']}</b> points: <i>{p['message']}</i>\n"

    await update.message.reply_text(msg, parse_mode='HTML')

async def removereward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /removereward (admin only): Start remove reward process
    """
    user = update.effective_user
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin_user = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    if not is_admin_user:
        await update.message.reply_text("Only admins can use this command.")
        return
    context.user_data[REMOVEREWARD_STATE] = {'group_id': str(update.effective_chat.id)}
    await update.message.reply_text("What is the name of the reward you want to remove?")

async def addpoints_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addpoints <username|id> (admin only): Start add points process
    """
    group_id = str(update.effective_chat.id)
    user = update.effective_user
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin_user = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    if not is_admin_user:
        await update.message.reply_text("Only admins can use this command.")
        return
    # If used as a reply, use the replied-to user's ID
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    else:
        if not context.args:
            await update.message.reply_text("Usage: /addpoints <username|id> or reply to a user's message.")
            return
        arg = context.args[0].strip()
        # Try to resolve by ID
        target_id = None
        if arg.isdigit():
            target_id = int(arg)
        else:
            target_id = await get_user_id_by_username(context, update.effective_chat.id, arg)
            # get_chat_member with username will not work unless it's a numeric ID
    if not target_id:
        await update.message.reply_text(f"Could not resolve user. Please reply to a user's message or provide a valid user ID.")
        return
    context.user_data[ADDPOINTS_STATE] = {'group_id': group_id, 'target_id': target_id}
    await update.message.reply_text(f"How many points do you want to add to this user?")

async def removepoints_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /removepoints <username|id> (admin only): Start remove points process
    """
    group_id = str(update.effective_chat.id)
    user = update.effective_user
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin_user = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    if not is_admin_user:
        await update.message.reply_text("Only admins can use this command.")
        return
    # If used as a reply, use the replied-to user's ID
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    else:
        if not context.args:
            await update.message.reply_text("Usage: /removepoints <username|id> or reply to a user's message.")
            return
        arg = context.args[0].strip()
        # Try to resolve by ID
        target_id = None
        if arg.isdigit():
            target_id = int(arg)
        else:
            target_id = await get_user_id_by_username(context, update.effective_chat.id, arg)
            # get_chat_member with username will not work unless it's a numeric ID
    if not target_id:
        await update.message.reply_text(f"Could not resolve user. Please reply to a user's message or provide a valid user ID.")
        return
    context.user_data[REMOVEPOINTS_STATE] = {'group_id': group_id, 'target_id': target_id}
    await update.message.reply_text(f"How many points do you want to remove from this user?")

async def point_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /point (user: see own points, admin: see own or another's points)
    """
    group_id = str(update.effective_chat.id)
    user = update.effective_user
    is_admin_user = False
    if update.effective_chat.type in ["group", "supergroup"]:
        member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
        is_admin_user = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    # If used as a reply, show replied-to user's points
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
        points = get_user_points(group_id, target_id)
        await update.message.reply_text(f"User {update.message.reply_to_message.from_user.full_name} has {points} points.")
        return
    # If no argument, show own points
    if not context.args:
        points = get_user_points(group_id, user.id)
        await update.message.reply_text(f"You have {points} points.")
        return
    # If argument, only allow admin to check others
    if not is_admin_user:
        await update.message.reply_text("You can only check your own points.")
        return
    arg = context.args[0].strip()
    # Try to resolve by ID
    target_id = None
    if arg.isdigit():
        target_id = int(arg)
    else:
        target_id = await get_user_id_by_username(context, update.effective_chat.id, arg)
        # get_chat_member with username will not work unless it's a numeric ID
    if not target_id:
        await update.message.reply_text(f"Could not resolve user '{arg}'. Please reply to a user's message or provide a valid user ID.")
        return
    points = get_user_points(group_id, target_id)
    await update.message.reply_text(f"User {arg} has {points} points.")

async def top5_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /top5 (admin only): Show top 5 users by points in the group
    """
    group_id = str(update.effective_chat.id)
    user = update.effective_user
    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    is_admin_user = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    if not is_admin_user:
        await update.message.reply_text("Only admins can use this command.")
        return
    data = load_points_data().get(group_id, {})
    if not data:
        await update.message.reply_text("No points data for this group yet.")
        return
    # Sort by points descending
    top5 = sorted(data.items(), key=lambda x: x[1], reverse=True)[:5]
    # Fetch usernames if possible
    lines = ["🎉 <b>Top 5 Point Leaders!</b> 🎉\n"]
    for idx, (uid, pts) in enumerate(top5, 1):
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, int(uid))
            name = member.user.full_name
            uname = f" (@{member.user.username})" if member.user.username else ""
        except Exception:
            name = f"User {uid}"
            uname = ""
        lines.append(f"<b>{idx}.</b> <i>{name}{uname}</i> — <b>{pts} points</b> {'🏆' if idx==1 else ''}")
    msg = '\n'.join(lines)
    await update.message.reply_text(msg, parse_mode='HTML')

# =============================
# Inactivity Tracking & Settings
# =============================
ACTIVITY_DATA_FILE = 'activity.json'  # Tracks last activity per user per group
INACTIVE_SETTINGS_FILE = 'inactive_settings.json'  # Stores inactivity threshold per group

def load_activity_data():
    if os.path.exists(ACTIVITY_DATA_FILE):
        with open(ACTIVITY_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_activity_data(data):
    with open(ACTIVITY_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_inactive_settings():
    if os.path.exists(INACTIVE_SETTINGS_FILE):
        with open(INACTIVE_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_inactive_settings(data):
    with open(INACTIVE_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_user_activity(user_id, group_id):
    data = load_activity_data()
    group_id = str(group_id)
    user_id = str(user_id)
    if group_id not in data:
        data[group_id] = {}
    data[group_id][user_id] = int(time.time())
    save_activity_data(data)
    print(f"[DEBUG] Updated activity for user {user_id} in group {group_id}")

# =============================
# Hashtag Message Handler
# =============================
async def hashtag_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles messages containing hashtags, saving them (and any media) for later retrieval.
    Supports both single messages and media groups.
    Also updates user activity for inactivity tracking.
    """
    message = update.message
    if not message:
        print("[DEBUG] No message found in update for hashtag handler.")
        return
    # Update user activity for inactivity tracking
    if message.chat and message.from_user and message.chat.type in ["group", "supergroup"]:
        update_user_activity(message.from_user.id, message.chat.id)
    text = message.text or message.caption or ''
    hashtags = re.findall(r'#(\w+)', text)
    if not hashtags:
        print("[DEBUG] No hashtags found in message.")
        return
    # Handle media groups (multiple media sent together)
    if message.media_group_id:
        for tag in hashtags:
            tag = tag.lower()
            cache_key = (tag, message.media_group_id)
            group = media_group_cache.setdefault(cache_key, {
                'user_id': message.from_user.id,
                'username': message.from_user.username,
                'text': message.text if message.text else None,
                'caption': message.caption if message.caption else None,
                'message_id': message.message_id,
                'chat_id': message.chat_id,
                'photos': [],
                'videos': []
            })
            # Add only the last photo (highest resolution) and avoid duplicates
            if message.photo:
                file_id = message.photo[-1].file_id
                if file_id not in group['photos']:
                    group['photos'].append(file_id)
            # Add video
            if message.video:
                group['videos'].append(message.video.file_id)
            # Add document if it's a video
            if message.document and message.document.mime_type and message.document.mime_type.startswith('video'):
                group['videos'].append(message.document.file_id)
            # Cancel and reschedule flush timer
            if cache_key in flush_tasks:
                flush_tasks[cache_key].cancel()
            flush_tasks[cache_key] = asyncio.create_task(flush_media_group(tag, message.media_group_id, message.chat_id, context))
            print(f"[DEBUG] Scheduled flush for media group {cache_key}")
        # Do not send reply here; reply will be sent after flush
        return
    # Handle single media or text
    data = load_hashtag_data()
    for tag in hashtags:
        tag = tag.lower()
        entry = {
            'user_id': message.from_user.id,
            'username': message.from_user.username,
            'text': message.text if message.text else None,
            'caption': message.caption if message.caption else None,
            'message_id': message.message_id,
            'chat_id': message.chat_id,
            'media_group_id': None,
            'photos': [],
            'videos': []
        }
        if message.photo:
            entry['photos'] = [message.photo[-1].file_id]
        if message.video:
            entry['videos'] = [message.video.file_id]
        if message.document and message.document.mime_type and message.document.mime_type.startswith('video'):
            entry['videos'].append(message.document.file_id)
        data.setdefault(tag, []).append(entry)
        print(f"[DEBUG] Saved single message under tag #{tag}")
    save_hashtag_data(data)
    await message.reply_text(f"Saved under: {', '.join('#'+t for t in hashtags)}")

# =============================
# Dynamic Hashtag Command Handler
# =============================
async def dynamic_hashtag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles dynamic hashtag commands (e.g. /mytag) to retrieve saved messages/media.
    Also updates user activity for inactivity tracking.
    """
    if update.effective_chat.type == "private":
        await update.message.reply_text("This command can only be used in group chats.")
        return
    # Update user activity for inactivity tracking
    if update.effective_user and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        update_user_activity(update.effective_user.id, update.effective_chat.id)
    print("[DEBUG] dynamic_hashtag_command called")
    if not update.message or not update.message.text:
        print("[DEBUG] No message or text in dynamic_hashtag_command.")
        return
    command = update.message.text[1:].split()[0].lower()  # Remove leading /

    # Prevent this handler from hijacking static commands
    static_commands = [
        'start', 'help', 'beowned', 'command', 'remove', 'admin', 'inactive',
        'addreward', 'removereward', 'reward', 'cancel', 'addpoints', 'removepoints',
        'point', 'top5', 'addpunishment', 'removepunishment', 'punishment', 'newgame',
        'loser', 'cleangames'
    ]
    if command in static_commands:
        return

    data = load_hashtag_data()
    if command not in data:
        await update.message.reply_text(f"No data found for #{command}.")
        print(f"[DEBUG] No data found for command: {command}")
        return
    # No admin check: allow all users to use hashtag commands
    found = False
    for entry in data[command]:
        # Send all photos
        for photo_id in entry.get('photos', []):
            await update.message.reply_photo(photo_id, caption=entry.get('caption') or entry.get('text') or '')
            found = True
        # Send all videos
        for video_id in entry.get('videos', []):
            await update.message.reply_video(video_id, caption=entry.get('caption') or entry.get('text') or '')
            found = True
        # Fallback for text/caption only
        if not entry.get('photos') and not entry.get('videos') and (entry.get('text') or entry.get('caption')):
            await update.message.reply_text(entry.get('text') or entry.get('caption'))
            found = True
    if not found:
        await update.message.reply_text(f"No saved messages or photos for #{command}.")
        print(f"[DEBUG] No saved messages or media for command: {command}")

# =============================
# /command - List all commands
# =============================
async def command_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Lists all available commands, showing which are admin-only and which are disabled.
    Also updates user activity for inactivity tracking.
    """
    if update.effective_chat.type == "private":
        await update.message.reply_text("This command can only be used in group chats.")
        return
    # Update user activity for inactivity tracking
    if update.effective_user and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        update_user_activity(update.effective_user.id, update.effective_chat.id)
    # Define static commands and their admin status
    static_commands = [
        ('/start', False),
        ('/help', False),
        ('/beowned', False),
        ('/command', False),
        ('/remove', True),
        ('/admin', False),
        ('/inactive', True),
    ]
    group_id = str(update.effective_chat.id)
    disabled = load_disabled_commands()
    disabled_cmds = set(disabled.get(group_id, []))
    print(f"[DEBUG] Disabled commands for group {group_id}: {disabled_cmds}")
    # Only show /start and /help in private chat, not in group
    if update.effective_chat.type == "private":
        everyone_cmds = [cmd for cmd, is_admin in static_commands if not is_admin and cmd.lstrip('/') not in disabled_cmds]
        msg = (
            '<b>Commands for everyone:</b>\n' + ('\n'.join(everyone_cmds) if everyone_cmds else 'None')
        )
        await update.message.reply_text(msg, parse_mode='HTML')
        return
    else:
        everyone_cmds = [cmd for cmd, is_admin in static_commands if not is_admin and cmd.lstrip('/') not in disabled_cmds and cmd not in ['/start', '/help']]
    # Check if user is admin in the group
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    is_admin_user = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    admin_only_cmds = [cmd for cmd, is_admin in static_commands if is_admin and cmd.lstrip('/') not in disabled_cmds]
    # Load hashtag commands (admin only)
    data = load_hashtag_data()
    hashtag_cmds = [f'/{tag}' for tag in data.keys()]
    admin_only_cmds += hashtag_cmds
    msg = '<b>Commands for everyone:</b>\n' + ('\n'.join(everyone_cmds) if everyone_cmds else 'None')
    if is_admin_user:
        msg += '\n\n<b>Commands for admins only:</b>\n' + ('\n'.join(admin_only_cmds) if admin_only_cmds else 'None')
    await update.message.reply_text(msg, parse_mode='HTML')
    print(f"[DEBUG] Sent command list to user {update.effective_user.id}")

# Persistent storage for disabled commands per group
DISABLED_COMMANDS_FILE = 'disabled_commands.json'

def load_disabled_commands():
    if os.path.exists(DISABLED_COMMANDS_FILE):
        with open(DISABLED_COMMANDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_disabled_commands(data):
    with open(DISABLED_COMMANDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# /remove - Remove a dynamic hashtag command or disable a static command (admin only)
async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Update user activity for inactivity tracking
    if update.effective_user and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        update_user_activity(update.effective_user.id, update.effective_chat.id)
    if update.effective_chat.type == "private":
        await update.message.reply_text("This command can only be used in group chats.")
        return
    if not update.message or not context.args:
        await update.message.reply_text("Usage: /remove <command or hashtag>")
        return
    tag = context.args[0].lstrip('#/').lower()
    data = load_hashtag_data()
    # Check admin status in the group via Telegram
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await update.message.reply_text("Only admins can use this command.")
        return
    # Dynamic command removal
    if tag in data:
        del data[tag]
        save_hashtag_data(data)
        await update.message.reply_text(f"Removed dynamic command: /{tag}")
        return
    # Static command disabling
    static_commands = ['start', 'help', 'beowned', 'command', 'admin']
    if tag in static_commands:
        group_id = str(update.effective_chat.id)
        disabled = load_disabled_commands()
        disabled.setdefault(group_id, set())
        # Convert to list for JSON
        disabled[group_id] = list(set(disabled.get(group_id, [])) | {tag})
        save_disabled_commands(disabled)
        await update.message.reply_text(f"Command /{tag} has been disabled in this group. Admins can re-enable it with /enable {tag}.")
        return
    await update.message.reply_text(f"No such dynamic or static command: /{tag}")

# Admin help request conversation state
ADMIN_HELP_STATE = 'awaiting_admin_help_reason'

# /admin command implementation
# Any user in a group chat can use this command to request help from group admins. Only admins will receive the notification.
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Update user activity for inactivity tracking
    if update.effective_user and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        update_user_activity(update.effective_user.id, update.effective_chat.id)
    if update.effective_chat.type == "private":
        await update.message.reply_text("This command can only be used in group chats.")
        return
    # Check if disabled in this group
    group_id = str(update.effective_chat.id)
    disabled = load_disabled_commands()
    if 'admin' in disabled.get(group_id, []):
        return
    message = update.message
    if not message:
        return
    # Record initial info
    user = message.from_user
    chat = message.chat
    replied_message = message.reply_to_message
    context.user_data['admin_help'] = {
        'user_id': user.id,
        'username': user.username,
        'chat_id': chat.id,
        'chat_title': getattr(chat, 'title', None),
        'replied_message': replied_message.to_dict() if replied_message else None,
        'reason': None
    }
    await message.reply_text("Please describe the reason you need admin help. Your request will be sent to all group admins.")
    context.user_data[ADMIN_HELP_STATE] = True

#Start command
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith('setstake_'):
        return  # This is handled by the game setup conversation handler

    # Update user activity for inactivity tracking
    if update.effective_user and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        update_user_activity(update.effective_user.id, update.effective_chat.id)
    if update.effective_chat.type != "private":
        await update.message.reply_text("Please message me in private to use /start.")
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text='Hey there fag! What can I help you with?'
            )
        except Exception:
            pass
        return
    # Check if disabled in this group (should never trigger in private)
    group_id = str(update.effective_chat.id)
    disabled = load_disabled_commands()
    if 'start' in disabled.get(group_id, []):
        return
    await update.message.reply_text('Hey there fag! What can I help you with?')

#Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Update user activity for inactivity tracking
    if update.effective_user and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        update_user_activity(update.effective_user.id, update.effective_chat.id)
    if update.effective_chat.type != "private":
        await update.message.reply_text("Please message me in private to use /help.")
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text='I exist to keep you fags in line! If you have issues in one of our groups contact @Lionspridechatbot or use the @admin function directly in our groups.'
            )
        except Exception:
            pass
        return
    # Check if disabled in this group (should never trigger in private)
    group_id = str(update.effective_chat.id)
    disabled = load_disabled_commands()
    if 'help' in disabled.get(group_id, []):
        return
    await update.message.reply_text('I exist to keep you fags in line!'
                                    ' '
                                    'If you have issues in one of our groups contact @Lionspridechatbot or use the @admin function directly in our groups.')

#BeOwned command
async def beowned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Update user activity for inactivity tracking
    if update.effective_user and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        update_user_activity(update.effective_user.id, update.effective_chat.id)
    # Check if disabled in this group
    if update.effective_chat.type != "private":
        group_id = str(update.effective_chat.id)
        disabled = load_disabled_commands()
        if 'beowned' in disabled.get(group_id, []):
            return
    await update.message.reply_text(
        "If you want to be Lion's property, contact @Lionspridechatbot with a head to toe nude picture of yourself and a clear, concise and complete presentation of yourself.")

#Responses
def handle_response(text: str) -> str:
    processed: str = text.lower()
    if 'dog' in processed:
        return 'Is @Luke082 here? Someone should use his command (/luke8)!'

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Update user activity for inactivity tracking
    if update.message and update.message.from_user and update.message.chat and update.message.chat.type in ["group", "supergroup"]:
        update_user_activity(update.message.from_user.id, update.message.chat.id)
    if update.message and update.message.text:
        response = handle_response(update.message.text)
        if response:
            await update.message.reply_text(response)

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')

# =============================
# Game Setup Conversation
# =============================
GAME_SELECTION, STAKE_TYPE_SELECTION, STAKE_SUBMISSION_POINTS, STAKE_SUBMISSION_MEDIA, OPPONENT_SELECTION, CONFIRMATION = range(6)

async def start_game_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the game setup conversation."""
    query = update.callback_query
    await query.answer()
    game_id = query.data.split('_')[-1]
    context.user_data['game_id'] = game_id

    keyboard = [
        [InlineKeyboardButton("Game A", callback_data='game_A')],
        [InlineKeyboardButton("Game B", callback_data='game_B')],
        [InlineKeyboardButton("Game C", callback_data='game_C')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text="Please select the game you want to play:",
        reply_markup=reply_markup
    )
    return GAME_SELECTION

async def game_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the game selection and asks for the stake type."""
    query = update.callback_query
    await query.answer()
    game_type = query.data

    game_id = context.user_data['game_id']
    games_data = load_games_data()
    games_data[game_id]['game_type'] = game_type
    save_games_data(games_data)

    keyboard = [
        [InlineKeyboardButton("Points", callback_data='stake_points')],
        [InlineKeyboardButton("Media (Photo, Video, Voice Note)", callback_data='stake_media')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text="What would you like to stake?",
        reply_markup=reply_markup
    )
    return STAKE_TYPE_SELECTION

async def stake_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the stake type selection."""
    query = update.callback_query
    await query.answer()
    stake_type = query.data

    if stake_type == 'stake_points':
        await query.edit_message_text(text="How many points would you like to stake?")
        return STAKE_SUBMISSION_POINTS
    elif stake_type == 'stake_media':
        await query.edit_message_text(text="Please send the media file you would like to stake (photo, video, or voice note).")
        return STAKE_SUBMISSION_MEDIA

async def stake_submission_points(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the submission of points as a stake."""
    try:
        points = int(update.message.text)
        user_id = update.effective_user.id
        game_id = context.user_data['game_id']
        games_data = load_games_data()
        group_id = games_data[game_id]['group_id']

        user_points = get_user_points(group_id, user_id)
        if user_points < points:
            await update.message.reply_text(f"You don't have enough points. You have {user_points}, but you tried to stake {points}. Please enter a valid amount.")
            return STAKE_SUBMISSION_POINTS

        if context.user_data.get('player_role') == 'opponent':
            games_data[game_id]['opponent_stake'] = {"type": "points", "value": points}
        else:
            games_data[game_id]['challenger_stake'] = {"type": "points", "value": points}
        save_games_data(games_data)

        if context.user_data.get('player_role') == 'opponent':
            games_data[game_id]['status'] = 'active'
            save_games_data(games_data)
            game = games_data[game_id]
            challenger = await context.bot.get_chat_member(game['group_id'], game['challenger_id'])
            opponent = await context.bot.get_chat_member(game['group_id'], game['opponent_id'])
            await context.bot.send_message(
                chat_id=game['group_id'],
                text=f"The game between {challenger.user.mention_html()} and {opponent.user.mention_html()} is on!",
                parse_mode='HTML'
            )
            return ConversationHandler.END
        else:
            await update.message.reply_text("Who would you like to challenge? Please provide their @username.")
            return OPPONENT_SELECTION

    except ValueError:
        await update.message.reply_text("Please enter a valid number of points.")
        return STAKE_SUBMISSION_POINTS

async def stake_submission_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the submission of media as a stake."""
    message = update.message
    file_id = None
    media_type = None

    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.video:
        file_id = message.video.file_id
        media_type = 'video'
    elif message.voice:
        file_id = message.voice.file_id
        media_type = 'voice'
    else:
        await update.message.reply_text("That is not a valid media file. Please send a photo, video, or voice note.")
        return STAKE_SUBMISSION_MEDIA

    game_id = context.user_data['game_id']
    games_data = load_games_data()

    if context.user_data.get('player_role') == 'opponent':
        games_data[game_id]['opponent_stake'] = {"type": media_type, "value": file_id}
    else:
        games_data[game_id]['challenger_stake'] = {"type": media_type, "value": file_id}
    save_games_data(games_data)

    if context.user_data.get('player_role') == 'opponent':
        games_data[game_id]['status'] = 'active'
        save_games_data(games_data)
        game = games_data[game_id]
        challenger = await context.bot.get_chat_member(game['group_id'], game['challenger_id'])
        opponent = await context.bot.get_chat_member(game['group_id'], game['opponent_id'])
        await context.bot.send_message(
            chat_id=game['group_id'],
            text=f"The game between {challenger.user.mention_html()} and {opponent.user.mention_html()} is on!",
            parse_mode='HTML'
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("Who would you like to challenge? Please provide their @username.")
        return OPPONENT_SELECTION

async def opponent_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the selection of an opponent."""
    username = update.message.text.strip()
    if not username.startswith('@'):
        await update.message.reply_text("Please provide a valid @username.")
        return OPPONENT_SELECTION

    game_id = context.user_data['game_id']
    games_data = load_games_data()
    group_id = games_data[game_id]['group_id']

    opponent_id = await get_user_id_by_username(context, group_id, username)

    if not opponent_id:
        await update.message.reply_text(f"Could not find user {username} in the group.")
        return OPPONENT_SELECTION

    games_data[game_id]['opponent_id'] = opponent_id
    save_games_data(games_data)

    # Show confirmation
    game = games_data[game_id]
    stake_type = game['challenger_stake']['type']
    stake_value = game['challenger_stake']['value']
    opponent = await context.bot.get_chat_member(group_id, opponent_id)

    confirmation_text = (
        f"<b>Game Setup Confirmation</b>\n\n"
        f"<b>Game:</b> {game['game_type']}\n"
        f"<b>Your Stake:</b> {stake_value} {stake_type}\n"
        f"<b>Opponent:</b> {opponent.user.mention_html()}\n\n"
        f"Is this correct?"
    )

    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data=f'confirm_game_{game_id}')],
        [InlineKeyboardButton("Cancel", callback_data=f'cancel_game_{game_id}')],
        [InlineKeyboardButton("Restart", callback_data=f'restart_game_{game_id}')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(confirmation_text, reply_markup=reply_markup, parse_mode='HTML')
    return CONFIRMATION

async def start_opponent_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the opponent to set up their stake."""
    game_id = context.args[0].split('_')[-1]

    games_data = load_games_data()
    game = games_data.get(game_id)

    if not game or game['opponent_id'] != update.effective_user.id:
        await update.message.reply_text("This is not a valid game for you to set up.")
        return ConversationHandler.END

    context.user_data['game_id'] = game_id
    context.user_data['player_role'] = 'opponent'

    keyboard = [
        [InlineKeyboardButton("Points", callback_data='stake_points')],
        [InlineKeyboardButton("Media (Photo, Video, Voice Note)", callback_data='stake_media')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text="What would you like to stake?",
        reply_markup=reply_markup
    )
    return STAKE_TYPE_SELECTION

async def cancel_game_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the game setup."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Game setup cancelled.")
    game_id = context.user_data.get('game_id')
    if game_id:
        games_data = load_games_data()
        if game_id in games_data:
            del games_data[game_id]
            save_games_data(games_data)
    return ConversationHandler.END

async def confirm_game_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirms the game setup and sends the challenge to the group."""
    query = update.callback_query
    await query.answer()
    game_id = query.data.split('_')[-1]

    games_data = load_games_data()
    game = games_data[game_id]

    game['status'] = 'pending_opponent_acceptance'
    save_games_data(games_data)

    challenger = await context.bot.get_chat_member(game['group_id'], game['challenger_id'])
    opponent = await context.bot.get_chat_member(game['group_id'], game['opponent_id'])

    challenge_text = (
        f"🚨 <b>New Challenge!</b> 🚨\n\n"
        f"{challenger.user.mention_html()} has challenged {opponent.user.mention_html()} to a game of {game['game_type']}!\n\n"
        f"{opponent.user.mention_html()}, do you accept?"
    )

    keyboard = [
        [
            InlineKeyboardButton("Accept", callback_data=f'accept_challenge_{game_id}'),
            InlineKeyboardButton("Refuse", callback_data=f'refuse_challenge_{game_id}'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=game['group_id'],
        text=challenge_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    await query.edit_message_text("Challenge has been sent!")
    return ConversationHandler.END

async def restart_game_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Restarts the game setup conversation."""
    return await start_game_setup(update, context)

async def challenge_response_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the opponent's response to a game challenge."""
    query = update.callback_query
    await query.answer()

    response_type, game_id = query.data.rsplit('_', 1)

    games_data = load_games_data()
    game = games_data.get(game_id)

    if not game:
        await query.edit_message_text("This game challenge is no longer valid.")
        return

    user_id = update.effective_user.id
    if user_id != game['opponent_id']:
        await query.answer("This challenge is not for you.", show_alert=True)
        return

    if response_type == 'accept_challenge':
        game['status'] = 'pending_opponent_stake'
        save_games_data(games_data)

        await query.edit_message_text("Challenge accepted! Please check your private messages to set up your stake.")

        keyboard = [[InlineKeyboardButton("Set Up Stake", url=f"https://t.me/{BOT_USERNAME}?start=setstake_{game_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=user_id,
            text="You have accepted the challenge! Click the button below to set up your stake.",
            reply_markup=reply_markup
        )

    elif response_type == 'refuse_challenge':
        challenger_id = game['challenger_id']
        challenger_stake = game['challenger_stake']

        await context.bot.send_message(
            chat_id=challenger_id,
            text=f"Your challenge was refused."
        )

        if challenger_stake['type'] == 'points':
            await context.bot.send_message(game['group_id'], f"The challenger has lost their stake of {challenger_stake['value']} points.")
        else:
            if challenger_stake['type'] == 'photo':
                await context.bot.send_photo(game['group_id'], challenger_stake['value'], caption="The challenger has lost their stake.")
            elif challenger_stake['type'] == 'video':
                await context.bot.send_video(game['group_id'], challenger_stake['value'], caption="The challenger has lost their stake.")
            elif challenger_stake['type'] == 'voice':
                await context.bot.send_voice(game['group_id'], challenger_stake['value'], caption="The challenger has lost their stake.")

        del games_data[game_id]
        save_games_data(games_data)

        await query.edit_message_text("Challenge refused.")

# =============================
# /inactive command and auto-kick logic
# =============================
async def inactive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /inactive <days> (admin only):
    - /inactive 0 disables auto-kick in the group.
    - /inactive <n> (1-99) enables auto-kick for users inactive for n days.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
        return
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await update.message.reply_text("Only admins can use this command.")
        return
    if not context.args or not context.args[0].strip().isdigit():
        await update.message.reply_text("Usage: /inactive <days> (0 to disable, 1-99 to enable)")
        return
    days = int(context.args[0].strip())
    group_id = str(update.effective_chat.id)
    settings = load_inactive_settings()
    if days == 0:
        settings.pop(group_id, None)
        save_inactive_settings(settings)
        await update.message.reply_text("Inactive user kicking is now disabled in this group.")
        print(f"[DEBUG] Inactive kicking disabled for group {group_id}")
        return
    if not (1 <= days <= 99):
        await update.message.reply_text("Please provide a number of days between 1 and 99.")
        return
    settings[group_id] = days
    save_inactive_settings(settings)
    await update.message.reply_text(f"Inactive user kicking is now enabled for this group. Users inactive for {days} days will be kicked.")
    print(f"[DEBUG] Inactive kicking enabled for group {group_id} with threshold {days} days")

async def check_and_kick_inactive_users(app):
    """
    Checks all groups with inactivity kicking enabled and kicks users who have been inactive too long.
    """
    print("[DEBUG] Running periodic inactive user check...")
    settings = load_inactive_settings()
    activity = load_activity_data()
    now = int(time.time())
    for group_id, days in settings.items():
        group_activity = activity.get(group_id, {})
        threshold = now - days * 86400
        try:
            bot = app.bot
            admins = await bot.get_chat_administrators(int(group_id))
            admin_ids = {str(admin.user.id) for admin in admins}
            members = list(group_activity.keys())
            for user_id in members:
                if user_id in admin_ids:
                    continue  # Never kick admins
                last_active = group_activity.get(user_id, 0)
                if last_active < threshold:
                    try:
                        await bot.ban_chat_member(int(group_id), int(user_id))
                        await bot.unban_chat_member(int(group_id), int(user_id))  # Unban to allow rejoining
                        print(f"[DEBUG] Kicked inactive user {user_id} from group {group_id}")
                    except Exception as e:
                        print(f"[ERROR] Failed to kick user {user_id} from group {group_id}: {e}")
        except Exception as e:
            print(f"[ERROR] Failed to process group {group_id} for inactivity kicking: {e}")

if __name__ == '__main__':
    print('Starting Telegram Bot...')
    print(f'TOKEN value: {TOKEN}')
    print(f'TOKEN repr: {repr(TOKEN)}')
    # Define post-init function to start periodic task after event loop is running
    async def periodic_inactive_check_job(context: ContextTypes.DEFAULT_TYPE):
        await check_and_kick_inactive_users(context.application)

    async def on_startup(app):
        # Schedule the periodic job using the job queue (every hour)
        app.job_queue.run_repeating(periodic_inactive_check_job, interval=3600, first=10)

    app = Application.builder().token(TOKEN).post_init(on_startup).build()

    #Commands
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('beowned', beowned_command))
    app.add_handler(CommandHandler('command', command_list_command))
    app.add_handler(CommandHandler('remove', remove_command))
    app.add_handler(CommandHandler('admin', admin_command))
    app.add_handler(CommandHandler('inactive', inactive_command))
    app.add_handler(CommandHandler('addreward', addreward_command))
    app.add_handler(CommandHandler('removereward', removereward_command))
    app.add_handler(CommandHandler('addpunishment', addpunishment_command))
    app.add_handler(CommandHandler('removepunishment', removepunishment_command))
    app.add_handler(CommandHandler('punishment', punishment_command))
    app.add_handler(CommandHandler('newgame', newgame_command))
    app.add_handler(CommandHandler('loser', loser_command))
    app.add_handler(CommandHandler('cleangames', cleangames_command))
    app.add_handler(CommandHandler('reward', reward_command))
    app.add_handler(CommandHandler('cancel', cancel_command))
    app.add_handler(CommandHandler('addpoints', addpoints_command))
    app.add_handler(CommandHandler('removepoints', removepoints_command))
    app.add_handler(CommandHandler('point', point_command))
    app.add_handler(CommandHandler('top5', top5_command))

    # Add the conversation handler with a high priority
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, conversation_handler), group=-1)

    game_setup_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_game_setup, pattern='^start_game_setup_'),
            CommandHandler('start', start_opponent_setup, filters=filters.Regex('^setstake_'))
        ],
        states={
            GAME_SELECTION: [CallbackQueryHandler(game_selection)],
            STAKE_TYPE_SELECTION: [CallbackQueryHandler(stake_type_selection)],
            STAKE_SUBMISSION_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, stake_submission_points)],
            STAKE_SUBMISSION_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO | filters.VOICE, stake_submission_media)],
            OPPONENT_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, opponent_selection)],
            CONFIRMATION: [
                CallbackQueryHandler(confirm_game_setup, pattern='^confirm_game_'),
                CallbackQueryHandler(restart_game_setup, pattern='^restart_game_'),
                CallbackQueryHandler(cancel_game_setup, pattern='^cancel_game_'),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_game_setup, pattern='^cancel_game_')],
    )
    app.add_handler(game_setup_handler)
    app.add_handler(CallbackQueryHandler(challenge_response_handler, pattern='^(accept_challenge_|refuse_challenge_)'))

    app.add_handler(MessageHandler(filters.COMMAND, dynamic_hashtag_command))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, hashtag_message_handler))
    # Unified handler for edited messages: process hashtags, responses, and future logic
    async def edited_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Normalize so .message is always present
        if hasattr(update, 'edited_message') and update.edited_message:
            update.message = update.edited_message
        # Route edited messages through all main logic
        await hashtag_message_handler(update, context)
        await message_handler(update, context)
        # Add future logic here as needed
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, edited_message_handler))
    app.add_handler(MessageHandler(filters.TEXT, message_handler))

    # Debug: catch-all handler to log all incoming messages
    async def debug_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"DEBUG: Received update: {update}")
    app.add_handler(MessageHandler(filters.ALL, debug_handler))

    # Errors
    app.add_error_handler(error)

    #Check for updates
    print('Polling...')
    app.run_polling(poll_interval=0.5)