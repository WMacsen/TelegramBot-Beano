# =========================
# Imports and Configuration
# =========================
import logging
import os
import json
import re
import random
import html
import traceback
from typing import Final
import uuid
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext, CallbackQueryHandler, ConversationHandler
from telegram.constants import ChatMemberStatus

# =========================
# Logging Configuration
# =========================
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
# Suppress noisy library logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Debug: Print all environment variables at startup
logger.debug(f"Environment variables: {os.environ}")

# Load the Telegram bot token from environment variable
TOKEN = os.environ.get('TELEGRAM_TOKEN')
BOT_USERNAME: Final = '@MasterBeanoBot'  # Bot's username (update if needed)

# File paths for persistent data storage
HASHTAG_DATA_FILE = 'hashtag_data.json'  # Stores hashtagged messages/media
ADMIN_DATA_FILE = 'admins.json'          # Stores admin/owner info
from functools import wraps
OWNER_ID = 7237569475  # Your Telegram ID (change to your actual Telegram user ID)


# =========================
# Decorators
# =========================
def command_handler_wrapper(admin_only=False):
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            # Do not process if the message is not from a user
            if not update.effective_user or not update.message:
                return

            user = update.effective_user
            chat = update.effective_chat
            message_id = update.message.message_id

            # Defer message deletion to the end
            should_delete = True

            try:
                # Check if the command is disabled
                if chat.type in ['group', 'supergroup']:
                    command_name = func.__name__.replace('_command', '')
                    disabled_cmds = set(load_disabled_commands().get(str(chat.id), []))
                    if command_name in disabled_cmds:
                        logger.info(f"Command '{command_name}' is disabled in group {chat.id}. Aborting.")
                        return # Silently abort if command is disabled

                if admin_only and chat.type in ['group', 'supergroup']:
                    member = await context.bot.get_chat_member(chat.id, user.id)
                    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                        await update.message.reply_text(
                            f"Warning: {user.mention_html()}, you are not authorized to use this command.",
                            parse_mode='HTML'
                        )
                        # Still delete their command attempt
                        return

                # Execute the actual command function
                await func(update, context, *args, **kwargs)

            finally:
                # Delete the command message
                if should_delete and chat.type in ['group', 'supergroup']:
                    try:
                        await context.bot.delete_message(chat.id, message_id)
                    except Exception:
                        logger.warning(f"Failed to delete command message {message_id} in chat {chat.id}. Bot may not have delete permissions.")

        return wrapper
    return decorator


# =============================
# Admin/Owner Data Management
# =============================
ADMIN_NICKNAMES_FILE = 'admin_nicknames.json'

