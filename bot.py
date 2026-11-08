import os
import re
import time
import random
import logging
import requests
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from pymongo import MongoClient

# --- DUMMY SERVER FOR RENDER ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Aegis Premium Bot is Alive!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# --- Import Data ---
try:
    from chat_data import CHAT_DATA, TRUTHS, DARES, RIZZ, ROASTS, SHAYARI, TRACE_WORDS, DESI_GIFS, ROB_GIFS_SUCCESS, ROB_GIFS_FAIL, BAN_GIFS, MUTE_GIFS
except ImportError:
    CHAT_DATA, TRUTHS, DARES, RIZZ, ROASTS, SHAYARI, TRACE_WORDS, DESI_GIFS = {}, [], [], [], [], {}, [], {}
    ROB_GIFS_SUCCESS, ROB_GIFS_FAIL, BAN_GIFS, MUTE_GIFS = [], [], [], []

# --- Logging Setup ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Database Setup ---
MONGO_URI = os.environ.get("MONGODB_URI")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

mongo_client = MongoClient(MONGO_URI)
db = mongo_client['aegis_db']
settings_col = db['settings']
filters_col = db['filters']
sticker_filters_col = db['sticker_filters']
warnings_col = db['warnings']
admins_col = db['custom_admins']
notes_col = db['notes']
badwords_col = db['badwords']
afk_col = db['afk']
chats_col = db['chats']
gbans_col = db['gbans']
users_col = db['users']

# --- Game Memories ---
ttt_games = {}
trace_games = {}

# --- Languages ---
LANGS = {
    "en": {
        "denied": "🚫 <b>Access Denied!</b> You Don't Have Enough Permissions.",
        "owner_respect": "👑 <b>Yes, Boss!</b> Executing your command. ⚡\n\n",
        "owner_protection": "🛑 <b>Access Denied!</b>\n\nNobody touches my Owner! 😡",
        "user_not_found": "❌ <b>Target Not Found!</b> Reply to a user.",
        "banned": "🔨 <b>BANNED!</b> {} has been removed. 🚫",
        "unbanned": "🕊️ {} has been unbanned. ✅",
        "kicked": "👢 <b>KICKED!</b> {} has been removed. 🚪",
        "muted": "🔇 <b>MUTED!</b> {} has been silenced. 🤐",
        "unmuted": "🔊 <b>UNMUTED!</b> {} can speak. 🗣️",
        "pinned": "📌 Message Pinned!",
        "unpinned": "📍 Message Unpinned!",
        "admin_error": "⚠️ <b>Error:</b> Failed. Is the bot an Admin with rights?",
        "lang_changed": "🌐 Language Changed To English! 🇬🇧"
    },
    "hi": {
        "denied": "🚫 <b>Permission Nahi Hai!</b>",
        "owner_respect": "👑 <b>Ji Huzoor!</b> Aapka hukum sar aankhon par. ⚡\n\n",
        "owner_protection": "🛑 <b>Access Denied!</b>\n\nMere Owner ko touch karne ki aukaat kisi mein nahi! 😡",
        "user_not_found": "❌ <b>Target Nahi Mila!</b> Kisi message ko reply karein.",
        "banned": "🔨 <b>BANNED!</b> {} ko nikal diya gaya. 🚫",
        "unbanned": "🕊️ {} ko unban kar diya gaya. ✅",
        "kicked": "👢 <b>KICKED!</b> {} ko nikal diya gaya. 🚪",
        "muted": "🔇 <b>MUTED!</b> {} ko chup karaya gaya. 🤐",
        "unmuted": "🔊 <b>UNMUTED!</b> {} ab bol sakta hai. 🗣️",
        "pinned": "📌 Message Pin Ho Gaya!",
        "unpinned": "📍 Message Unpin Ho Gaya!",
        "admin_error": "⚠️ <b>Error:</b> Fail. Kya bot Admin hai?",
        "lang_changed": "🌐 Language Hindi Mein Badli! 🇮🇳"
    }
}

def get_lang(chat_id):
    data = settings_col.find_one({"chat_id": chat_id})
    return data.get("lang", "en") if data else "en"

# --- Helpers ---
async def get_user_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == OWNER_ID: return 99
    chat_id = update.effective_chat.id
    data = admins_col.find_one({"chat_id": chat_id, "user_id": user_id})
    if data: return data.get("level", 0)
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']: return 2
    except: pass
    return 0

async def get_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        return update.message.reply_to_message.from_user
    if context.args:
        arg = context.args[0]
        try:
            if arg.isdigit() or (arg.startswith('-') and arg[1:].isdigit()):
                return await context.bot.get_chat(int(arg))
            else:
                if not arg.startswith('@'): arg = '@' + arg
                return await context.bot.get_chat(arg)
        except: return None
    return None

def extract_time(time_str):
    match = re.match(r'(\d+)([mhd])', time_str.lower())
    if not match: return None
    val, unit = int(match.group(1)), match.group(2)
    if unit == 'm': return timedelta(minutes=val)
    if unit == 'h': return timedelta(hours=val)
    if unit == 'd': return timedelta(days=val)
    return None

def get_chat_permissions():
    return ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True, can_send_polls=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True)

async def auto_unmute(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    try: await context.bot.restrict_chat_member(job.chat_id, job.data['user_id'], get_chat_permissions())
    except: pass

async def auto_unban(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    try: await context.bot.unban_chat_member(job.chat_id, job.data['user_id'])
    except: pass

def fetch_gif(action):
    try:
        url = f"https://nekos.best/api/v2/{action}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200: return res.json()["results"][0]["url"]
    except: pass
    return None

# --- Economy Helpers ---
def get_user_bal(user_id):
    if user_id == OWNER_ID: return "♾️ Unlimited"
    user = users_col.find_one({"user_id": user_id})
    if not user:
        users_col.insert_one({"user_id": user_id, "balance": 100, "last_daily": None})
        return 100
    return user.get("balance", 100)

def update_user_bal(user_id, amount):
    if user_id == OWNER_ID and amount < 0: return 
    users_col.update_one({"user_id": user_id}, {"$inc": {"balance": amount}}, upsert=True)

# --- Keyboards ---
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me To Your Group", url="https://t.me/aegis_manager_bot?startgroup=true")],
        [InlineKeyboardButton("🛡️ Moderation", callback_data="m_mod"), InlineKeyboardButton("🎮 Fun & Games", callback_data="m_fun")],
        [InlineKeyboardButton("👑 Admin Levels", callback_data="m_admin"), InlineKeyboardButton("💰 Economy", callback_data="m_eco")],
        [InlineKeyboardButton("📝 Notes", callback_data="m_notes"), InlineKeyboardButton("🚫 Blacklist", callback_data="m_badwords")],
        [InlineKeyboardButton("⚙️ Filters", callback_data="m_filter"), InlineKeyboardButton("🔒 Locks", callback_data="m_lock")],
        [InlineKeyboardButton("🌐 Language", callback_data="m_lang")]
    ])

