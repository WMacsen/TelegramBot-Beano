import logging
import os
import json
import time
import random

from telegram import Update
from telegram.ext import ContextTypes

from features_admin import get_display_name, command_handler_wrapper, is_admin, get_user_id_by_username

logger = logging.getLogger(__name__)

# --- Constants ---
REWARDS_DATA_FILE = 'rewards.json'
POINTS_DATA_FILE = 'points.json'
PUNISHMENTS_DATA_FILE = 'punishments.json'
PUNISHMENT_STATUS_FILE = 'punishment_status.json'
NEGATIVE_POINTS_TRACKER_FILE = 'negative_points_tracker.json'
CHANCE_COOLDOWNS_FILE = 'chance_cooldowns.json'
DEFAULT_REWARD = {"name": "Other", "cost": 0}

# Conversation states
REWARD_STATE, ADDREWARD_STATE, ADDREWARD_COST_STATE, REMOVEREWARD_STATE, ADDPOINTS_STATE, REMOVEPOINTS_STATE, FREE_REWARD_SELECTION, ASK_TASK_TARGET, ASK_TASK_DESCRIPTION, ADMIN_HELP_STATE = range(10)

# --- Data Load/Save ---
def load_data(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {}
    return {}

def save_data(data, filepath):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- Logic from Main.py ---
def get_rewards_list(group_id):
    data = load_data(REWARDS_DATA_FILE)
    rewards = data.get(str(group_id), [])
    if not any(r["name"].lower() == "other" for r in rewards):
        rewards.append(DEFAULT_REWARD)
    return rewards

def add_reward(group_id, name, cost):
    if name.strip().lower() == "other": return False
    data = load_data(REWARDS_DATA_FILE)
    group_id_str = str(group_id)
    if group_id_str not in data: data[group_id_str] = []
    if any(r["name"].lower() == name.strip().lower() for r in data[group_id_str]): return False
    data[group_id_str].append({"name": name.strip(), "cost": int(cost)})
    save_data(data, REWARDS_DATA_FILE)
    return True

def remove_reward(group_id, name):
    if name.strip().lower() == "other": return False
    data, group_id_str = load_data(REWARDS_DATA_FILE), str(group_id)
    if group_id_str not in data: return False
    original_len = len(data[group_id_str])
    data[group_id_str] = [r for r in data[group_id_str] if r["name"].lower() != name.strip().lower()]
    if len(data[group_id_str]) == original_len: return False
    save_data(data, REWARDS_DATA_FILE)
    return True

def get_user_points(group_id, user_id):
    return load_data(POINTS_DATA_FILE).get(str(group_id), {}).get(str(user_id), 0)

def set_user_points(group_id, user_id, points):
    data = load_data(POINTS_DATA_FILE)
    data.setdefault(str(group_id), {})[str(user_id)] = points
    save_data(data, POINTS_DATA_FILE)

async def add_user_points(group_id, user_id, delta, context: ContextTypes.DEFAULT_TYPE):
    points = get_user_points(group_id, user_id) + delta
    set_user_points(group_id, user_id, points)
    if points >= 0:
        tracker = load_data(NEGATIVE_POINTS_TRACKER_FILE)
        group_id_str, user_id_str = str(group_id), str(user_id)
        if group_id_str in tracker and user_id_str in tracker.get(group_id_str, {}):
            if tracker[group_id_str][user_id_str] != 0:
                tracker[group_id_str][user_id_str] = 0
                save_data(tracker, NEGATIVE_POINTS_TRACKER_FILE)
    await check_for_punishment(group_id, user_id, context)
    await check_for_negative_points(group_id, user_id, points, context)

def get_triggered_punishments_for_user(group_id, user_id):
    return load_data(PUNISHMENT_STATUS_FILE).get(str(group_id), {}).get(str(user_id), [])

def add_triggered_punishment_for_user(group_id, user_id, punishment_message: str):
    data = load_data(PUNISHMENT_STATUS_FILE)
    group_id_str, user_id_str = str(group_id), str(user_id)
    data.setdefault(group_id_str, {}).setdefault(user_id_str, [])
    if punishment_message not in data[group_id_str][user_id_str]:
        data[group_id_str][user_id_str].append(punishment_message)
        save_data(data, PUNISHMENT_STATUS_FILE)

def remove_triggered_punishment_for_user(group_id, user_id, punishment_message: str):
    data = load_data(PUNISHMENT_STATUS_FILE)
    group_id_str, user_id_str = str(group_id), str(user_id)
    if group_id_str in data and user_id_str in data[group_id_str]:
        if punishment_message in data[group_id_str][user_id_str]:
            data[group_id_str][user_id_str].remove(punishment_message)
            save_data(data, PUNISHMENT_STATUS_FILE)

async def check_for_punishment(group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    punishments = load_data(PUNISHMENTS_DATA_FILE).get(str(group_id), [])
    user_points = get_user_points(group_id, user_id)
    triggered = get_triggered_punishments_for_user(group_id, user_id)
    for p in punishments:
        threshold = p.get("threshold")
        if threshold is not None and user_points < threshold and p["message"] not in triggered:
            member = await context.bot.get_chat_member(group_id, user_id)
            display_name = get_display_name(user_id, member.user.full_name)
            await context.bot.send_message(group_id, f"🚨 <b>Punishment Issued!</b> 🚨\n{display_name} has fallen below {threshold} points. Punishment: {p['message']}", parse_mode='HTML')
            add_triggered_punishment_for_user(group_id, user_id, p["message"])
        elif threshold is not None and user_points >= threshold and p["message"] in triggered:
            remove_triggered_punishment_for_user(group_id, user_id, p["message"])

async def check_for_negative_points(group_id, user_id, points, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation from Main.py needed

# --- Command Handlers ---
@command_handler_wrapper(admin_only=False)
async def reward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=True)
async def addreward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=True)
async def removereward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=True)
async def addpunishment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=True)
async def removepunishment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=False)
async def point_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

@command_handler_wrapper(admin_only=False)
async def chance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

async def conversation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass # Full implementation needed