def load_admin_nicknames():
    if os.path.exists(ADMIN_NICKNAMES_FILE):
        with open(ADMIN_NICKNAMES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_admin_nicknames(data):
    with open(ADMIN_NICKNAMES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@command_handler_wrapper(admin_only=True)
async def setnickname_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Only the owner can use this command.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setnickname <@username or user_id> <nickname>")
        return

    target_identifier = context.args[0]
    nickname = " ".join(context.args[1:])

    target_id = None
    if target_identifier.isdigit():
        target_id = int(target_identifier)
    else:
        target_id = await get_user_id_by_username(context, update.effective_chat.id, target_identifier)

    if not target_id:
        await update.message.reply_text(f"Could not find user {target_identifier}.")
        return

    if not is_admin(target_id):
        await update.message.reply_text("You can only set nicknames for admins.")
        return

    nicknames = load_admin_nicknames()
    nicknames[str(target_id)] = nickname
    save_admin_nicknames(nicknames)

    await update.message.reply_text(f"Nickname for user {target_id} has been set to '{nickname}'.")

def load_admin_data():
    """Load admin and owner data from file. Ensures owner is always in admin list."""
    if os.path.exists(ADMIN_DATA_FILE):
        with open(ADMIN_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Always ensure owner is in admin list
            if str(OWNER_ID) not in data.get('admins', []):
                data['admins'] = list(set(data.get('admins', []) + [str(OWNER_ID)]))
            data['owner'] = str(OWNER_ID)
            logger.debug(f"Loaded admin data: {data}")
            return data
    # Default: owner is admin
    logger.debug("No admin data file found, using default owner as admin.")
    return {'owner': str(OWNER_ID), 'admins': [str(OWNER_ID)]}

def save_admin_data(data):
    """Save admin and owner data to file. Ensures owner is always in admin list."""
    # Always ensure owner is in admin list
    if str(data['owner']) not in data['admins']:
        data['admins'].append(str(data['owner']))
    with open(ADMIN_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.debug(f"Saved admin data: {data}")

def is_owner(user_id):
    """Check if the user is the owner."""
    data = load_admin_data()
    result = str(user_id) == str(data['owner'])
    logger.debug(f"is_owner({user_id}) -> {result}")
    return result

def get_display_name(user_id: int, full_name: str) -> str:
    """
    Determines the display name for a user based on their admin status and nickname.
    """
    if not is_admin(user_id):
        return "fag"

    nicknames = load_admin_nicknames()
    return nicknames.get(str(user_id), full_name)

def is_admin(user_id):
    """Check if the user is an admin or the owner."""
    data = load_admin_data()
    result = str(user_id) in data['admins'] or str(user_id) == str(data['owner'])
    logger.debug(f"is_admin({user_id}) -> {result}")
    return result

async def get_user_id_by_username(context, chat_id, username) -> str:
    """Get a user's Telegram ID by their username in a chat."""
    async for member in context.bot.get_chat_administrators(chat_id):
        if member.user.username and member.user.username.lower() == username.lower().lstrip('@'):
            logger.debug(f"Found user ID {member.user.id} for username {username}")
            return str(member.user.id)
    logger.debug(f"Username {username} not found in chat {chat_id}")
    return None

# =============================
# Hashtag Data Management
# =============================
def load_hashtag_data():
    """Load hashtagged message/media data from file."""
    if os.path.exists(HASHTAG_DATA_FILE):
        with open(HASHTAG_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.debug(f"Loaded hashtag data: {list(data.keys())}")
            return data
    logger.debug("No hashtag data file found, returning empty dict.")
    return {}

def save_hashtag_data(data):
    """Save hashtagged message/media data to file."""
    with open(HASHTAG_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.debug(f"Saved hashtag data: {list(data.keys())}")

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
    logger.debug(f"Added reward '{name}' with cost {cost} to group {group_id}")
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
    logger.debug(f"Removed reward '{name}' from group {group_id}")
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
    logger.debug(f"Set points for user {user_id} in group {group_id} to {points}")

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
                user_member = await context.bot.get_chat_member(group_id, user_id)
                display_name = get_display_name(user_id, user_member.user.full_name)
                await context.bot.send_message(
                    chat_id=group_id,
                    text=f"🚨 <b>Punishment Issued!</b> 🚨\n{display_name} has fallen below {threshold} points. Punishment: {message}",
                    parse_mode='HTML'
                )

                chat = await context.bot.get_chat(group_id)
                admins = await context.bot.get_chat_administrators(group_id)
                for admin in admins:
                    try:
                        await context.bot.send_message(
                            chat_id=admin.user.id,
                            text=f"User {display_name} (ID: {user_id}) in group {chat.title} (ID: {group_id}) triggered punishment '{message}' by falling below {threshold} points."
                        )
                    except Exception:
                        logger.warning(f"Failed to notify admin {admin.user.id} about punishment.")

                add_triggered_punishment_for_user(group_id, user_id, message)
        else:
            # If user is above threshold, reset their status for this punishment
            if message in triggered_punishments:
                remove_triggered_punishment_for_user(group_id, user_id, message)

async def add_user_points(group_id, user_id, delta, context: ContextTypes.DEFAULT_TYPE):
    points = get_user_points(group_id, user_id) + delta
    set_user_points(group_id, user_id, points)
    logger.debug(f"Added {delta} points for user {user_id} in group {group_id} (new total: {points})")

    # If user's points are non-negative, reset their negative strike counter for this group.
    if points >= 0:
        tracker = load_negative_tracker()
        group_id_str = str(group_id)
        user_id_str = str(user_id)
        if group_id_str in tracker and user_id_str in tracker.get(group_id_str, {}):
            if tracker[group_id_str][user_id_str] != 0:
                tracker[group_id_str][user_id_str] = 0
                save_negative_tracker(tracker)
                logger.debug(f"Reset negative points tracker for user {user_id_str} in group {group_id_str}.")

    # Run all punishment checks
    await check_for_punishment(group_id, user_id, context)
    await check_for_negative_points(group_id, user_id, points, context)

# =============================
# Negative Points Tracker
# =============================
NEGATIVE_POINTS_TRACKER_FILE = 'negative_points_tracker.json'

def load_negative_tracker():
    if os.path.exists(NEGATIVE_POINTS_TRACKER_FILE):
        with open(NEGATIVE_POINTS_TRACKER_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_negative_tracker(data):
    with open(NEGATIVE_POINTS_TRACKER_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def check_for_negative_points(group_id, user_id, points, context: ContextTypes.DEFAULT_TYPE):
    if points < 0:
        tracker = load_negative_tracker()
        group_id_str = str(group_id)
        user_id_str = str(user_id)

        if group_id_str not in tracker:
            tracker[group_id_str] = {}

        current_strikes = tracker.get(group_id_str, {}).get(user_id_str, 0)
        current_strikes += 1
        tracker[group_id_str][user_id_str] = current_strikes
        save_negative_tracker(tracker)

        user_member = await context.bot.get_chat_member(group_id, user_id)
        user_mention = user_member.user.mention_html()

        if current_strikes < 3:
            # On the first and second strike, mute for 24h and reset points.
            try:
                await context.bot.restrict_chat_member(
                    chat_id=group_id,
                    user_id=user_id,
                    permissions={'can_send_messages': False},
                    until_date=time.time() + 86400  # 24 hours
                )
                set_user_points(group_id, user_id, 0) # Reset points to 0
                await context.bot.send_message(
                    chat_id=group_id,
                    text=f"{user_mention} has dropped into negative points (Strike {current_strikes}/3). They have been muted for 24 hours and their points reset to 0.",
                    parse_mode='HTML'
                )
            except Exception:
                logger.exception(f"Failed to mute user {user_id} for negative points (Strike {current_strikes}).")
        else:
            # On the third strike, send a special message and notify admins.
            tracker[group_id_str][user_id_str] = 0  # Reset strikes after 3rd strike
            save_negative_tracker(tracker)

            chat = await context.bot.get_chat(group_id)
            admins = await context.bot.get_chat_administrators(group_id)
            await context.bot.send_message(
                chat_id=group_id,
                text=f"🚨 <b>Third Strike!</b> 🚨\n{user_mention} has reached negative points for the third time. A special punishment from the admins is coming, and you are not allowed to refuse if you wish to remain in the group.",
                parse_mode='HTML'
            )
            for admin in admins:
                try:
                    await context.bot.send_message(
                        chat_id=admin.user.id,
                        text=f"User {user_mention} in group '{chat.title}' has reached negative points for the third time and requires a special punishment. Their strike counter has been reset.",
                        parse_mode='HTML'
                    )
                except Exception:
                    logger.warning(f"Failed to notify admin {admin.user.id} about 3rd strike.")

# =============================
# Chance Game Helpers
# =============================
CHANCE_COOLDOWNS_FILE = 'chance_cooldowns.json'

def load_cooldowns():
    if os.path.exists(CHANCE_COOLDOWNS_FILE):
        with open(CHANCE_COOLDOWNS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cooldowns(data):
    with open(CHANCE_COOLDOWNS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_last_played(user_id):
    cooldowns = load_cooldowns()
    return cooldowns.get(str(user_id))

def set_last_played(user_id):
    cooldowns = load_cooldowns()
    cooldowns[str(user_id)] = time.time()
    save_cooldowns(cooldowns)

def get_chance_outcome():
    """
    Returns a random outcome for the chance game based on weighted probabilities.
    """
    outcomes = [
        {"name": "plus_50", "weight": 15},
        {"name": "minus_100", "weight": 15},
        {"name": "chastity_2_days", "weight": 15},
        {"name": "chastity_7_days", "weight": 5},
        {"name": "nothing", "weight": 30},
        {"name": "free_reward", "weight": 10},
        {"name": "lose_all_points", "weight": 2.5},
        {"name": "double_points", "weight": 2.5},
        {"name": "ask_task", "weight": 5},
    ]

    total_weight = sum(o['weight'] for o in outcomes)
    random_num = random.uniform(0, total_weight)

    current_weight = 0
    for outcome in outcomes:
        current_weight += outcome['weight']
        if random_num <= current_weight:
            return outcome['name']

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
# Game Logic Helpers
# =============================
def create_connect_four_board_markup(board: list, game_id: str):
    """Creates the text and markup for a Connect Four board."""
    emojis = {0: '⚫️', 1: '🔴', 2: '🟡'}
    board_text = ""
    for row in board:
        board_text += " ".join([emojis.get(cell, '⚫️') for cell in row]) + "\n"

    keyboard = [
        [InlineKeyboardButton(str(i + 1), callback_data=f'c4_move_{game_id}_{i}') for i in range(7)]
    ]
    return board_text, InlineKeyboardMarkup(keyboard)


def check_connect_four_win(board: list, player_num: int) -> bool:
    """Check for a win in Connect Four."""
    # Check horizontal
    for r in range(6):
        for c in range(4):
            if all(board[r][c + i] == player_num for i in range(4)):
                return True
    # Check vertical
    for r in range(3):
        for c in range(7):
            if all(board[r + i][c] == player_num for i in range(4)):
                return True
    # Check diagonal (down-right)
    for r in range(3):
        for c in range(4):
            if all(board[r + i][c + i] == player_num for i in range(4)):
                return True
    # Check diagonal (up-right)
    for r in range(3, 6):
        for c in range(4):
            if all(board[r - i][c + i] == player_num for i in range(4)):
                return True
    return False


def check_connect_four_draw(board: list) -> bool:
    """Check for a draw in Connect Four."""
    return all(cell != 0 for cell in board[0])


async def handle_game_over(context: ContextTypes.DEFAULT_TYPE, game_id: str, winner_id: int, loser_id: int):
    """Handles the end of a game, distributing stakes."""
    games_data = load_games_data()
    game = games_data[game_id]

    if str(game['challenger_id']) == str(loser_id):
        loser_stake = game.get('challenger_stake')
    else:
        loser_stake = game.get('opponent_stake')

    if not loser_stake:
        logger.error(f"No loser stake found for game {game_id}")
        return

    loser_member = await context.bot.get_chat_member(game['group_id'], loser_id)
    winner_member = await context.bot.get_chat_member(game['group_id'], winner_id)
    loser_name = get_display_name(loser_id, loser_member.user.full_name)
    winner_name = get_display_name(winner_id, winner_member.user.full_name)

    if loser_stake['type'] == 'points':
        points_val = loser_stake['value']
        await add_user_points(game['group_id'], winner_id, points_val, context)
        await add_user_points(game['group_id'], loser_id, -points_val, context)
        message = f"{winner_name.capitalize()} has won the game! {loser_name} lost {points_val} points."
        if 'fag' in winner_name:
            message = f"The {winner_name} has won the game! {loser_name} lost {points_val} points."
        await context.bot.send_message(
            game['group_id'],
            message,
            parse_mode='HTML'
        )
    else:  # media
        caption = f"{winner_name.capitalize()} won the game! This is the loser's stake from {loser_name}."
        if 'fag' in winner_name:
            caption = f"The {winner_name} won the game! This is the loser's stake from {loser_name}."
        if loser_stake['type'] == 'photo':
            await context.bot.send_photo(game['group_id'], loser_stake['value'], caption=caption, parse_mode='HTML')
        elif loser_stake['type'] == 'video':
            await context.bot.send_video(game['group_id'], loser_stake['value'], caption=caption, parse_mode='HTML')
        elif loser_stake['type'] == 'voice':
            await context.bot.send_voice(game['group_id'], loser_stake['value'], caption=caption, parse_mode='HTML')

    game['status'] = 'complete'
    save_games_data(games_data)


async def connect_four_move_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles a move in a Connect Four game."""
    query = update.callback_query
    await query.answer()

    _, _, game_id, col_str = query.data.split('_')
    col = int(col_str)
    user_id = query.from_user.id

    games_data = load_games_data()
    game = games_data.get(game_id)

    if not game or game.get('status') != 'active':
        await query.edit_message_text("This game is no longer active.")
        return

    # Check if it's the user's turn
    if game.get('turn') != user_id:
        await query.answer("It's not your turn!", show_alert=True)
        return

    # Make the move
    board = game['board']
    player_num = 1 if user_id == game['challenger_id'] else 2

    # Find the lowest empty row in the column
    move_made = False
    for r in range(5, -1, -1):
        if board[r][col] == 0:
            board[r][col] = player_num
            move_made = True
            break

    if not move_made:
        await query.answer("This column is full!", show_alert=True)
        return

    game['board'] = board

    # Check for win
    if check_connect_four_win(board, player_num):
        winner_id = user_id
        loser_id = game['opponent_id'] if user_id == game['challenger_id'] else game['challenger_id']

        winner_member = await context.bot.get_chat_member(game['group_id'], winner_id)
        winner_name = get_display_name(winner_id, winner_member.user.full_name)

        board_text, _ = create_connect_four_board_markup(board, game_id)

        win_message = f"{winner_name.capitalize()} wins!"
        if 'fag' in winner_name:
            win_message = f"The {winner_name} wins!"

        await query.edit_message_text(
            f"<b>Connect Four - Game Over!</b>\n\n{board_text}\n{win_message}",
            parse_mode='HTML'
        )
        await handle_game_over(context, game_id, winner_id, loser_id)
        return

    # Check for draw
    if check_connect_four_draw(board):
        board_text, _ = create_connect_four_board_markup(board, game_id)
        await query.edit_message_text(f"<b>Connect Four - Draw!</b>\n\n{board_text}\nThe game is a draw!")
        game['status'] = 'complete'
        save_games_data(games_data)
        return

    # Switch turns
    game['turn'] = game['opponent_id'] if user_id == game['challenger_id'] else game['challenger_id']
    save_games_data(games_data)

    # Update board message
    turn_player_id = game['turn']
    turn_player_member = await context.bot.get_chat_member(game['group_id'], turn_player_id)
    turn_player_name = get_display_name(turn_player_id, turn_player_member.user.full_name)
    board_text, reply_markup = create_connect_four_board_markup(game['board'], game_id)

    await query.edit_message_text(
        f"<b>Connect Four</b>\n\n{board_text}\nIt's {turn_player_name}'s turn.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


# =============================
# Game Logic Helpers
# =============================
BATTLESHIP_SHIPS = {
    "Carrier": 5, "Battleship": 4, "Cruiser": 3,
    "Submarine": 3, "Destroyer": 2,
}
BS_AWAITING_PLACEMENT = 0

def parse_bs_coords(coord_str: str) -> tuple[int, int] | None:
    """Parses 'A1' style coordinates into (row, col) tuple."""
    coord_str = coord_str.upper().strip()
    if not (2 <= len(coord_str) <= 3): return None
    col_char = coord_str[0]
    row_str = coord_str[1:]
    if not ('A' <= col_char <= 'J' and row_str.isdigit()): return None
    row = int(row_str) - 1
    col = ord(col_char) - ord('A')
    if not (0 <= row <= 9 and 0 <= col <= 9): return None
    return row, col

def generate_bs_board_text(board: list, show_ships: bool = True) -> str:
    """Generates a text representation of a battleship board."""
    emojis = {'water': '🟦', 'ship': '🚢', 'hit': '🔥', 'miss': '❌'}

    map_values = {0: emojis['water'], 1: emojis['ship'] if show_ships else emojis['water'], 2: emojis['miss'], 3: emojis['hit']}

    header = '`  A B C D E F G H I J`\n'
    board_text = header
    for r, row_data in enumerate(board):
        row_num = str(r + 1).rjust(2)
        row_str = ' '.join([map_values.get(cell, '🟦') for cell in row_data])
        board_text += f"`{row_num} {row_str}`\n"
    return board_text

async def bs_start_game_in_group(context: ContextTypes.DEFAULT_TYPE, game_id: str):
    """Announces the start of the Battleship game in the group chat and prompts the first player."""
    games_data = load_games_data()
    game = games_data[game_id]

    challenger_id = game['challenger_id']
    challenger_member = await context.bot.get_chat_member(game['group_id'], challenger_id)
    challenger_name = get_display_name(challenger_id, challenger_member.user.full_name)

    await context.bot.send_message(
        chat_id=game['group_id'],
        text=f"All ships have been placed! The battle begins now.\n\nIt's {challenger_name}'s turn to attack. Check your private messages!",
        parse_mode='HTML'
    )
    await bs_send_turn_message(context, game_id)

def check_bs_ship_sunk(board: list, ship_coords: list) -> bool:
    """Checks if a ship has been completely sunk."""
    return all(board[r][c] == 3 for r, c in ship_coords)

async def bs_send_turn_message(context: ContextTypes.DEFAULT_TYPE, game_id: str, message_id: int = None, chat_id: int = None):
    """Sends the private message to the current player to make their move."""
    games_data = load_games_data()
    game = games_data[game_id]

    player_id_str = str(game['turn'])
    opponent_id_str = str(game['opponent_id'] if player_id_str == str(game['challenger_id']) else game['challenger_id'])

    my_board_text = generate_bs_board_text(game['boards'][player_id_str], show_ships=True)
    tracking_board_text = generate_bs_board_text(game['boards'][opponent_id_str], show_ships=False)

    # Keyboard to select a column to attack
    keyboard = [
        [InlineKeyboardButton(chr(ord('A') + c), callback_data=f"bs_col_{game_id}_{c}") for c in range(5)],
        [InlineKeyboardButton(chr(ord('A') + c), callback_data=f"bs_col_{game_id}_{c}") for c in range(5, 10)]
    ]

    text = f"YOUR BOARD:\n{my_board_text}\nOPPONENT'S BOARD:\n{tracking_board_text}\nSelect a column to attack:"

    if message_id and chat_id:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text,
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2'
        )
    else:
        await context.bot.send_message(
            chat_id=int(player_id_str), text=text,
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2'
        )

async def bs_select_col_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the player selecting a column, then asks for the row."""
    query = update.callback_query
    await query.answer()

    _, _, game_id, c_str = query.data.split('_')
    c = int(c_str)

    # Keyboard to select a row to attack
    keyboard = [[InlineKeyboardButton(str(r + 1), callback_data=f"bs_attack_{game_id}_{r}_{c}") for r in range(10)]]

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

async def bs_attack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the player's final attack choice."""
    query = update.callback_query
    await query.answer()

    _, _, game_id, r_str, c_str = query.data.split('_')
    r, c = int(r_str), int(c_str)
    user_id_str = str(query.from_user.id)

    games_data = load_games_data()
    game = games_data.get(game_id)

    if not game or game.get('status') != 'active':
        await query.edit_message_text("This game is no longer active.")
        return

    if str(game.get('turn')) != user_id_str:
        await query.answer("It's not your turn!", show_alert=True)
        return

    opponent_id_str = str(game['opponent_id'] if user_id_str == str(game['challenger_id']) else game['challenger_id'])
    opponent_board = game['boards'][opponent_id_str]
    target_val = opponent_board[r][c]

    if target_val in [2, 3]:
        await query.answer("You have already fired at this location.", show_alert=True)
        return

    result_text = ""
    if target_val == 0:
        opponent_board[r][c] = 2; result_text = "It's a MISS!"
    elif target_val == 1:
        opponent_board[r][c] = 3; result_text = "It's a HIT!"
        for ship, coords in game['ships'][opponent_id_str].items():
            if (r, c) in coords and check_bs_ship_sunk(opponent_board, coords):
                result_text += f"\nYou sunk their {ship}!"
                break

    all_sunk = all(check_bs_ship_sunk(opponent_board, coords) for coords in game['ships'][opponent_id_str].values())

    if all_sunk:
        winner_name = get_display_name(int(user_id_str), query.from_user.full_name)
        win_message = f"The game is over! {winner_name.capitalize()} has won the battle!"
        if 'fag' in winner_name:
            win_message = f"The game is over! The {winner_name} has won the battle!"
        await context.bot.send_message(
            chat_id=game['group_id'],
            text=win_message,
            parse_mode='HTML'
        )
        await handle_game_over(context, game_id, int(user_id_str), int(opponent_id_str))
        await query.edit_message_text("You are victorious! See the group for the result.")
        return

    game['turn'] = int(opponent_id_str)
    save_games_data(games_data)

    opponent_member = await context.bot.get_chat_member(game['group_id'], int(opponent_id_str))
    opponent_name = get_display_name(int(opponent_id_str), opponent_member.user.full_name)
    attacker_name = get_display_name(int(user_id_str), query.from_user.full_name)
    coord_name = f"{chr(ord('A')+c)}{r+1}"

    await query.edit_message_text(f"You fired at {coord_name}. {result_text}\n\nWaiting for {opponent_name} to move.", parse_mode='HTML')

    try:
        await context.bot.send_message(
            chat_id=int(opponent_id_str),
            text=f"{attacker_name} fired at {coord_name}. {result_text}"
        )
    except Exception as e:
        print(f"Failed to send attack result to victim: {e}")

    await context.bot.send_message(
        chat_id=game['group_id'],
        text=f"It is now {opponent_name}'s turn.",
        parse_mode='HTML'
    )

    await bs_send_turn_message(context, game_id)

async def bs_start_placement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the battleship ship placement conversation."""
    query = update.callback_query
    await query.answer()

    _, _, game_id = query.data.split('_')
    user_id = str(query.from_user.id)

    games_data = load_games_data()
    game = games_data.get(game_id)
    if not game:
        await query.edit_message_text("This game no longer exists.")
        return ConversationHandler.END

    if game.get('placement_complete', {}).get(user_id):
        await query.edit_message_text("You have already placed your ships.")
        return ConversationHandler.END

    context.user_data['bs_game_id'] = game_id
    context.user_data['bs_ships_to_place'] = list(BATTLESHIP_SHIPS.keys())

    board_text = generate_bs_board_text(game['boards'][user_id])

    ship_to_place = context.user_data['bs_ships_to_place'][0]
    ship_size = BATTLESHIP_SHIPS[ship_to_place]

    await query.edit_message_text(
        f"Your board:\n{board_text}\n"
        f"Place your {ship_to_place} ({ship_size} spaces).\n"
        "Send coordinates in the format `A1 H` (for horizontal) or `A1 V` (for vertical).",
        parse_mode='MarkdownV2'
    )
    return BS_AWAITING_PLACEMENT

async def bs_handle_placement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the user's input for placing a single ship."""
    game_id = context.user_data.get('bs_game_id')
    if not game_id: return ConversationHandler.END

    user_id = str(update.effective_user.id)
    games_data = load_games_data()
    game = games_data[game_id]
    board = game['boards'][user_id]

    ship_name = context.user_data['bs_ships_to_place'][0]
    ship_size = BATTLESHIP_SHIPS[ship_name]

    text = update.message.text.strip().upper()
    parts = text.split()

    if len(parts) != 2:
        await update.message.reply_text("Invalid format. Please use `A1 H` or `A1 V`.", parse_mode='MarkdownV2')
        return BS_AWAITING_PLACEMENT

    start_coord_str, orientation = parts
    start_pos = parse_bs_coords(start_coord_str)

    if not start_pos or orientation not in ['H', 'V']:
        await update.message.reply_text("Invalid coordinate or orientation. Use `A1 H` or `B2 V`.", parse_mode='MarkdownV2')
        return BS_AWAITING_PLACEMENT

    r_start, c_start = start_pos
    ship_coords = []

    valid = True
    for i in range(ship_size):
        r, c = r_start, c_start
        if orientation == 'H': c += i
        else: r += i

        if not (0 <= r <= 9 and 0 <= c <= 9): valid = False; break
        if board[r][c] != 0: valid = False; break
        ship_coords.append((r, c))

    if not valid:
        await update.message.reply_text("Invalid placement: ship is out of bounds or overlaps another ship. Try again.")
        return BS_AWAITING_PLACEMENT

    for r, c in ship_coords:
        board[r][c] = 1
    game['ships'][user_id][ship_name] = ship_coords

    context.user_data['bs_ships_to_place'].pop(0)

    save_games_data(games_data)
    board_text = generate_bs_board_text(board)

    if not context.user_data['bs_ships_to_place']:
        game['placement_complete'][user_id] = True
        save_games_data(games_data)

        await update.message.reply_text(f"Final board:\n{board_text}\nAll ships placed! Waiting for opponent...", parse_mode='MarkdownV2')

        opponent_id = str(game['opponent_id'] if user_id == str(game['challenger_id']) else game['challenger_id'])
        if game.get('placement_complete', {}).get(opponent_id):
            await bs_start_game_in_group(context, game_id)

        return ConversationHandler.END
    else:
        next_ship_name = context.user_data['bs_ships_to_place'][0]
        next_ship_size = BATTLESHIP_SHIPS[next_ship_name]
        await update.message.reply_text(
            f"Your board:\n{board_text}\n"
            f"Place your {next_ship_name} ({next_ship_size} spaces). Format: `A1 H` or `A1 V`.",
            parse_mode='MarkdownV2'
        )
        return BS_AWAITING_PLACEMENT

async def bs_placement_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the ship placement conversation and aborts the game."""
    game_id = context.user_data.get('bs_game_id')
    if game_id:
        games_data = load_games_data()
        if game_id in games_data:
            game = games_data[game_id]
            # Notify the other player if possible
            user_id = str(update.effective_user.id)
            other_player_id = str(game['opponent_id'] if user_id == str(game['challenger_id']) else game['challenger_id'])
            try:
                await context.bot.send_message(
                    chat_id=other_player_id,
                    text=f"{update.effective_user.full_name} has cancelled the game during ship placement."
                )
            except Exception:
                logger.warning(f"Failed to notify other player {other_player_id} of cancellation.")

            # Delete the game
            del games_data[game_id]
            save_games_data(games_data)

    await update.message.reply_text("Ship placement cancelled. The game has been aborted.")
    context.user_data.clear()
    return ConversationHandler.END

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
        logger.debug(f"Added triggered punishment '{punishment_message}' for user {user_id} in group {group_id}")

def remove_triggered_punishment_for_user(group_id, user_id, punishment_message: str):
    data = load_punishment_status_data()
    group_id = str(group_id)
    user_id = str(user_id)
    if group_id in data and user_id in data[group_id]:
        if punishment_message in data[group_id][user_id]:
            data[group_id][user_id].remove(punishment_message)
            save_punishment_status_data(data)
            logger.debug(f"Removed triggered punishment '{punishment_message}' for user {user_id} in group {group_id}")

# =============================
# Reward System Commands
# =============================
REWARD_STATE = 'awaiting_reward_choice'
ADDREWARD_STATE = 'awaiting_addreward_name'
ADDREWARD_COST_STATE = 'awaiting_addreward_cost'
REMOVEREWARD_STATE = 'awaiting_removereward_name'
ADDPOINTS_STATE = 'awaiting_addpoints_value'
REMOVEPOINTS_STATE = 'awaiting_removepoints_value'

@command_handler_wrapper(admin_only=False)
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
            display_name = get_display_name(user_id, update.effective_user.full_name)
            chat_title = update.effective_chat.title

            message = f"You have selected 'Other', {display_name}. Please contact Beta or Lion to determine your reward and its cost."
            await update.message.reply_text(message, parse_mode='HTML')

            admins = await context.bot.get_chat_administrators(update.effective_chat.id)
            for admin in admins:
                try:
                    admin_message = f"The user {display_name} has selected the 'Other' reward in group {chat_title}. They will contact you to finalize the details."
                    if 'fag' in display_name:
                        admin_message = f"The fag has selected the 'Other' reward in group {chat_title}. They will contact you to finalize the details."
                    await context.bot.send_message(
                        chat_id=admin.user.id,
                        text=admin_message,
                        parse_mode='HTML'
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
        display_name = get_display_name(user_id, update.effective_user.full_name)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🎁 <b>{display_name}</b> just bought the reward: <b>{reward['name']}</b>! 🎉",
            parse_mode='HTML'
        )

        # Private message to admins
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        for admin in admins:
            try:
                await context.bot.send_message(
                    chat_id=admin.user.id,
                    text=f"User {display_name} (ID: {user_id}) in group {update.effective_chat.title} (ID: {group_id}) just bought the reward: '{reward['name']}' for {reward['cost']} points."
                )
            except Exception:
                logger.warning(f"Failed to notify admin {admin.user.id} about reward purchase.")

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

    # === Free Reward Flow ===
    if FREE_REWARD_SELECTION in context.user_data:
        state = context.user_data[FREE_REWARD_SELECTION]
        group_id = state['group_id']
        user_id = update.effective_user.id
        choice = update.message.text.strip()
        rewards = get_rewards_list(group_id)
        reward = next((r for r in rewards if r['name'].lower() == choice.lower()), None)

        if not reward:
            await update.message.reply_text("That reward does not exist. Please reply with a valid reward name.")
            return

        display_name = get_display_name(user_id, update.effective_user.full_name)
        await update.message.reply_text(f"Congratulations! You have claimed your free reward: <b>{reward['name']}</b>!", parse_mode='HTML')

        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        for admin in admins:
            try:
                await context.bot.send_message(
                    chat_id=admin.user.id,
                    text=f"User {display_name} (ID: {user_id}) in group {update.effective_chat.title} (ID: {group_id}) claimed the free reward: '{reward['name']}'."
                )
            except Exception:
                logger.warning(f"Failed to notify admin {admin.user.id} about free reward.")

        context.user_data.pop(FREE_REWARD_SELECTION, None)
        return

    # === Ask Task Flow ===
    if ASK_TASK_TARGET in context.user_data:
        state = context.user_data[ASK_TASK_TARGET]
        username = update.message.text.strip()
        if not username.startswith('@'):
            await update.message.reply_text("Please provide a valid @username.")
            return

        state['target_username'] = username
        context.user_data[ASK_TASK_DESCRIPTION] = state
        context.user_data.pop(ASK_TASK_TARGET, None)
        await update.message.reply_text("What is the simple task you want to ask of them?")
        return

    if ASK_TASK_DESCRIPTION in context.user_data:
        state = context.user_data[ASK_TASK_DESCRIPTION]
        task_description = update.message.text.strip()
        group_id = state['group_id']
        challenger_user = update.effective_user
        challenger_name = get_display_name(challenger_user.id, challenger_user.full_name)
        target_username = state['target_username']

        # Announce in group
        message = f"{challenger_name.capitalize()} has a task for {target_username}: {task_description}"
        if 'fag' in challenger_name:
            message = f"The {challenger_name} has a task for {target_username}: {task_description}"
        await context.bot.send_message(
            chat_id=group_id,
            text=message,
            parse_mode='HTML'
        )

        await update.message.reply_text("Your task has been assigned.")
        context.user_data.pop(ASK_TASK_DESCRIPTION, None)
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
        display_name = get_display_name(user.id, user.full_name)
        chat = message.chat
        replied_message = help_data.get('replied_message')
        help_text = f"🚨 <b>Admin Help Request</b> 🚨\n" \
                    f"<b>User:</b> {display_name} (ID: {user.id})\n" \
                    f"<b>Group:</b> {getattr(chat, 'title', chat.id)} (ID: {chat.id})\n" \
                    f"<b>Reason:</b> {reason}\n"
        if replied_message:
            rep_user_data = replied_message.get('from', {})
            rep_user_id = rep_user_data.get('id')
            rep_user_name = get_display_name(rep_user_id, rep_user_data.get('username', 'Unknown'))
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
                help_text += f"<b>Replied to:</b> {rep_user_name} (ID: {rep_user_id})\n"
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
            except Exception:
                logger.warning(f"Failed to notify admin {admin.user.id} in help request.")
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

@command_handler_wrapper(admin_only=True)
async def addreward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addreward (admin only): Start add reward process
    """
    if update.effective_chat.type == "private":
        await update.message.reply_text("This command can only be used in group chats.")
        return
    context.user_data[ADDREWARD_STATE] = {'group_id': str(update.effective_chat.id)}
    await update.message.reply_text("What is the name of the reward you want to add?")

@command_handler_wrapper(admin_only=True)
async def addpunishment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addpunishment <threshold> <message> (admin only): Adds a new punishment.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
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

@command_handler_wrapper(admin_only=True)
async def removepunishment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /removepunishment <message> (admin only): Removes a punishment.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
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

@command_handler_wrapper(admin_only=False)
async def newgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /newgame (as a reply): Starts a new game with the replied-to user.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Please use this command as a reply to the user you want to challenge.")
        return

    challenger_user = update.effective_user
    opponent_user = update.message.reply_to_message.from_user

    if challenger_user.id == opponent_user.id:
        await update.message.reply_text("You cannot challenge yourself.")
        return

    game_id = str(uuid.uuid4())
    games_data = load_games_data()

    games_data[game_id] = {
        "group_id": update.effective_chat.id,
        "challenger_id": challenger_user.id,
        "opponent_id": opponent_user.id,
        "game_type": None,
        "challenger_stake": None,
        "opponent_stake": None,
        "status": "pending_game_selection"
    }
    save_games_data(games_data)

    challenger_name = get_display_name(challenger_user.id, challenger_user.full_name)
    opponent_name = get_display_name(opponent_user.id, opponent_user.full_name)

    await update.message.reply_text(
        f"{challenger_name} has challenged {opponent_name}! {challenger_name}, please check your private messages to set up the game.",
        parse_mode='HTML'
    )

    try:
        keyboard = [[InlineKeyboardButton("Start Game Setup", callback_data=f"start_game_setup_{game_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=challenger_user.id,
            text="Let's set up your game! Click the button below to begin.",
            reply_markup=reply_markup
        )
    except Exception:
        logger.exception(f"Failed to send private message to user {challenger_user.id}")
        await update.message.reply_text("I couldn't send you a private message. Please make sure you have started a chat with me privately first.")

@command_handler_wrapper(admin_only=True)
async def loser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /loser <user> (admin only): Enacts the loser condition for the specified user.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
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

    loser_member = await context.bot.get_chat_member(game['group_id'], loser_id)
    winner_member = await context.bot.get_chat_member(game['group_id'], winner_id)
    loser_name = get_display_name(loser_id, loser_member.user.full_name)
    winner_name = get_display_name(winner_id, winner_member.user.full_name)

    # Determine the message based on whether the loser is a 'fag'
    message = f"{loser_name.capitalize()} is a loser! They lost {loser_stake['value']} points to {winner_name}."
    if 'fag' in loser_name:
        message = f"The {loser_name} is a loser! They lost {loser_stake['value']} points to {winner_name}."

    if loser_stake['type'] == 'points':
        await add_user_points(game['group_id'], winner_id, loser_stake['value'], context)
        await add_user_points(game['group_id'], loser_id, -loser_stake['value'], context)
        await context.bot.send_message(
            game['group_id'],
            message,
            parse_mode='HTML'
        )
    else:
        caption = f"{loser_name.capitalize()} is a loser! This was their stake."
        if 'fag' in loser_name:
            caption = f"The {loser_name} is a loser! This was their stake."

        if loser_stake['type'] == 'photo':
            await context.bot.send_photo(game['group_id'], loser_stake['value'], caption=caption, parse_mode='HTML')
        elif loser_stake['type'] == 'video':
            await context.bot.send_video(game['group_id'], loser_stake['value'], caption=caption, parse_mode='HTML')
        elif loser_stake['type'] == 'voice':
            await context.bot.send_voice(game['group_id'], loser_stake['value'], caption=caption, parse_mode='HTML')

    game['status'] = 'complete'
    save_games_data(games_data)

@command_handler_wrapper(admin_only=False)
async def chance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /chance (once per day): Play a game of chance for a random outcome.
    """
    user_id = update.effective_user.id
    last_played = get_last_played(user_id)

    if last_played and (time.time() - last_played) < 86400: # 24 hours
        remaining_time = 86400 - (time.time() - last_played)
        hours = int(remaining_time // 3600)
        minutes = int((remaining_time % 3600) // 60)
        await update.message.reply_text(f"You have already played today. Please wait {hours}h {minutes}m to play again.")
        return

    await update.message.reply_text("You spin the wheel of fortune...")
    outcome = get_chance_outcome()

    group_id = str(update.effective_chat.id)

    if outcome == "plus_50":
        await add_user_points(group_id, user_id, 50, context)
        await update.message.reply_text("Congratulations! You won 50 points!")
    elif outcome == "minus_100":
        await add_user_points(group_id, user_id, -100, context)
        await update.message.reply_text("Ouch! You lost 100 points.")
    elif outcome == "chastity_2_days":
        await update.message.reply_text("Your fate is 2 days of chastity!")
    elif outcome == "chastity_7_days":
        await update.message.reply_text("Your fate is 7 days of chastity! Good luck.")
    elif outcome == "nothing":
        await update.message.reply_text("Nothing happened. Better luck next time!")
    elif outcome == "lose_all_points":
        points = get_user_points(group_id, user_id)
        await add_user_points(group_id, user_id, -points, context)
        await update.message.reply_text("Catastrophic failure! You lost all your points.")
    elif outcome == "double_points":
        points = get_user_points(group_id, user_id)
        await add_user_points(group_id, user_id, points, context)
        await update.message.reply_text("Jackpot! Your points have been doubled!")

    elif outcome == "free_reward":
        rewards = get_rewards_list(group_id)
        msg = "<b>You won a free reward!</b>\nChoose one of the following:\n"
        for r in rewards:
            msg += f"• <b>{r['name']}</b>\n"
        msg += "\nReply with the name of the reward you want."
        context.user_data[FREE_REWARD_SELECTION] = {'group_id': group_id}
        await update.message.reply_text(msg, parse_mode='HTML')
    elif outcome == "ask_task":
        await update.message.reply_text("You have won the right to ask a simple task from any of the other boys. Who would you like to ask? (Please provide their @username)")
        context.user_data[ASK_TASK_TARGET] = {'group_id': group_id}

    set_last_played(user_id)

@command_handler_wrapper(admin_only=True)
async def cleangames_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cleangames (admin only): Clears out completed or stale game data.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
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

@command_handler_wrapper(admin_only=True)
async def punishment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /punishment (admin only): Lists all punishments for the group.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
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

@command_handler_wrapper(admin_only=True)
async def removereward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /removereward (admin only): Start remove reward process
    """
    context.user_data[REMOVEREWARD_STATE] = {'group_id': str(update.effective_chat.id)}
    await update.message.reply_text("What is the name of the reward you want to remove?")

@command_handler_wrapper(admin_only=True)
async def addpoints_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addpoints <username|id> (admin only): Start add points process
    """
    group_id = str(update.effective_chat.id)
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

@command_handler_wrapper(admin_only=True)
async def removepoints_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /removepoints <username|id> (admin only): Start remove points process
    """
    group_id = str(update.effective_chat.id)
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

@command_handler_wrapper(admin_only=False)
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
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
        points = get_user_points(group_id, target_id)
        display_name = get_display_name(target_id, target_user.full_name)
        message = f"{display_name.capitalize()} has {points} points."
        if 'fag' in display_name:
            message = f"The {display_name} has {points} points."
        await update.message.reply_text(message)
        return
    # If no argument, show own points
    if not context.args:
        points = get_user_points(group_id, user.id)
        await update.message.reply_text(f"The fag has {points} points.")
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

    target_member = await context.bot.get_chat_member(group_id, target_id)
    display_name = get_display_name(target_id, target_member.user.full_name)
    points = get_user_points(group_id, target_id)
    await update.message.reply_text(f"{display_name} has {points} points.")

@command_handler_wrapper(admin_only=True)
async def top5_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /top5 (admin only): Show top 5 users by points in the group
    """
    group_id = str(update.effective_chat.id)
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
            name = get_display_name(int(uid), member.user.full_name)
        except Exception:
            name = f"User {uid}"
        lines.append(f"<b>{idx}.</b> <i>{name}</i> — <b>{pts} points</b> {'🏆' if idx==1 else ''}")
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
    logger.debug(f"Updated activity for user {user_id} in group {group_id}")

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
        logger.debug("No message found in update for hashtag handler.")
        return
    # Update user activity for inactivity tracking
    if message.chat and message.from_user and message.chat.type in ["group", "supergroup"]:
        update_user_activity(message.from_user.id, message.chat.id)
    text = message.text or message.caption or ''
    hashtags = re.findall(r'#(\w+)', text)
    if not hashtags:
        logger.debug("No hashtags found in message.")
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
            logger.debug(f"Scheduled flush for media group {cache_key}")
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
        logger.debug(f"Saved single message under tag #{tag}")
    save_hashtag_data(data)
    await message.reply_text(f"Saved under: {', '.join('#'+t for t in hashtags)}")

# =============================
# Dynamic Hashtag Command Handler
# =============================
async def dynamic_hashtag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles dynamic hashtag commands (e.g. /mytag) to retrieve saved messages/media.
    This acts as a fallback for any command not in COMMAND_MAP.
    """
    if update.effective_chat.type == "private":
        # This message is not sent because the wrapper deletes the command.
        # It's better to handle this check inside the command logic if a response is needed.
        return

    if not update.message or not update.message.text:
        return

    command = update.message.text[1:].split()[0].lower()

    # Prevent this handler from hijacking static commands defined in COMMAND_MAP
    if command in COMMAND_MAP:
        return

    data = load_hashtag_data()
    if command not in data:
        await update.message.reply_text(f"No data found for #{command}.")
        logger.debug(f"No data found for command: {command}")
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
        logger.debug(f"No saved messages or media for command: {command}")

# =============================
# /command - List all commands
# =============================
COMMAND_MAP = {
    'start': {'is_admin': False}, 'help': {'is_admin': False}, 'beowned': {'is_admin': False},
    'command': {'is_admin': False}, 'remove': {'is_admin': True}, 'admin': {'is_admin': False},
    'link': {'is_admin': True}, 'inactive': {'is_admin': True}, 'addreward': {'is_admin': True},
    'removereward': {'is_admin': True}, 'addpunishment': {'is_admin': True},
    'removepunishment': {'is_admin': True}, 'punishment': {'is_admin': True},
    'newgame': {'is_admin': False}, 'loser': {'is_admin': True}, 'cleangames': {'is_admin': True},
    'chance': {'is_admin': False}, 'reward': {'is_admin': False}, 'cancel': {'is_admin': False},
    'addpoints': {'is_admin': True}, 'removepoints': {'is_admin': True},
    'point': {'is_admin': False}, 'top5': {'is_admin': True}, 'setnickname': {'is_admin': True},
}

@command_handler_wrapper(admin_only=False)
async def command_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dynamically lists all available commands based on user's admin status and disabled commands.
    """
    if update.effective_chat.type == "private":
        await update.message.reply_text("Please use this command in a group to see the available commands for that group.")
        return

    group_id = str(update.effective_chat.id)
    disabled_cmds = set(load_disabled_commands().get(group_id, []))

    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    is_admin_user = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]

    everyone_cmds = []
    admin_only_cmds = []

    # Static commands from COMMAND_MAP
    for cmd, info in sorted(COMMAND_MAP.items()):
        if cmd in ['start', 'help']:  # Don't show these in the group list
            continue

        is_disabled = cmd in disabled_cmds
        display_cmd = f"/{cmd}"
        if is_disabled:
            display_cmd += " (disabled)"

        if info['is_admin']:
            if is_admin_user:  # Admins see all admin commands
                admin_only_cmds.append(display_cmd)
        else:  # Everyone commands
            if not is_disabled:
                everyone_cmds.append(display_cmd)
            elif is_admin_user:  # Admins also see disabled everyone commands
                everyone_cmds.append(display_cmd)

    # Dynamic hashtag commands (always admin-only)
    if is_admin_user:
        hashtag_data = load_hashtag_data()
        for tag in sorted(hashtag_data.keys()):
            admin_only_cmds.append(f"/{tag}")

    msg = '<b>Commands for everyone:</b>\n' + ('\n'.join(everyone_cmds) if everyone_cmds else 'None')
    if is_admin_user:
        msg += '\n\n<b>Commands for admins only:</b>\n' + ('\n'.join(admin_only_cmds) if admin_only_cmds else 'None')

    await update.message.reply_text(msg, parse_mode='HTML')

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
@command_handler_wrapper(admin_only=True)
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
    # Dynamic command removal
    if tag in data:
        del data[tag]
        save_hashtag_data(data)
        await update.message.reply_text(f"Removed dynamic command: /{tag}")
        return
    # Static command disabling
    if tag in COMMAND_MAP:
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
@command_handler_wrapper(admin_only=False)
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


@command_handler_wrapper(admin_only=True)
async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /link (admin only): Creates a single-use invite link for the group.
    """
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == 'private':
        await update.message.reply_text(
            "This command is used to generate an invite link for a group. "
            "Please run this command inside the group you want the link for."
        )
        return

    if chat.type in ['group', 'supergroup']:
        try:
            # Create a single-use invite link
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=chat.id,
                member_limit=1,
                name=f"Invite for {user.full_name}"
            )

            # Send the link to the admin in a private message
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"Here is your single-use invite link for the group '{chat.title}':\n{invite_link.invite_link}"
                )
                # Confirm in the group chat
                await update.message.reply_text("I have sent you a single-use invite link in a private message.")
            except Exception as e:
                logger.error(f"Failed to send private message to admin {user.id}: {e}")
                await update.message.reply_text(
                    "I couldn't send you a private message. "
                    "Please make sure you have started a chat with me privately first."
                )

        except Exception as e:
            logger.error(f"Failed to create invite link for chat {chat.id}: {e}")
            await update.message.reply_text(
                "I was unable to create an invite link. "
                "Please ensure I have the 'Invite Users via Link' permission in this group."
            )


#Start command
@command_handler_wrapper(admin_only=False)
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
@command_handler_wrapper(admin_only=False)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows the interactive help menu.
    """
    if update.effective_chat.type != "private":
        await update.message.reply_text("Please use the /help command in a private chat with me for a better experience.")
        return

    keyboard = [
        [InlineKeyboardButton("General Commands", callback_data='help_general')],
        [InlineKeyboardButton("Game Commands", callback_data='help_games')],
        [InlineKeyboardButton("Point System", callback_data='help_points')],
        [InlineKeyboardButton("Admin Commands", callback_data='help_admin')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Welcome to the help menu! Please choose a category:",
        reply_markup=reply_markup
    )

async def help_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all interactions with the interactive help menu."""
    query = update.callback_query
    await query.answer()

    topic = query.data

    text = ""
    keyboard = [[InlineKeyboardButton("« Back to Main Menu", callback_data='help_back')]]

    if topic == 'help_general':
        text = """
<b>General Commands</b>
- /help: Shows this help menu.
- /command: Lists all available commands in the current group.
- /beowned: Information on how to be owned.
- /admin: Request help from admins in a group.
        """
    elif topic == 'help_games':
        text = """
<b>Game Commands</b>
- /newgame (reply to user): Challenge someone to a game (Dice, Connect Four, Battleship).
- /loser (admin only): Declare a user as the loser of a game.
- /cleangames (admin only): Clean up old game data.
- /chance: Play a daily game of chance for points or other outcomes.
        """
    elif topic == 'help_points':
        text = """
<b>Point & Reward System</b>
- /point: Check your own points.
- /reward: View and buy available rewards.
- /top5 (admin only): See the top 5 users with the most points.
- /addpoints (admin only): Add points to a user.
- /removepoints (admin only): Remove points from a user.
- /addreward (admin only): Add a new reward.
- /removereward (admin only): Remove a reward.
- /punishment (admin only): List punishments for low points.
- /addpunishment (admin only): Add a new punishment.
- /removepunishment (admin only): Remove a punishment.
        """
    elif topic == 'help_admin':
        text = """
<b>Admin Commands</b>
This bot has many admin commands for managing games, points, and users.
Due to Telegram limitations, I cannot know if you are an admin in a private chat.

To see the full list of admin commands available to you in a specific group, please go to that group and use the `/command` command.
        """
    elif topic == 'help_back':
        main_menu_keyboard = [
            [InlineKeyboardButton("General Commands", callback_data='help_general')],
            [InlineKeyboardButton("Game Commands", callback_data='help_games')],
            [InlineKeyboardButton("Point System", callback_data='help_points')],
            [InlineKeyboardButton("Admin Commands", callback_data='help_admin')],
        ]
        await query.edit_message_text(
            "Welcome to the help menu! Please choose a category:",
            reply_markup=InlineKeyboardMarkup(main_menu_keyboard)
        )
        return

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML', disable_web_page_preview=True)

#BeOwned command
@command_handler_wrapper(admin_only=False)
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

import html
import traceback

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    logger.error(message)


# =============================
# Game Setup Conversation
# =============================
GAME_SELECTION, ROUND_SELECTION, STAKE_TYPE_SELECTION, STAKE_SUBMISSION_POINTS, STAKE_SUBMISSION_MEDIA, OPPONENT_SELECTION, CONFIRMATION, FREE_REWARD_SELECTION, ASK_TASK_TARGET, ASK_TASK_DESCRIPTION = range(10)

async def start_game_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the game setup conversation."""
    query = update.callback_query
    await query.answer()
    game_id = query.data.split('_')[-1]
    context.user_data['game_id'] = game_id

    keyboard = [
        [InlineKeyboardButton("Dice Game", callback_data='game_dice')],
        [InlineKeyboardButton("Connect Four", callback_data='game_connect_four')],
        [InlineKeyboardButton("Battleship", callback_data='game_battleship')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text="Please select the game you want to play:",
        reply_markup=reply_markup
    )
    return GAME_SELECTION

async def game_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the game selection."""
    query = update.callback_query
    await query.answer()
    game_type = query.data

    game_id = context.user_data['game_id']
    games_data = load_games_data()
    games_data[game_id]['game_type'] = game_type

    if game_type == 'game_connect_four':
        # Initialize Connect Four board (6 rows, 7 columns)
        games_data[game_id]['board'] = [[0 for _ in range(7)] for _ in range(6)]
        # Challenger goes first
        games_data[game_id]['turn'] = games_data[game_id]['challenger_id']

    save_games_data(games_data)

    if game_type == 'game_dice':
        keyboard = [
            [InlineKeyboardButton("Best of 3", callback_data='rounds_3')],
            [InlineKeyboardButton("Best of 5", callback_data='rounds_5')],
            [InlineKeyboardButton("Best of 9", callback_data='rounds_9')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="How many rounds would you like to play?",
            reply_markup=reply_markup
        )
        return ROUND_SELECTION
    else:
        # Placeholder for other games
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

async def round_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the round selection for the Dice Game."""
    query = update.callback_query
    await query.answer()
    rounds = int(query.data.split('_')[-1])

    game_id = context.user_data['game_id']
    games_data = load_games_data()
    games_data[game_id]['rounds_to_play'] = rounds
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
    logger.debug("In stake_submission_points")
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
            game = games_data[game_id]
            if game['game_type'] == 'game_dice':
                game['current_round'] = 1
                game['challenger_score'] = 0
                game['opponent_score'] = 0
                game['last_roll'] = None
            game['status'] = 'active'
            save_games_data(games_data)
            challenger = await context.bot.get_chat_member(game['group_id'], game['challenger_id'])
            opponent = await context.bot.get_chat_member(game['group_id'], game['opponent_id'])
            await context.bot.send_message(
                chat_id=game['group_id'],
                text=f"The game between {challenger.user.mention_html()} and {opponent.user.mention_html()} is on!",
                parse_mode='HTML'
            )

            if game['game_type'] == 'game_connect_four':
                challenger_member = await context.bot.get_chat_member(game['group_id'], game['challenger_id'])
                board_text, reply_markup = create_connect_four_board_markup(game['board'], game_id)
                await context.bot.send_message(
                    chat_id=game['group_id'],
                    text=f"<b>Connect Four!</b>\n\n{board_text}\nIt's {challenger_member.user.mention_html()}'s turn.",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            elif game['game_type'] == 'game_battleship':
                challenger_id = str(game['challenger_id'])
                opponent_id = str(game['opponent_id'])
                game['boards'] = {
                    challenger_id: [[0] * 10 for _ in range(10)],
                    opponent_id: [[0] * 10 for _ in range(10)]
                }
                game['ships'] = {challenger_id: {}, opponent_id: {}}
                game['placement_complete'] = {challenger_id: False, opponent_id: False}
                game['turn'] = game['challenger_id']
                save_games_data(games_data)

                placement_keyboard = [[InlineKeyboardButton("Begin Ship Placement", callback_data=f'bs_start_placement_{game_id}')]]
                placement_markup = InlineKeyboardMarkup(placement_keyboard)
                try:
                    await context.bot.send_message(
                        chat_id=game['challenger_id'],
                        text="Your Battleship game is ready! It's time to place your ships.",
                        reply_markup=placement_markup
                    )
                    await context.bot.send_message(
                        chat_id=game['opponent_id'],
                        text="Your Battleship game is ready! It's time to place your ships.",
                        reply_markup=placement_markup
                    )
                except Exception as e:
                    print(f"Error sending battleship placement message: {e}")

            return ConversationHandler.END
        else:
            # Since opponent is already selected, go straight to confirmation
            return await show_confirmation(update, context)

    except ValueError:
        await update.message.reply_text("Please enter a valid number of points.")
        return STAKE_SUBMISSION_POINTS

async def stake_submission_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the submission of media as a stake."""
    logger.debug("In stake_submission_media")
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
        game = games_data[game_id]
        if game['game_type'] == 'game_dice':
            game['current_round'] = 1
            game['challenger_score'] = 0
            game['opponent_score'] = 0
            game['last_roll'] = None
        game['status'] = 'active'
        save_games_data(games_data)
        challenger = await context.bot.get_chat_member(game['group_id'], game['challenger_id'])
        opponent = await context.bot.get_chat_member(game['group_id'], game['opponent_id'])
        await context.bot.send_message(
            chat_id=game['group_id'],
            text=f"The game between {challenger.user.mention_html()} and {opponent.user.mention_html()} is on!",
            parse_mode='HTML'
        )

        if game['game_type'] == 'game_connect_four':
            challenger_member = await context.bot.get_chat_member(game['group_id'], game['challenger_id'])
            board_text, reply_markup = create_connect_four_board_markup(game['board'], game_id)
            await context.bot.send_message(
                chat_id=game['group_id'],
                text=f"<b>Connect Four!</b>\n\n{board_text}\nIt's {challenger_member.user.mention_html()}'s turn.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        elif game['game_type'] == 'game_battleship':
            challenger_id = str(game['challenger_id'])
            opponent_id = str(game['opponent_id'])
            game['boards'] = {
                challenger_id: [[0] * 10 for _ in range(10)],
                opponent_id: [[0] * 10 for _ in range(10)]
            }
            game['ships'] = {challenger_id: {}, opponent_id: {}}
            game['placement_complete'] = {challenger_id: False, opponent_id: False}
            game['turn'] = game['challenger_id']
            save_games_data(games_data)

            placement_keyboard = [[InlineKeyboardButton("Begin Ship Placement", callback_data=f'bs_start_placement_{game_id}')]]
            placement_markup = InlineKeyboardMarkup(placement_keyboard)
            try:
                await context.bot.send_message(
                    chat_id=game['challenger_id'],
                    text="Your Battleship game is ready! It's time to place your ships.",
                    reply_markup=placement_markup
                )
                await context.bot.send_message(
                    chat_id=game['opponent_id'],
                    text="Your Battleship game is ready! It's time to place your ships.",
                    reply_markup=placement_markup
                )
            except Exception:
                logger.exception("Error sending battleship placement message")

        return ConversationHandler.END
    else:
        return await show_confirmation(update, context)

async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows the confirmation message."""
    game_id = context.user_data['game_id']
    games_data = load_games_data()
    game = games_data[game_id]

    if context.user_data.get('player_role') == 'opponent':
        stake_type = game['opponent_stake']['type']
        stake_value = game['opponent_stake']['value']
    else:
        stake_type = game['challenger_stake']['type']
        stake_value = game['challenger_stake']['value']

    opponent_member = await context.bot.get_chat_member(game['group_id'], game['opponent_id'])
    opponent_name = get_display_name(opponent_member.user.id, opponent_member.user.full_name)

    confirmation_text = (
        f"<b>Game Setup Confirmation</b>\n\n"
        f"<b>Game:</b> {game['game_type']}\n"
        f"<b>Your Stake:</b> {stake_value} {stake_type}\n"
        f"<b>Opponent:</b> {opponent_name}\n\n"
        f"Is this correct?"
    )

    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data=f'confirm_game_{game_id}')],
        [InlineKeyboardButton("Cancel", callback_data=f'cancel_game_{game_id}')],
        [InlineKeyboardButton("Restart", callback_data=f'restart_game_{game_id}')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(confirmation_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(confirmation_text, reply_markup=reply_markup, parse_mode='HTML')

    return CONFIRMATION

async def start_opponent_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the opponent to set up their stake via callback."""
    query = update.callback_query
    await query.answer()
    game_id = query.data.split('_')[-1]

    games_data = load_games_data()
    game = games_data.get(game_id)

    if not game or game['opponent_id'] != query.from_user.id:
        await query.edit_message_text("This is not a valid game for you to set up.")
        return ConversationHandler.END

    context.user_data['game_id'] = game_id
    context.user_data['player_role'] = 'opponent'

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

    challenger_member = await context.bot.get_chat_member(game['group_id'], game['challenger_id'])
    opponent_member = await context.bot.get_chat_member(game['group_id'], game['opponent_id'])
    challenger_name = get_display_name(challenger_member.user.id, challenger_member.user.full_name)
    opponent_name = get_display_name(opponent_member.user.id, opponent_member.user.full_name)

    challenge_text = (
        f"🚨 <b>New Challenge!</b> 🚨\n\n"
        f"{challenger_name} has challenged {opponent_name} to a game of {game['game_type']}!\n\n"
        f"{opponent_name}, do you accept?"
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

async def dice_roll_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles dice rolls for the Dice Game."""
    if not update.message or not update.message.dice or update.message.dice.emoji != '🎲':
        return

    user_id = update.effective_user.id
    games_data = load_games_data()

    active_game_id = None
    active_game = None
    for game_id, game in games_data.items():
        if game.get('game_type') == 'game_dice' and \
           game.get('status') == 'active' and \
           (game.get('challenger_id') == user_id or game.get('opponent_id') == user_id):
            active_game_id = game_id
            active_game = game
            break

    if not active_game:
        return

    # This is a lot of logic for one function. I will break it down in the future if needed.
    last_roll = active_game.get('last_roll')

    if not last_roll: # First roll of a round
        active_game['last_roll'] = {'user_id': user_id, 'value': update.message.dice.value}
        save_games_data(games_data)
        other_player_id = active_game['challenger_id'] if user_id == active_game['opponent_id'] else active_game['opponent_id']
        other_player_member = await context.bot.get_chat_member(active_game['group_id'], other_player_id)
        other_player_name = get_display_name(other_player_id, other_player_member.user.full_name)
        await update.message.reply_text(f"You rolled a {update.message.dice.value}. Waiting for {other_player_name} to roll.", parse_mode='HTML')
        return

    if last_roll['user_id'] == user_id:
        await update.message.reply_text("It's not your turn to roll.")
        return

    # Second roll of a round, determine winner
    player1_id = last_roll['user_id']
    player2_id = user_id
    player1_roll = last_roll['value']
    player2_roll = update.message.dice.value

    if player1_roll > player2_roll:
        winner_id = player1_id
    elif player2_roll > player1_roll:
        winner_id = player2_id
    else: # Tie
        await update.message.reply_text(f"You both rolled a {player1_roll}. It's a tie! Roll again.")
        active_game['last_roll'] = None # Reset for re-roll
        save_games_data(games_data)
        return

    # Update scores
    if winner_id == active_game['challenger_id']:
        active_game['challenger_score'] += 1
    else:
        active_game['opponent_score'] += 1

    winner_member = await context.bot.get_chat_member(active_game['group_id'], winner_id)
    winner_name = get_display_name(winner_id, winner_member.user.full_name)
    win_message = f"{winner_name.capitalize()} wins round {active_game['current_round']}!\n" \
                  f"Score: {active_game['challenger_score']} - {active_game['opponent_score']}"
    if 'fag' in winner_name:
        win_message = f"The {winner_name} wins round {active_game['current_round']}!\n" \
                      f"Score: {active_game['challenger_score']} - {active_game['opponent_score']}"
    await context.bot.send_message(
        chat_id=active_game['group_id'],
        text=win_message,
        parse_mode='HTML'
    )

    # Check for game over
    rounds_to_win = (active_game['rounds_to_play'] // 2) + 1
    if active_game['challenger_score'] >= rounds_to_win or active_game['opponent_score'] >= rounds_to_win:
        # Game over
        if active_game['challenger_score'] > active_game['opponent_score']:
            game_winner_id = active_game['challenger_id']
            game_loser_id = active_game['opponent_id']
        else:
            game_winner_id = active_game['opponent_id']
            game_loser_id = active_game['challenger_id']

        # Enact loser logic by calling the /loser command's logic
        # This is code duplication. A better design would be to have a separate function.
        # For now, I will duplicate the logic from loser_command.
        game = active_game
        loser_id = game_loser_id
        winner_id = game_winner_id

        if str(game['challenger_id']) == str(loser_id):
            loser_stake = game['challenger_stake']
        else:
            loser_stake = game['opponent_stake']

        loser_member = await context.bot.get_chat_member(game['group_id'], loser_id)
        winner_member = await context.bot.get_chat_member(game['group_id'], winner_id)

        loser_name = get_display_name(loser_id, loser_member.user.full_name)
        winner_name = get_display_name(winner_id, winner_member.user.full_name)
        if loser_stake['type'] == 'points':
            await add_user_points(game['group_id'], winner_id, loser_stake['value'], context)
            await add_user_points(game['group_id'], loser_id, -loser_stake['value'], context)
            message = f"{loser_name.capitalize()} is a loser! They lost {loser_stake['value']} points to {winner_name}."
            if 'fag' in loser_name:
                message = f"The {loser_name} is a loser! They lost {loser_stake['value']} points to {winner_name}."
            await context.bot.send_message(
                game['group_id'],
                message,
                parse_mode='HTML'
            )
        else:
            caption = f"{loser_name.capitalize()} is a loser! This was their stake."
            if 'fag' in loser_name:
                caption = f"The {loser_name} is a loser! This was their stake."
            if loser_stake['type'] == 'photo':
                await context.bot.send_photo(game['group_id'], loser_stake['value'], caption=caption, parse_mode='HTML')
            elif loser_stake['type'] == 'video':
                await context.bot.send_video(game['group_id'], loser_stake['value'], caption=caption, parse_mode='HTML')
            elif loser_stake['type'] == 'voice':
                await context.bot.send_voice(game['group_id'], loser_stake['value'], caption=caption, parse_mode='HTML')

        game['status'] = 'complete'
        save_games_data(games_data)
    else:
        # Next round
        active_game['current_round'] += 1
        active_game['last_roll'] = None
        save_games_data(games_data)
        await context.bot.send_message(
            chat_id=active_game['group_id'],
            text=f"Round {active_game['current_round']}! It's anyone's turn to roll."
        )

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

        keyboard = [[InlineKeyboardButton("Set your stakes", callback_data=f"opponent_setup_{game_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=user_id,
            text="You have accepted the challenge! Click the button below to set up your stake.",
            reply_markup=reply_markup
        )

    elif response_type == 'refuse_challenge':
        challenger_id = game['challenger_id']
        challenger_stake = game['challenger_stake']

        challenger_member = await context.bot.get_chat_member(game['group_id'], challenger_id)
        challenger_name = get_display_name(challenger_id, challenger_member.user.full_name)

        await context.bot.send_message(
            chat_id=challenger_id,
            text=f"Your challenge was refused by {get_display_name(update.effective_user.id, update.effective_user.full_name)}."
        )

        if challenger_stake['type'] == 'points':
            message = f"{challenger_name.capitalize()} is a loser for being refused! They lost {challenger_stake['value']} points."
            if 'fag' in challenger_name:
                message = f"The {challenger_name} is a loser for being refused! They lost {challenger_stake['value']} points."
            await context.bot.send_message(
                game['group_id'],
                message,
                parse_mode='HTML'
            )
        else:
            caption = f"{challenger_name.capitalize()} is a loser for being refused! This was their stake."
            if 'fag' in challenger_name:
                caption = f"The {challenger_name} is a loser for being refused! This was their stake."
            if challenger_stake['type'] == 'photo':
                await context.bot.send_photo(game['group_id'], challenger_stake['value'], caption=caption, parse_mode='HTML')
            elif challenger_stake['type'] == 'video':
                await context.bot.send_video(game['group_id'], challenger_stake['value'], caption=caption, parse_mode='HTML')
            elif challenger_stake['type'] == 'voice':
                await context.bot.send_voice(game['group_id'], challenger_stake['value'], caption=caption, parse_mode='HTML')

        del games_data[game_id]
        save_games_data(games_data)

        await query.edit_message_text("Challenge refused.")

# =============================
# /inactive command and auto-kick logic
# =============================
@command_handler_wrapper(admin_only=True)
async def inactive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /inactive <days> (admin only):
    - /inactive 0 disables auto-kick in the group.
    - /inactive <n> (1-99) enables auto-kick for users inactive for n days.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in group chats.")
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
        logger.debug(f"Inactive kicking disabled for group {group_id}")
        return
    if not (1 <= days <= 99):
        await update.message.reply_text("Please provide a number of days between 1 and 99.")
        return
    settings[group_id] = days
    save_inactive_settings(settings)
    await update.message.reply_text(f"Inactive user kicking is now enabled for this group. Users inactive for {days} days will be kicked.")
    logger.debug(f"Inactive kicking enabled for group {group_id} with threshold {days} days")

async def check_and_kick_inactive_users(app):
    """
    Checks all groups with inactivity kicking enabled and kicks users who have been inactive too long.
    """
    logger.debug("Running periodic inactive user check...")
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
                        logger.error(f"Failed to kick user {user_id} from group {group_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to process group {group_id} for inactivity kicking: {e}")

# =============================
# Command Registration Helper
# =============================
def add_command(app: Application, command: str, handler):
    """
    Registers a command with support for /, ., and ! prefixes.
    """
    # Wrapper for MessageHandlers to populate context.args
    async def message_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message and update.message.text:
            context.args = update.message.text.split()[1:]
        await handler(update, context)

    # Register for /<command> - uses the original handler as it populates args automatically
    app.add_handler(CommandHandler(command, handler))

    # Register for .<command> and !<command> - uses the wrapper
    app.add_handler(MessageHandler(filters.Regex(rf'^\.{command}(\s|$)'), message_handler_wrapper))
    app.add_handler(MessageHandler(filters.Regex(rf'^!{command}(\s|$)'), message_handler_wrapper))


if __name__ == '__main__':
    logger.info('Starting Telegram Bot...')
    logger.debug(f'TOKEN value: {TOKEN}')
    # Define post-init function to start periodic task after event loop is running
    async def periodic_inactive_check_job(context: ContextTypes.DEFAULT_TYPE):
        await check_and_kick_inactive_users(context.application)

    async def on_startup(app):
        # Schedule the periodic job using the job queue (every hour)
        app.job_queue.run_repeating(periodic_inactive_check_job, interval=3600, first=10)

    app = Application.builder().token(TOKEN).post_init(on_startup).build()

    #Commands
    # Register all commands using the new helper
    add_command(app, 'start', start_command)
    add_command(app, 'help', help_command)
    add_command(app, 'beowned', beowned_command)
    add_command(app, 'command', command_list_command)
    add_command(app, 'remove', remove_command)
    add_command(app, 'admin', admin_command)
    add_command(app, 'link', link_command)
    add_command(app, 'inactive', inactive_command)
    add_command(app, 'addreward', addreward_command)
    add_command(app, 'removereward', removereward_command)
    add_command(app, 'addpunishment', addpunishment_command)
    add_command(app, 'removepunishment', removepunishment_command)
    add_command(app, 'punishment', punishment_command)
    add_command(app, 'newgame', newgame_command)
    add_command(app, 'loser', loser_command)
    add_command(app, 'cleangames', cleangames_command)
    add_command(app, 'chance', chance_command)
    add_command(app, 'reward', reward_command)
    add_command(app, 'cancel', cancel_command)
    add_command(app, 'addpoints', addpoints_command)
    add_command(app, 'removepoints', removepoints_command)
    add_command(app, 'point', point_command)
    add_command(app, 'top5', top5_command)
    add_command(app, 'setnickname', setnickname_command)

    # Add the conversation handler with a high priority
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, conversation_handler), group=-1)

    game_setup_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_game_setup, pattern='^start_game_setup_'),
            CallbackQueryHandler(start_opponent_setup, pattern='^opponent_setup_')
        ],
        states={
            GAME_SELECTION: [CallbackQueryHandler(game_selection)],
            ROUND_SELECTION: [CallbackQueryHandler(round_selection)],
            STAKE_TYPE_SELECTION: [CallbackQueryHandler(stake_type_selection)],
            STAKE_SUBMISSION_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, stake_submission_points)],
            STAKE_SUBMISSION_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO | filters.VOICE, stake_submission_media)],
            CONFIRMATION: [
                CallbackQueryHandler(confirm_game_setup, pattern='^confirm_game_'),
                CallbackQueryHandler(restart_game_setup, pattern='^restart_game_'),
                CallbackQueryHandler(cancel_game_setup, pattern='^cancel_game_'),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_game_setup, pattern='^cancel_game_')],
    )
    # Battleship placement handler
    battleship_placement_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(bs_start_placement, pattern='^bs_start_placement_')],
        states={
            BS_AWAITING_PLACEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bs_handle_placement)],
        },
        fallbacks=[CommandHandler('cancel', bs_placement_cancel)],
        conversation_timeout=600  # 10 minutes to place all ships
    )
    app.add_handler(battleship_placement_handler)

    app.add_handler(game_setup_handler)
    app.add_handler(CallbackQueryHandler(challenge_response_handler, pattern='^(accept_challenge_|refuse_challenge_)'))
    app.add_handler(CallbackQueryHandler(connect_four_move_handler, pattern=r'^c4_move_'))
    app.add_handler(CallbackQueryHandler(bs_select_col_handler, pattern=r'^bs_col_'))
    app.add_handler(CallbackQueryHandler(bs_attack_handler, pattern=r'^bs_attack_'))
    app.add_handler(CallbackQueryHandler(help_menu_handler, pattern=r'^help_'))
    app.add_handler(MessageHandler(filters.Dice, dice_roll_handler))

    # Fallback handler for dynamic hashtag commands.
    # The group=1 makes it lower priority than the static commands registered with add_command (which are in the default group 0)
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^[./!].*'), dynamic_hashtag_command), group=1)

    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.Document()) & ~filters.COMMAND, hashtag_message_handler))
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

    # Errors
    app.add_error_handler(error_handler)

    #Check for updates
    logger.info('Polling...')
    app.run_polling(poll_interval=0.5)