def mod_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔨 Ban", callback_data="cmd_ban"), InlineKeyboardButton("👢 Kick", callback_data="cmd_kick")],
        [InlineKeyboardButton("🔇 Mute", callback_data="cmd_mute"), InlineKeyboardButton("🔊 Unmute", callback_data="cmd_unmute")],
        [InlineKeyboardButton("⚠️ Warn", callback_data="cmd_warn"), InlineKeyboardButton("📌 Pin", callback_data="cmd_pin")],
        [InlineKeyboardButton("🔙 Back", callback_data="m_main")]
    ])

def fun_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Truth", callback_data="cmd_t"), InlineKeyboardButton("🔥 Dare", callback_data="cmd_d")],
        [InlineKeyboardButton("💘 Rizz", callback_data="cmd_rizz"), InlineKeyboardButton("😂 Roast", callback_data="cmd_roast")],
        [InlineKeyboardButton("🫂 Hug", callback_data="cmd_hug"), InlineKeyboardButton("👋 Slap", callback_data="cmd_slap")],
        [InlineKeyboardButton("🖋️ Shayari", callback_data="m_shayari"), InlineKeyboardButton("🏃 Trace Game", callback_data="m_trace")],
        [InlineKeyboardButton("🔙 Back", callback_data="m_main")]
    ])

def shayari_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💔 Sad", callback_data="shayari_sad"), InlineKeyboardButton("❤️ Love", callback_data="shayari_love")],
        [InlineKeyboardButton("🥀 Broken", callback_data="shayari_broken"), InlineKeyboardButton("😊 Happy", callback_data="shayari_happy")],
        [InlineKeyboardButton("😈 Jealousy", callback_data="shayari_jealousy")],
        [InlineKeyboardButton("🔙 Back", callback_data="m_fun")]
    ])

def eco_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Balance", callback_data="cmd_bal"), InlineKeyboardButton("🎁 Daily", callback_data="cmd_daily")],
        [InlineKeyboardButton("💸 Transfer", callback_data="cmd_pay"), InlineKeyboardButton("🔪 Kill", callback_data="cmd_kill")],
        [InlineKeyboardButton("🕵️ Rob", callback_data="cmd_rob"), InlineKeyboardButton("🎲 Dice Bet", callback_data="cmd_bet")],
        [InlineKeyboardButton("✊ RPS Game", callback_data="cmd_rps"), InlineKeyboardButton("❌ Tic-Tac-Toe", callback_data="cmd_ttt")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="cmd_top")],
        [InlineKeyboardButton("🔙 Back", callback_data="m_main")]
    ])

