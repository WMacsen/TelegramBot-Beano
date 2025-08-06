from telegram.ext import ContextTypes
from Main import (
    ADDREWARD_STATE, ADDREWARD_COST_STATE, REMOVEREWARD_STATE, REWARD_STATE,
    add_reward, remove_reward, reward_choice_handler
)

async def reward_interactive_handler(update, context: ContextTypes.DEFAULT_TYPE):
    # Add reward name step
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
    # Add reward cost step
    if ADDREWARD_COST_STATE in context.user_data:
        state = context.user_data[ADDREWARD_COST_STATE]
        try:
            cost = int(update.message.text.strip())
            if cost < 0:
                raise ValueError
        except Exception:
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
    # Remove reward step
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
    # Reward choice step
    if REWARD_STATE in context.user_data:
        await reward_choice_handler(update, context)