# --- Callback Handlers ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    
    if data == "m_main": 
        await query.edit_message_text(
            "⚡ <b>Aegis Premium Panel</b> ⚡\n\n"
            "👑 <b>System Developer:</b> <code>Aman</code>\n"
            "🔥 <i>The Ultimate Architecture</i>\n\n"
            "👇 Select a category:", 
            reply_markup=main_menu(), parse_mode='HTML'
        )
    elif data == "m_mod": await query.edit_message_text("🛡️ <b>Moderation</b>", reply_markup=mod_menu(), parse_mode='HTML')
    elif data == "m_fun": await query.edit_message_text("🎮 <b>Fun & Games</b>", reply_markup=fun_menu(), parse_mode='HTML')
    elif data == "m_shayari": await query.edit_message_text("🖋️ <b>Shayari Menu</b>", reply_markup=shayari_menu(), parse_mode='HTML')
    elif data == "m_eco": await query.edit_message_text("💰 <b>Economy</b>", reply_markup=eco_menu(), parse_mode='HTML')
    elif data == "m_trace":
        await query.edit_message_text("🏃 <b>Word Trace Game</b>\n\nType <code>/trace</code> to start!", parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_fun")]]))
    
    elif data == "m_admin":
        text = "👑 <b>Admin Levels</b>\n\n<code>/promote @user 1</code> - Mod\n<code>/promote @user 2</code> - Admin\n<code>/promote @user 3</code> - Co-Owner\n<code>/demote @user</code>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_main")]]), parse_mode='HTML')
    elif data == "m_notes":
        text = "📝 <b>Notes</b>\n\n<code>/save name text</code>\n<code>/get name</code>\n<code>/notes</code>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_main")]]), parse_mode='HTML')
    elif data == "m_badwords":
        text = "🚫 <b>Blacklist</b>\n\n<code>/addbadword word</code>\n<code>/delbadword word</code>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_main")]]), parse_mode='HTML')
    elif data == "m_filter":
        text = "⚙️ <b>Filters</b>\n\n<code>/addfilter word -&gt; reply</code>\n<code>/delfilter word</code>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_main")]]), parse_mode='HTML')
    elif data == "m_lock":
        text = "🔒 <b>Locks</b>\n\n<code>/lock</code> / <code>/unlock</code>\n<code>/lockstickers</code> / <code>/unlockstickers</code>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_main")]]), parse_mode='HTML')
    elif data == "m_lang":
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("English 🇬🇧", callback_data="setlang_en"), InlineKeyboardButton("Hindi 🇮🇳", callback_data="setlang_hi")],
            [InlineKeyboardButton("🔙 Back", callback_data="m_main")]
        ])
        await query.edit_message_text("🌐 <b>Select Language</b>", reply_markup=markup, parse_mode='HTML')
    elif data.startswith("setlang_"):
        lang = data.split("_")[1]
        settings_col.update_one({"chat_id": chat_id}, {"$set": {"lang": lang}}, upsert=True)
        await query.edit_message_text(LANGS[lang]["lang_changed"], reply_markup=main_menu(), parse_mode='HTML')
    
    elif data.startswith("shayari_"):
        category = data.split("_")[1]
        shayari_text = random.choice(SHAYARI.get(category, ["Shayari Nahi Mili."]))
        await query.edit_message_text(f"🖋️ <b>{category.capitalize()} Shayari:</b>\n\n<i>{shayari_text}</i>", reply_markup=shayari_menu(), parse_mode='HTML')

    elif data == "cmd_ban": await query.edit_message_text("Reply: <code>/ban</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_mod")]]), parse_mode='HTML')
    elif data == "cmd_kick": await query.edit_message_text("Reply: <code>/kick</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_mod")]]), parse_mode='HTML')
    elif data == "cmd_mute": await query.edit_message_text("Reply: <code>/mute</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_mod")]]), parse_mode='HTML')
    elif data == "cmd_unmute": await query.edit_message_text("Reply: <code>/unmute</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_mod")]]), parse_mode='HTML')
    elif data == "cmd_warn": await query.edit_message_text("Reply: <code>/warn</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_mod")]]), parse_mode='HTML')
    elif data == "cmd_pin": await query.edit_message_text("Reply: <code>/pin</code> or <code>/unpin</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_mod")]]), parse_mode='HTML')
    elif data == "cmd_t": await query.edit_message_text("Type: <code>/t</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_fun")]]), parse_mode='HTML')
    elif data == "cmd_d": await query.edit_message_text("Type: <code>/d</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_fun")]]), parse_mode='HTML')
    elif data == "cmd_rizz": await query.edit_message_text("Type: <code>/rizz</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_fun")]]), parse_mode='HTML')
    elif data == "cmd_roast": await query.edit_message_text("Type: <code>/roast</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_fun")]]), parse_mode='HTML')
    elif data == "cmd_hug": await query.edit_message_text("Reply: <code>/hug</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_fun")]]), parse_mode='HTML')
    elif data == "cmd_slap": await query.edit_message_text("Reply: <code>/slap</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_fun")]]), parse_mode='HTML')
    elif data == "cmd_bal": await query.edit_message_text("Type: <code>/bal</code> (Or Reply)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_daily": await query.edit_message_text("Type: <code>/daily</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_pay": await query.edit_message_text("Usage: Reply with <code>/pay 100</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_kill": await query.edit_message_text("Reply: <code>/kill</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_rob": await query.edit_message_text("Usage: Reply with <code>/rob 100</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_bet": await query.edit_message_text("Type: <code>/bet 100 dice</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_rps": await query.edit_message_text("Type: <code>/rps 100</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_ttt": await query.edit_message_text("Type: <code>/ttt</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_top": await query.edit_message_text("Type: <code>/top</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')

    # Games Logic
    elif data.startswith("rps_"):
        parts = data.split("_")
        user_choice = parts[1]
        bet = int(parts[2])
        bal = get_user_bal(user_id)
        
        if bal != "♾️ Unlimited" and bal < bet:
            return await query.edit_message_text("❌ Insufficient Funds!")
            
        bot_choice = random.choice(["rock", "paper", "scissors"])
        
        if user_choice == bot_choice:
            result = "🤝 <b>TIE!</b> Money returned."
        elif (user_choice == "rock" and bot_choice == "scissors") or \
             (user_choice == "paper" and bot_choice == "rock") or \
             (user_choice == "scissors" and bot_choice == "paper"):
            update_user_bal(user_id, bet)
            result = f"🎉 <b>You Won!</b> Earned ${bet}."
        else:
            update_user_bal(user_id, -bet)
            result = f"😭 <b>You Lost!</b> Lost ${bet}."
            
        await query.edit_message_text(f"You: {user_choice.upper()} | Bot: {bot_choice.upper()}\n\n{result}", parse_mode='HTML')

    elif data.startswith("rpspvp_"):
        parts = data.split("_")
        p2_choice = parts[1]
        bet = int(parts[2])
        p1_id = int(parts[3])
        p2_id = int(parts[4])
        
        if query.from_user.id != p2_id:
            return await query.answer("This challenge is not for you!", show_alert=True)
            
        if get_user_bal(p1_id) < bet or get_user_bal(p2_id) < bet:
            return await query.answer("One player lacks funds!", show_alert=True)
            
        p1_choice = random.choice(["rock", "paper", "scissors"])
        p1_name = "Challenger"
        p2_name = query.from_user.first_name
        
        if p1_choice == p2_choice:
            result = "🤝 <b>TIE!</b> Money returned."
        elif (p1_choice == "rock" and p2_choice == "scissors") or \
             (p1_choice == "paper" and p2_choice == "rock") or \
             (p1_choice == "scissors" and p2_choice == "paper"):
            update_user_bal(p1_id, bet)
            update_user_bal(p2_id, -bet)
            result = f"🏆 <b>Challenger Won!</b>\nChoice: {p1_choice.upper()}\nLost ${bet}."
        else:
            update_user_bal(p1_id, -bet)
            update_user_bal(p2_id, bet)
            result = f"🎉 <b>You Won!</b>\nChoice: {p1_choice.upper()}\nEarned ${bet}."
            
        await query.edit_message_text(f"⚔️ <b>PvP Result</b>\n\n{p2_name}: {p2_choice.upper()}\n{p1_name}: {p1_choice.upper()}\n\n{result}", parse_mode='HTML')

    elif data.startswith("ttt_"):
        parts = data.split("_")
        idx = int(parts[1])
        
        if chat_id not in ttt_games:
            return await query.answer("Game Over! Start a new one with /ttt", show_alert=True)
            
        board, turn = ttt_games[chat_id]
        if board[idx] != "⬜":
            return await query.answer("Spot already taken!", show_alert=True)
            
        board[idx] = "❌"
        ttt_games[chat_id] = (board, "O")
        
        if check_win(board, "❌"):
            del ttt_games[chat_id]
            update_user_bal(user_id, 200)
            return await query.edit_message_text(f"🎉 <b>You beat the Bot!</b> Reward: $200", parse_mode='HTML')
            
        empty_spots = [i for i, val in enumerate(board) if val == "⬜"]
        if empty_spots:
            bot_idx = random.choice(empty_spots)
            board[bot_idx] = "⭕"
            ttt_games[chat_id] = (board, "❌")
            
            if check_win(board, "⭕"):
                del ttt_games[chat_id]
                update_user_bal(user_id, -100)
                return await query.edit_message_text(f"🤖 <b>Bot beat you!</b> Lost $100.", parse_mode='HTML', reply_markup=generate_ttt_board(board))
        
        if not empty_spots:
            del ttt_games[chat_id]
            return await query.edit_message_text("🤝 <b>Tie!</b> No money lost.", parse_mode='HTML', reply_markup=generate_ttt_board(board))
            
        await query.edit_message_text("Your turn! (You are ❌)", reply_markup=generate_ttt_board(board))

def check_win(board, player):
    wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    for w in wins:
        if board[w[0]] == board[w[1]] == board[w[2]] == player:
            return True
    return False

def generate_ttt_board(board):
    keyboard = []
    for i in range(0, 9, 3):
        keyboard.append([
            InlineKeyboardButton(board[i], callback_data=f"ttt_{i}"),
            InlineKeyboardButton(board[i+1], callback_data=f"ttt_{i+1}"),
            InlineKeyboardButton(board[i+2], callback_data=f"ttt_{i+2}")
        ])
    return InlineKeyboardMarkup(keyboard)

# --- Core Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chats_col.update_one({"chat_id": update.effective_chat.id}, {"$set": {"chat_id": update.effective_chat.id}}, upsert=True)
    text = (
        "⚡ <b>Aegis Premium Panel</b> ⚡\n\n"
        "👑 <b>System Developer:</b> <code>Aman</code>\n"
        "🔥 <i>The Ultimate Architecture</i>\n\n"
        "👇 Select a category below:"
    )
    await update.message.reply_text(text, reply_markup=main_menu(), parse_mode='HTML')

async def set_lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return await update.message.reply_text("🚫 Admin Only.")
    if not context.args or context.args[0] not in ['en', 'hi']: return await update.message.reply_text("Usage: <code>/setlang en</code> or <code>/setlang hi</code>", parse_mode='HTML')
    lang = context.args[0]
    settings_col.update_one({"chat_id": update.effective_chat.id}, {"$set": {"lang": lang}}, upsert=True)
    await update.message.reply_text(LANGS[lang]["lang_changed"], parse_mode='HTML')

# --- Trace Game ---
async def trace_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in trace_games:
        return await update.message.reply_text("❌ A game is already running!")
        
    word = random.choice(TRACE_WORDS)
    word_list = list(word)
    random.shuffle(word_list)
    scrambled = "".join(word_list)
    
    trace_games[chat_id] = word
    
    await update.message.reply_text(
        f"🏃 <b>WORD TRACE!</b> 🏃\n\n"
        f"Unscramble this word:\n"
        f"👉 <code>{scrambled}</code> 👈\n\n"
        f"First to answer gets <b>$200</b>! (60s)",
        parse_mode='HTML'
    )
    context.job_queue.run_once(trace_timeout, 60, chat_id=chat_id)

async def trace_timeout(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    if chat_id in trace_games:
        del trace_games[chat_id]
        await context.bot.send_message(chat_id, "⏰ <b>Time Over!</b> Game cancelled.", parse_mode='HTML')

# --- Owner Panel ---
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("🚫 Owner Only Command!")
    total_chats = chats_col.count_documents({})
    text = f"👑 <b>Welcome Boss</b> 👑\n\n📊 <b>Total Groups:</b> {total_chats}\n💰 <b>Balance:</b> ♾️ Unlimited\n⚡ <b>Status:</b> God Mode Active\n\n<b>Commands:</b>\n<code>/broadcast &lt;msg&gt;</code>\n<code>/gban (reply)</code>"
    await update.message.reply_text(text, parse_mode='HTML')

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not context.args: return await update.message.reply_text("Usage: /broadcast message")
    msg = " ".join(context.args)
    chats = chats_col.find()
    success, fail = 0, 0
    status_msg = await update.message.reply_text("📢 <b>Broadcasting...</b>", parse_mode='HTML')
    
    for chat in chats:
        try:
            await context.bot.send_message(chat['chat_id'], f"📢 <b>ANNOUNCEMENT:</b>\n\n{msg}", parse_mode='HTML')
            success += 1
        except: fail += 1
        
    await status_msg.edit_text(f"✅ <b>Broadcast Complete!</b>\n\nSuccess: {success}\nFailed: {fail}", parse_mode='HTML')

async def gban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    target = await get_target(update, context)
    if not target: return await update.message.reply_text("Reply to a user to GBAN.")
    gbans_col.insert_one({"user_id": target.id})
    chats = chats_col.find()
    for chat in chats:
        try: await context.bot.ban_chat_member(chat['chat_id'], target.id)
        except: pass
    await update.message.reply_text(f"🔨 <b>GBANNED!</b> {target.first_name}", parse_mode='HTML')

# --- Economy & Betting ---
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
    bal = get_user_bal(target.id)
    if target.id == update.effective_user.id:
        await update.message.reply_text(f"💰 <b>{target.first_name}</b>, Balance: <b>{bal}</b>", parse_mode='HTML')
    else:
        await update.message.reply_text(f"💰 <b>{target.first_name}</b>'s Balance: <b>{bal}</b>", parse_mode='HTML')

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_col.find_one({"user_id": user_id})
    now = datetime.utcnow()
    
    if user and user.get("last_daily"):
        last_daily = user["last_daily"]
        if now - last_daily < timedelta(hours=24):
            time_left = timedelta(hours=24) - (now - last_daily)
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return await update.message.reply_text(f"⏳ Wait {hours}h {minutes}m for next daily.")
    
    update_user_bal(user_id, 500)
    users_col.update_one({"user_id": user_id}, {"$set": {"last_daily": now}}, upsert=True)
    await update.message.reply_text(f"🎁 <b>Daily Claimed!</b>\nEarned $500. Total: {get_user_bal(user_id)}", parse_mode='HTML')

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await get_target(update, context)
    if not target: return await update.message.reply_text("Reply to a user to pay.")
    if not context.args or len(context.args) < 1:
        return await update.message.reply_text("Usage: Reply with `/pay 100`")
    try: amount = int(context.args[0])
    except: return await update.message.reply_text("Invalid amount.")
    
    if amount <= 0: return await update.message.reply_text("Amount must be positive.")
    
    if update.effective_user.id != OWNER_ID:
        if get_user_bal(update.effective_user.id) < amount:
            return await update.message.reply_text("❌ Insufficient funds!")
        
    update_user_bal(update.effective_user.id, -amount)
    update_user_bal(target.id, amount)
    await update.message.reply_text(f"💸 <b>Transferred!</b>\n{update.effective_user.first_name} sent ${amount} to {target.first_name}.", parse_mode='HTML')

async def bet_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return await update.message.reply_text("Usage: <code>/bet 100 dice</code>")
    try: amount = int(context.args[0])
    except: return await update.message.reply_text("Invalid amount.")
    game_type = context.args[1].lower()
    
    if game_type not in ['dice', 'dart', 'basket', 'bowling']:
        return await update.message.reply_text("Allowed: dice, dart, basket, bowling")
        
    if update.effective_user.id != OWNER_ID and get_user_bal(update.effective_user.id) < amount:
        return await update.message.reply_text("❌ Insufficient funds!")
        
    update_user_bal(update.effective_user.id, -amount)
    msg = await context.bot.send_dice(update.effective_chat.id, emoji=game_type)
    await asyncio.sleep(4) 
    
    value = msg.dice.value
    win = False
    if game_type == 'dice' and value >= 4: win = True
    elif game_type == 'dart' and value >= 4: win = True
    elif game_type == 'basket' and value >= 4: win = True
    elif game_type == 'bowling' and value == 6: win = True
    
    if win:
        update_user_bal(update.effective_user.id, amount * 2)
        await update.message.reply_text(f"🎉 <b>You Won!</b> Result: {value}. Earned ${amount*2}.", parse_mode='HTML')
    else:
        await update.message.reply_text(f"😭 <b>You Lost!</b> Result: {value}. Lost ${amount}.", parse_mode='HTML')

async def rob_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await get_target(update, context)
    if not target: return await update.message.reply_text("Reply to a user to rob.")
    if not context.args:
        return await update.message.reply_text("Usage: Reply with `/rob <amount>`")
    
    try: amount = int(context.args[0])
    except: return await update.message.reply_text("Invalid amount.")
    
    if amount <= 0: return await update.message.reply_text("Amount must be positive.")
    if target.id == update.effective_user.id: return await update.message.reply_text("You cannot rob yourself!")
    
    if get_user_bal(update.effective_user.id) < amount:
        return await update.message.reply_text("❌ You don't have that much money to risk!")
        
    if get_user_bal(target.id) < amount:
        return await update.message.reply_text("😂 Target doesn't have that much money!")

    success = random.choice([True, False])
    if success:
        gif = random.choice(ROB_GIFS_SUCCESS)
        update_user_bal(target.id, -amount)
        update_user_bal(update.effective_user.id, amount)
        caption = f"🕵️‍♂️ <b>ROBBED!</b>\n\n{update.effective_user.first_name} stole ${amount} from {target.first_name}!"
    else:
        gif = random.choice(ROB_GIFS_FAIL)
        update_user_bal(update.effective_user.id, -amount)
        update_user_bal(target.id, amount)
        caption = f"🚨 <b>CAUGHT!</b>\n\n{update.effective_user.first_name} failed to rob {target.first_name} and paid ${amount} as a fine!"
        
    await update.message.reply_animation(animation=gif, caption=caption, parse_mode='HTML')

async def kill_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await get_target(update, context)
    if not target: return await update.message.reply_text("Reply to a user to kill.")
    if target.id == update.effective_user.id: return await update.message.reply_text("Suicide is not allowed!")
    if get_user_bal(update.effective_user.id) < 50:
        return await update.message.reply_text("❌ Need $50 to attempt a kill.")
    
    update_user_bal(update.effective_user.id, -50)
    success = random.choice([True, False])
    if success:
        gif = fetch_gif("kill") or "https://media.tenor.com/B8J4vI8q4AAAAAC/thor-hammer.gif"
        update_user_bal(update.effective_user.id, 100)
        caption = f"☠️ <b>KILLED!</b>\n\n{update.effective_user.first_name} killed {target.first_name}!\n💰 Reward: $100"
    else:
        gif = fetch_gif("cry") or "https://media.tenor.com/M8J4vI8q4AAAAAC/shut-up.gif"
        caption = f"😂 <b>MISSED!</b>\n\n{update.effective_user.first_name} missed the attack!\n💸 Lost $50."
        
    await update.message.reply_animation(animation=gif, caption=caption, parse_mode='HTML')

async def rps_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Usage: <code>/rps 100</code>")
    try: bet = int(context.args[0])
    except: return await update.message.reply_text("Invalid amount.")
    
    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    
    if opponent and opponent.id != challenger.id:
        if update.effective_user.id != OWNER_ID and get_user_bal(challenger.id) < bet:
            return await update.message.reply_text("❌ Insufficient funds!")
            
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪨 Rock", callback_data=f"rpspvp_rock_{bet}_{challenger.id}_{opponent.id}"), 
             InlineKeyboardButton("📄 Paper", callback_data=f"rpspvp_paper_{bet}_{challenger.id}_{opponent.id}")],
            [InlineKeyboardButton("✂️ Scissors", callback_data=f"rpspvp_scissors_{bet}_{challenger.id}_{opponent.id}")]
        ])
        await update.message.reply_text(f"⚔️ <b>PvP Challenge!</b>\n\n{challenger.first_name} challenged {opponent.first_name} for ${bet}!\n\n{opponent.first_name}, choose:", reply_markup=markup, parse_mode='HTML')
    else:
        if update.effective_user.id != OWNER_ID and get_user_bal(challenger.id) < bet:
            return await update.message.reply_text("❌ Insufficient funds!")
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪨 Rock", callback_data=f"rps_rock_{bet}"), InlineKeyboardButton("📄 Paper", callback_data=f"rps_paper_{bet}")],
            [InlineKeyboardButton("✂️ Scissors", callback_data=f"rps_scissors_{bet}")]
        ])
        await update.message.reply_text(f"✊ <b>RPS (vs Bot)</b>\nBet: ${bet}\nChoose:", reply_markup=markup, parse_mode='HTML')

async def ttt_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id in ttt_games:
        return await update.message.reply_text("Game already running!")
        
    board = ["⬜"] * 9
    ttt_games[update.effective_chat.id] = (board, "❌")
    await update.message.reply_text("❌ <b>Tic-Tac-Toe (vs Bot)</b>\nYour turn:", reply_markup=generate_ttt_board(board), parse_mode='HTML')

async def top_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = list(users_col.find().sort("balance", -1).limit(10))
    if not top_users: return await update.message.reply_text("No data yet!")
    
    text = "🏆 <b>GLOBAL LEADERBOARD</b> 🏆\n\n"
    for i, user in enumerate(top_users, 1):
        try:
            u = await context.bot.get_chat(user['user_id'])
            name = u.first_name
        except:
            name = f"User_{user['user_id']}"
        text += f"{i}. {name} - ${user['balance']}\n"
        
    await update.message.reply_text(text, parse_mode='HTML')

# --- Moderation Commands ---
async def pin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 2: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to a message to pin.")
    try:
        await context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
        await update.message.reply_text(LANGS[lang]["pinned"], parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def unpin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 2: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to a message to unpin.")
    try:
        await context.bot.unpin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
        await update.message.reply_text(LANGS[lang]["unpinned"], parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    role = await get_user_level(update, context)
    if role < 2: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    if target.id == OWNER_ID: return await update.message.reply_text(LANGS[lang]["owner_protection"], parse_mode='HTML')

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        prefix = LANGS[lang]["owner_respect"] if role == 99 else ""
        caption = f"{prefix}{LANGS[lang]['banned'].format(target.first_name)}"
        if BAN_GIFS: await update.message.reply_animation(animation=random.choice(BAN_GIFS), caption=caption, parse_mode='HTML')
        else: await update.message.reply_text(caption, parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}. Is Bot Admin?")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 2: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(LANGS[lang]['unbanned'].format(target.first_name), parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 2: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    if target.id == OWNER_ID: return await update.message.reply_text(LANGS[lang]["owner_protection"], parse_mode='HTML')
    
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)
        caption = LANGS[lang]['kicked'].format(target.first_name)
        if BAN_GIFS: await update.message.reply_animation(animation=random.choice(BAN_GIFS), caption=caption, parse_mode='HTML')
        else: await update.message.reply_text(caption, parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 1: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    if target.id == OWNER_ID: return await update.message.reply_text(LANGS[lang]["owner_protection"], parse_mode='HTML')
    
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, ChatPermissions(can_send_messages=False))
        caption = LANGS[lang]['muted'].format(target.first_name)
        if MUTE_GIFS: await update.message.reply_animation(animation=random.choice(MUTE_GIFS), caption=caption, parse_mode='HTML')
        else: await update.message.reply_text(caption, parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 1: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, get_chat_permissions())
        await update.message.reply_text(LANGS[lang]['unmuted'].format(target.first_name), parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def tmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 1: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target or len(context.args) < 1: return await update.message.reply_text("Usage: <code>/tmute 10m</code>")
    time_delta = extract_time(context.args[0])
    if not time_delta: return await update.message.reply_text("Invalid time. Use 10m, 1h, 1d.")
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"⏱️ {target.first_name} muted for {context.args[0]}.", parse_mode='HTML')
        context.job_queue.run_once(auto_unmute, time_delta, chat_id=update.effective_chat.id, data={'user_id': target.id})
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def tban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 2: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target or len(context.args) < 1: return await update.message.reply_text("Usage: <code>/tban 1d</code>")
    time_delta = extract_time(context.args[0])
    if not time_delta: return await update.message.reply_text("Invalid time.")
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(f"⏱️ {target.first_name} banned for {context.args[0]}.", parse_mode='HTML')
        context.job_queue.run_once(auto_unban, time_delta, chat_id=update.effective_chat.id, data={'user_id': target.id})
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 1: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    if target.id == OWNER_ID: return await update.message.reply_text(LANGS[lang]["owner_protection"], parse_mode='HTML')
    
    chat_id, user_id = update.effective_chat.id, target.id
    data = warnings_col.find_one({"chat_id": chat_id, "user_id": user_id})
    new_count = (data.get("count", 0) + 1) if data else 1
    if data: warnings_col.update_one({"_id": data["_id"]}, {"$set": {"count": new_count}})
    else: warnings_col.insert_one({"chat_id": chat_id, "user_id": user_id, "count": new_count})
    await update.message.reply_text(f"⚠️ {target.first_name} warned! ({new_count}/3)", parse_mode='HTML')
    if new_count >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await update.message.reply_text(f"💀 {target.first_name} banned for 3 warnings!", parse_mode='HTML')
            warnings_col.delete_one({"chat_id": chat_id, "user_id": user_id})
        except: pass

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 3: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target or len(context.args) < 1: return await update.message.reply_text("Usage: <code>/promote @user 1</code> (1: Mod, 2: Admin, 3: Co-Owner)", parse_mode='HTML')
    
    try: level = int(context.args[0]) if context.args[0].isdigit() else int(context.args[1]) # Handle reply or username
    except:
        level = 1 # default

    try:
        # Give actual Telegram Admin Rights
        await context.bot.promote_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.id,
            can_change_info=True if level >= 2 else False,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True if level >= 2 else False,
            can_pin_messages=True if level >= 2 else False,
            can_promote_members=True if level == 3 else False
        )
        # Save custom level in DB
        admins_col.update_one({"chat_id": update.effective_chat.id, "user_id": target.id}, {"$set": {"level": level}}, upsert=True)
        await update.message.reply_text(f"✅ {target.first_name} promoted to Level {level} with Admin Rights!", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to promote. Error: {e}")

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 3: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    
    try:
        await context.bot.promote_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.id,
            can_change_info=False, can_delete_messages=False, can_invite_users=False,
            can_restrict_members=False, can_pin_messages=False, can_promote_members=False
        )
        admins_col.delete_one({"chat_id": update.effective_chat.id, "user_id": target.id})
        await update.message.reply_text(f"📉 {target.first_name} demoted!", parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def purge_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    if not update.message.reply_to_message: return
    message_id, current_id = update.message.reply_to_message.message_id, update.message.message_id
    deleted = 0
    for msg_id in range(message_id, current_id + 1):
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            deleted += 1
        except: pass
    await context.bot.send_message(update.effective_chat.id, f"🧹 Deleted {deleted} messages.")

async def del_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 1: return
    if not update.message.reply_to_message: return
    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()
    except: pass

# --- Locks ---
async def lock_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    try:
        await context.bot.set_chat_permissions(update.effective_chat.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text("🔒 Group Locked! (Only Admins can speak)")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}. Bot needs 'Manage Permissions' right.")

async def unlock_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    try:
        await context.bot.set_chat_permissions(update.effective_chat.id, get_chat_permissions())
        await update.message.reply_text("🔓 Group Unlocked!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}. Bot needs 'Manage Permissions' right.")

async def lock_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    settings_col.update_one({"chat_id": update.effective_chat.id}, {"$set": {"stickers_locked": True}}, upsert=True)
    await update.message.reply_text("🔒 Stickers Locked!")

async def unlock_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    settings_col.update_one({"chat_id": update.effective_chat.id}, {"$set": {"stickers_locked": False}}, upsert=True)
    await update.message.reply_text("🔓 Stickers Unlocked!")

# --- Fun, Desi & Action Commands ---
async def truth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    truth = random.choice(TRUTHS)
    if target: await update.message.reply_text(f"🎯 <b>Truth for {target.first_name}:</b>\n\n{truth}", parse_mode='HTML')
    else: await update.message.reply_text(f"🎯 <b>Truth:</b>\n\n{truth}", parse_mode='HTML')

async def dare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    dare = random.choice(DARES)
    if target: await update.message.reply_text(f"🔥 <b>Dare for {target.first_name}:</b>\n\n{dare}", parse_mode='HTML')
    else: await update.message.reply_text(f"🔥 <b>Dare:</b>\n\n{dare}", parse_mode='HTML')

async def rizz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    rizz = random.choice(RIZZ)
    if target: await update.message.reply_text(f"💘 {update.effective_user.first_name} to {target.first_name}:\n\n<i>{rizz}</i>", parse_mode='HTML')
    else: await update.message.reply_text(f"💘 <i>{rizz}</i>", parse_mode='HTML')

async def roast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    roast = random.choice(ROASTS)
    if target: await update.message.reply_text(f"😂 <b>{target.first_name}</b>, {roast}", parse_mode='HTML')
    else: await update.message.reply_text(f"😂 {roast}", parse_mode='HTML')

async def action_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, action_name):
    if not update.message.reply_to_message: return await update.message.reply_text(f"Reply to someone with /{action_name}")
    target = update.message.reply_to_message.from_user
    user = update.effective_user.first_name
    
    # Check hardcoded GIFs first
    gif_url = DESI_GIFS.get(action_name) or fetch_gif(action_name)
    caption = f"✨ <b>{user}</b> {action_name}ed <b>{target.first_name}</b>! 😂"
    
    if gif_url: await update.message.reply_animation(animation=gif_url, caption=caption, parse_mode='HTML')
    else: await update.message.reply_text(caption, parse_mode='HTML')

async def hug_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "hug")
async def slap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "slap")
async def kiss_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "kiss")
async def punch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "punch")
async def pat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "pat")

async def bhai_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "bhai")
async def bhen_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "bhen")
async def pyar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "pyar")
async def gussa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "gussa")
async def dost_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "dost")
async def dushman_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "dushman")
async def nacho_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "nacho")
async def chappal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "chappal")
async def jhadu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "jhadu")
async def belan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "belan")
async def tamacha_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "tamacha")
async def lathi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "lathi")
async def kela_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "kela")
async def chai_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "chai")
async def mirchi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "mirchi")
async def dhoka_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "dhoka")
async def kamra_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE): await action_cmd(update, context, "kamra")

async def shayari_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🖋️ <b>Shayari Menu</b>", reply_markup=shayari_menu(), parse_mode='HTML')

# --- Settings, Notes, Filters ---
async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    if len(context.args) < 2: return await update.message.reply_text("Usage: <code>/save name text</code>", parse_mode='HTML')
    notes_col.update_one({"chat_id": update.effective_chat.id, "name": context.args[0].lower()}, {"$set": {"text": " ".join(context.args[1:])}}, upsert=True)
    await update.message.reply_text(f"✅ Note saved!")

async def get_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    data = notes_col.find_one({"chat_id": update.effective_chat.id, "name": context.args[0].lower()})
    if data: await update.message.reply_text(data['text'])
    else: await update.message.reply_text("❌ Note not found.")

async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    if "->" not in update.message.text: return await update.message.reply_text("Format: <code>/addfilter hello -&gt; Hi!</code>", parse_mode='HTML')
    parts = update.message.text.split("->", 1)
    trigger = parts[0].replace("/addfilter", "").strip().lower()
    filters_col.update_one({"chat_id": update.effective_chat.id, "trigger": trigger}, {"$set": {"reply": parts[1].strip()}}, upsert=True)
    await update.message.reply_text(f"✅ Filter added for <code>{trigger}</code>")

async def add_badword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2 or not context.args: return
    badwords_col.update_one({"chat_id": update.effective_chat.id, "word": context.args[0].lower()}, {"$set": {"word": context.args[0].lower()}}, upsert=True)
    await update.message.reply_text(f"✅ Blacklisted.")

# --- Message Handlers ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = settings_col.find_one({"chat_id": update.effective_chat.id})
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        welcome = data.get("welcome_text", "Welcome {name}! 👋").replace("{name}", member.first_name) if data else f"Welcome {member.first_name}! 👋"
        media = data.get("welcome_media") if data else None
        media_type = data.get("media_type") if data else None
        
        if media and media_type == "animation": await update.message.reply_animation(animation=media, caption=welcome)
        elif media and media_type == "photo": await update.message.reply_photo(photo=media, caption=welcome)
        else: await update.message.reply_text(welcome)
        
        if data and "rules" in data: await update.message.reply_text(f"📜 <b>Rules:</b>\n{data['rules']}", parse_mode='HTML')

async def handle_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = settings_col.find_one({"chat_id": chat_id})
    if data and data.get("stickers_locked", False):
        if await get_user_level(update, context) < 1:
            try:
                await update.message.delete()
                await update.message.reply_text("🔒 Stickers Locked!")
            except: pass

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat_id, user_id = update.effective_chat.id, update.effective_user.id
    text_upper = update.message.text.upper()
    text_lower = update.message.text.lower()

    # Trace Game Check
    if chat_id in trace_games:
        if text_upper == trace_games[chat_id]:
            del trace_games[chat_id]
            update_user_bal(user_id, 200)
            return await update.message.reply_text(f"🎉 <b>CORRECT!</b>\n\n{update.effective_user.first_name} won $200!", parse_mode='HTML')

    # Reaction System
    try:
        if any(word in text_lower for word in ["haha", "lol", "😂"]): await update.message.set_reaction("😂")
        elif any(word in text_lower for word in ["sad", "rona", "😭"]): await update.message.set_reaction("🥺")
        elif any(word in text_lower for word in ["gali", "bc", "mc"]): await update.message.set_reaction("🤮")
        elif any(word in text_lower for word in ["love", "pyar", "❤️"]): await update.message.set_reaction("❤️")
        elif any(word in text_lower for word in ["gussa", "angry", "😡"]): await update.message.set_reaction("🤬")
    except: pass

    # Anti-link & Badwords (for non-admins)
    if await get_user_level(update, context) < 1:
        if "http://" in text_lower or "https://" in text_lower or "t.me/" in text_lower:
            try:
                await update.message.delete()
                await update.message.reply_text(f"⚠️ {update.effective_user.first_name}, Links not allowed!")
                return
            except: pass
            
        # Badwords check
        badwords = badwords_col.find({"chat_id": chat_id})
        for bw in badwords:
            if bw['word'] in text_lower:
                try:
                    await update.message.delete()
                    await update.message.reply_text("🚫 Bad word detected!")
                    return
                except: pass

    # Chat Data Check
    for trigger, replies in CHAT_DATA.items():
        if text_lower == trigger:
            if random.random() < 0.5: # 50% chance to reply
                return await update.message.reply_text(random.choice(replies))

# --- Main App ---
async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "Start Bot"), BotCommand("balance", "Check Money"), BotCommand("daily", "Claim Daily $500"),
        BotCommand("pay", "Transfer Money"), BotCommand("rob", "Rob a user"), BotCommand("kill", "Kill a user"), BotCommand("bet", "Bet On Dice"),
        BotCommand("rps", "Rock Paper Scissors"), BotCommand("ttt", "Tic-Tac-Toe"), BotCommand("trace", "Word Trace Game"),
        BotCommand("top", "Leaderboard"), BotCommand("ban", "Ban"), BotCommand("kick", "Kick"), BotCommand("mute", "Mute"),
        BotCommand("t", "Truth"), BotCommand("d", "Dare"), BotCommand("roast", "Roast"), BotCommand("shayari", "Shayari Menu"),
        BotCommand("chappal", "Chappal Maaro"), BotCommand("bhai", "Bhai Wali Vibe")
    ]
    await application.bot.set_my_commands(commands)

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("setlang", set_lang_cmd))
    app.add_handler(CommandHandler("owner", owner_panel))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("gban", gban_user))
    
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("bal", balance))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("pay", pay))
    app.add_handler(CommandHandler("rob", rob_user))
    app.add_handler(CommandHandler("kill", kill_user))
    app.add_handler(CommandHandler("bet", bet_dice))
    app.add_handler(CommandHandler("rps", rps_game))
    app.add_handler(CommandHandler("ttt", ttt_game))
    app.add_handler(CommandHandler("trace", trace_game))
    app.add_handler(CommandHandler("top", top_group))
    app.add_handler(CommandHandler("globaltop", top_group))
    
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("kick", kick_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("tmute", tmute_user))
    app.add_handler(CommandHandler("tban", tban_user))
    app.add_handler(CommandHandler("pin", pin_message))
    app.add_handler(CommandHandler("unpin", unpin_message))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("promote", promote_user))
    app.add_handler(CommandHandler("demote", demote_user))
    app.add_handler(CommandHandler("purge", purge_messages))
    app.add_handler(CommandHandler("del", del_message))
    app.add_handler(CommandHandler("lock", lock_group))
    app.add_handler(CommandHandler("unlock", unlock_group))
    app.add_handler(CommandHandler("lockstickers", lock_stickers))
    app.add_handler(CommandHandler("unlockstickers", unlock_stickers))
    
    app.add_handler(CommandHandler("t", truth_cmd))
    app.add_handler(CommandHandler("d", dare_cmd))
    app.add_handler(CommandHandler("rizz", rizz_cmd))
    app.add_handler(CommandHandler("roast", roast_cmd))
    app.add_handler(CommandHandler("hug", hug_cmd))
    app.add_handler(CommandHandler("slap", slap_cmd))
    app.add_handler(CommandHandler("kiss", kiss_cmd))
    app.add_handler(CommandHandler("punch", punch_cmd))
    app.add_handler(CommandHandler("pat", pat_cmd))
    
    # Desi Commands
    app.add_handler(CommandHandler("bhai", bhai_cmd))
    app.add_handler(CommandHandler("bhen", bhen_cmd))
    app.add_handler(CommandHandler("pyar", pyar_cmd))
    app.add_handler(CommandHandler("gussa", gussa_cmd))
    app.add_handler(CommandHandler("dost", dost_cmd))
    app.add_handler(CommandHandler("dushman", dushman_cmd))
    app.add_handler(CommandHandler("nacho", nacho_cmd))
    app.add_handler(CommandHandler("chappal", chappal_cmd))
    app.add_handler(CommandHandler("jhadu", jhadu_cmd))
    app.add_handler(CommandHandler("belan", belan_cmd))
    app.add_handler(CommandHandler("tamacha", tamacha_cmd))
    app.add_handler(CommandHandler("lathi", lathi_cmd))
    app.add_handler(CommandHandler("kela", kela_cmd))
    app.add_handler(CommandHandler("chai", chai_cmd))
    app.add_handler(CommandHandler("mirchi", mirchi_cmd))
    app.add_handler(CommandHandler("dhoka", dhoka_cmd))
    app.add_handler(CommandHandler("kamra", kamra_cmd))
    
    app.add_handler(CommandHandler("shayari", shayari_cmd))
    app.add_handler(CommandHandler("save", save_note))
    app.add_handler(CommandHandler("get", get_note))
    app.add_handler(CommandHandler("addfilter", add_filter))
    app.add_handler(CommandHandler("addbadword", add_badword))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_stickers))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Aegis V17.0 Premium running...")
    app.run_polling()

if __name__ == '__main__':
    main()
