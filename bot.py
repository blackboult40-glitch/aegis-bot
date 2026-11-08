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

# --- DUMMY SERVER ---
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
    from chat_data import CHAT_DATA, TRUTHS, DARES, RIZZ, ROASTS, SHAYARI, TRACE_WORDS, TRIVIA_QUESTIONS, DESI_GIFS, ROB_GIFS_SUCCESS, ROB_GIFS_FAIL, BAN_GIFS, MUTE_GIFS
except ImportError:
    CHAT_DATA, TRUTHS, DARES, RIZZ, ROASTS, SHAYARI, TRACE_WORDS, TRIVIA_QUESTIONS, DESI_GIFS = {}, [], [], [], [], {}, [], [], {}
    ROB_GIFS_SUCCESS, ROB_GIFS_FAIL, BAN_GIFS, MUTE_GIFS = [], [], [], []

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Database ---
MONGO_URI = os.environ.get("MONGODB_URI")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

mongo_client = MongoClient(MONGO_URI)
db = mongo_client['aegis_db']
settings_col = db['settings']
filters_col = db['filters']
warnings_col = db['warnings']
admins_col = db['custom_admins']
notes_col = db['notes']
badwords_col = db['badwords']
chats_col = db['chats']
gbans_col = db['gbans']
users_col = db['users']
approved_col = db['approved_users']
bad_stickers_col = db['bad_stickers']          # NEW
reports_log_col = db['reports_log']            # NEW
violations_col = db['violations']              # NEW

# --- Game Memories ---
ttt_games = {}
trace_games = {}
trivia_games = {}
message_timestamps = defaultdict(list)         # NEW anti-flood

# ============================================================
# 🛡️ PROTECTION CONSTANTS (NEW)
# ============================================================
ABUSE_SHORTFORMS = {
    "bc", "mc", "bkl", "bkc", "mkc", "bsdk", "msdk", "chutiya", "chutya",
    "gandu", "gand", "gaand", "madarchod", "maderchod", "bhenchod", "bhenchd",
    "chut", "loda", "lodu", "lund", "randi", "harami", "kutta", "kamina",
    "saala", "sala", "chodu", "choda", "bhadwa", "tatte", "jhat", "jhaat",
    "chod", "lode", "bhosd", "bhosda", "chhiya", "lavda", "lauda", "theli",
    "bakland", "baklund", "bkl", "mkl", "chudai", "chodai"
}

DRUG_KEYWORDS = {
    "ganja", "charas", "weed", "cocaine", "heroin", "mdma", "lsd", "meth",
    "opium", "nashe", "nasha", "drugs", "drug", "coke", "chitta", "afim",
    "afeem", "bhang", "bhaang", "smack", "party drugs", "ice drug",
    "ganja bechna", "charas bechna", "drugs bechna", "drugs sell",
    "cocaine sell", "heroin sell", "weed sell", "drug dealer"
}

NSFW_KEYWORDS = {
    "porn", "porno", "xxx", "nude", "nudes", "naked", "nangi", "nanga",
    "sex chat", "horny", "rape", "child porn", "cp", "loli", "incest",
    "hentai", "nsfw", "onlyfans", "orgy", "18+", "18 plus", "adult video",
    "sex video", "sexy girl", "chudai video", "blue film", "bf video"
}

SCAM_KEYWORDS = {
    "lottery", "prize money", "you won", "click here to claim", "free money",
    "otp bhejo", "otp send", "verify account", "account block", "kyc update",
    "crypto double", "investment double", "guaranteed return", "earn daily",
    "work from home", "part time job", "click link earn", "free recharge",
    "telegram premium free", "free gift", "gift card"
}

BAD_STICKER_EMOJIS = {"🍆", "🍑", "💦", "🍼", "🖕", "💊", "💉", "🚬", "🔞",
                      "🩸", "👅", "👙", "🩲", "🧨", "💣", "🔫", "🖐️", "🍌"}

BAD_STICKER_SET_KEYWORDS = {"nsfw", "porn", "sex", "xxx", "18plus", "18+",
                            "nude", "adult", "gali", "abuse", "gaali", "hot"}

REPORT_TRIGGERS = {"report", "rpt", "complaint", "admin", "@admin",
                   "report him", "report her", "mods", "moderator"}

# ============================================================
# LANGUAGE
# ============================================================
LANGS = {
    "en": {
        "denied": "🚫 <b>Access Denied!</b> You Don't Have Enough Permissions.",
        "owner_respect": "👑 <b>Yes, Boss!</b> Executing your command. ⚡\n\n",
        "owner_protection": "👑 <b>Owner Protected!</b> Cannot perform this action on the boss.",
        "user_not_found": "❌ <b>Target Not Found!</b> Reply to a user.",
        "banned": "🔨 <b>BANNED!</b> {} has been removed. 🚫",
        "kicked": "👢 <b>KICKED!</b> {} has been removed. 🚪",
        "muted": "🔇 <b>MUTED!</b> {} has been silenced. 🤐",
        "unmuted": "🔊 <b>UNMUTED!</b> {} can speak. 🗣️",
        "pinned": "📌 Message Pinned!",
        "unpinned": "📍 Message Unpinned!",
        "lang_changed": "🌐 Language Changed To English! 🇬🇧"
    },
    "hi": {
        "denied": "🚫 <b>Permission Nahi Hai!</b>",
        "owner_respect": "👑 <b>Ji Huzoor!</b> Aapka hukum sar aankhon par. ⚡\n\n",
        "owner_protection": "👑 <b>Owner Protected!</b> Boss ke saath aisa nahi kar sakte.",
        "user_not_found": "❌ <b>Target Nahi Mila!</b> Kisi message ko reply karein.",
        "banned": "🔨 <b>BANNED!</b> {} ko nikal diya gaya. 🚫",
        "kicked": "👢 <b>KICKED!</b> {} ko nikal diya gaya. 🚪",
        "muted": "🔇 <b>MUTED!</b> {} ko chup karaya gaya. 🤐",
        "unmuted": "🔊 <b>UNMUTED!</b> {} ab bol sakta hai. 🗣️",
        "pinned": "📌 Message Pin Ho Gaya!",
        "unpinned": "📍 Message Unpin Ho Gaya!",
        "lang_changed": "🌐 Language Hindi Mein Badli! 🇮🇳"
    }
}

def get_lang(chat_id):
    data = settings_col.find_one({"chat_id": chat_id})
    return data.get("lang", "en") if data else "en"

# ============================================================
# HELPERS
# ============================================================
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

# ============================================================
# ECONOMY HELPERS
# ============================================================
def get_user_bal(user_id):
    if user_id == OWNER_ID: return "♾️ Unlimited"
    user = users_col.find_one({"user_id": user_id})
    if not user:
        users_col.insert_one({"user_id": user_id, "balance": 100})
        return 100
    return user.get("balance", 100)

def update_user_bal(user_id, amount):
    if user_id == OWNER_ID and amount < 0: return 
    users_col.update_one({"user_id": user_id}, {"$inc": {"balance": amount}}, upsert=True)

# ============================================================
# 🛡️ PROTECTION HELPERS (NEW)
# ============================================================
async def notify_admins(context, chat_id, text, notify_owner=True):
    """DM all admins + owner with violation details."""
    sent = 0
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.user.is_bot: continue
            try:
                await context.bot.send_message(admin.user.id, text, parse_mode='HTML', disable_web_page_preview=True)
                sent += 1
            except: pass
    except: pass
    if notify_owner and OWNER_ID and OWNER_ID != 0:
        try:
            await context.bot.send_message(OWNER_ID, text, parse_mode='HTML', disable_web_page_preview=True)
            sent += 1
        except: pass
    return sent

def track_violation(chat_id, user_id, vtype):
    """Increment violation counter and return new count."""
    violations_col.update_one(
        {"chat_id": chat_id, "user_id": user_id, "type": vtype},
        {"$inc": {"count": 1}, "$set": {"last_at": datetime.utcnow()}},
        upsert=True
    )
    doc = violations_col.find_one({"chat_id": chat_id, "user_id": user_id, "type": vtype})
    return doc.get("count", 1) if doc else 1

async def punish_violator(context, chat_id, user_id, user_first_name, count, reason):
    """Apply escalating punishment: 1-2 warn, 3-4 mute 1h, 5+ ban."""
    try:
        if count >= 5:
            await context.bot.ban_chat_member(chat_id, user_id)
            await context.bot.send_message(
                chat_id,
                f"🔨 <b>{user_first_name}</b> banned after {count} violations ({reason}).",
                parse_mode='HTML'
            )
        elif count >= 3:
            await context.bot.restrict_chat_member(
                chat_id=chat_id, user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=datetime.now() + timedelta(hours=1)
            )
            await context.bot.send_message(
                chat_id,
                f"🔇 <b>{user_first_name}</b> muted 1 hour ({count} violations: {reason}).",
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id,
                f"⚠️ <b>{user_first_name}</b>, {reason}! Warning {count}/5.",
                parse_mode='HTML'
            )
    except: pass

def is_abuse(text):
    words = text.lower().split()
    return any(w.strip(".,!?") in ABUSE_SHORTFORMS for w in words)

def is_drug(text):
    return any(kw in text.lower() for kw in DRUG_KEYWORDS)

def is_nsfw(text):
    return any(kw in text.lower() for kw in NSFW_KEYWORDS)

def is_scam(text):
    return any(kw in text.lower() for kw in SCAM_KEYWORDS)

def check_sticker_violation(sticker):
    """Returns reason string if bad, else None."""
    db_check = bad_stickers_col.find_one({"file_unique_id": sticker.file_unique_id})
    if db_check: return "🚫 Blacklisted sticker"
    if sticker.emoji and sticker.emoji in BAD_STICKER_EMOJIS:
        return f"🚫 Inappropriate emoji ({sticker.emoji})"
    set_name = (sticker.set_name or "").lower()
    if any(kw in set_name for kw in BAD_STICKER_SET_KEYWORDS):
        return "🚫 NSFW/Abuse sticker pack"
    return None

# ============================================================
# KEYBOARDS
# ============================================================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me To Your Group", url="https://t.me/aegis_manager_bot?startgroup=true")],
        [InlineKeyboardButton("🛡️ Moderation", callback_data="m_mod"), InlineKeyboardButton("🎮 Fun & Games", callback_data="m_fun")],
        [InlineKeyboardButton("👑 Admin Levels", callback_data="m_admin"), InlineKeyboardButton("💰 Economy", callback_data="m_eco")],
        [InlineKeyboardButton("📝 Notes", callback_data="m_notes"), InlineKeyboardButton("🚫 Blacklist", callback_data="m_badwords")],
        [InlineKeyboardButton("🔒 Locks", callback_data="m_lock"), InlineKeyboardButton("🌐 Language", callback_data="m_lang")],
        [InlineKeyboardButton("🛡️ Protection System", callback_data="m_protect")]
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

def protection_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Stickers", callback_data="prot_sticker"), InlineKeyboardButton("💊 Drugs", callback_data="prot_drug")],
        [InlineKeyboardButton("🔞 NSFW", callback_data="prot_nsfw"), InlineKeyboardButton("💸 Scam", callback_data="prot_scam")],
        [InlineKeyboardButton("✏️ Edits", callback_data="prot_edit"), InlineKeyboardButton("🌊 Flood", callback_data="prot_flood")],
        [InlineKeyboardButton("🔙 Back", callback_data="m_main")]
    ])

# ============================================================
# CALLBACK HANDLER
# ============================================================
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
    elif data == "m_protect": await query.edit_message_text(
        "🛡️ <b>Protection System</b>\n\nBot automatically deletes:\n• NSFW/Abuse stickers\n• Drug/illegal text\n• NSFW text\n• Scam messages\n• Edited messages\n• Flood spam\n\nUse <code>/protection</code> for status.",
        reply_markup=protection_menu(), parse_mode='HTML'
    )
    elif data.startswith("prot_"):
        await query.edit_message_text(
            f"ℹ️ <b>Protection Info</b>\n\nType <code>/protection</code> to see full status.\nViolations auto-escalate: warn → mute 1h → ban.",
            reply_markup=protection_menu(), parse_mode='HTML'
        )
    elif data == "m_trace":
        await query.edit_message_text("🏃 <b>Word Trace Game</b>\n\nType <code>/trace</code> to start!", parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_fun")]]))
    elif data == "m_admin":
        text = "👑 <b>Admin Levels</b>\n\n<code>/promote @user 1</code> - Mod\n<code>/promote @user 2</code> - Admin\n<code>/promote @user 3</code> - Co-Owner\n<code>/demote @user</code>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_main")]]), parse_mode='HTML')
    elif data == "m_notes":
        text = "📝 <b>Notes</b>\n\n<code>/save name text</code>\n<code>/get name</code>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_main")]]), parse_mode='HTML')
    elif data == "m_badwords":
        text = "🚫 <b>Blacklist</b>\n\n<code>/addbadword word</code>"
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
    elif data == "cmd_roast": await query.edit_message_text("Reply: <code>/roast</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_fun")]]), parse_mode='HTML')
    elif data == "cmd_bal": await query.edit_message_text("Type: <code>/bal</code> (Or Reply)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_daily": await query.edit_message_text("Type: <code>/daily</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_pay": await query.edit_message_text("Usage: Reply with <code>/pay 100</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_kill": await query.edit_message_text("Reply: <code>/kill</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_rob": await query.edit_message_text("Usage: Reply with <code>/rob 100</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_bet": await query.edit_message_text("Type: <code>/bet 100 dice</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_rps": await query.edit_message_text("Type: <code>/rps 100</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_ttt": await query.edit_message_text("Type: <code>/ttt</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')
    elif data == "cmd_top": await query.edit_message_text("Type: <code>/top</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="m_eco")]]), parse_mode='HTML')

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
        if chat_id not in ttt_games: return await query.answer("Game Over!", show_alert=True)
        board, turn = ttt_games[chat_id]
        if board[idx] != "⬜": return await query.answer("Spot taken!", show_alert=True)
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
            return await query.edit_message_text("🤝 <b>Tie!</b>", parse_mode='HTML', reply_markup=generate_ttt_board(board))
        await query.edit_message_text("Your turn! (You are ❌)", reply_markup=generate_ttt_board(board))

def check_win(board, player):
    wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    for w in wins:
        if board[w[0]] == board[w[1]] == board[w[2]] == player: return True
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

# ============================================================
# CORE COMMANDS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chats_col.update_one({"chat_id": update.effective_chat.id}, {"$set": {"chat_id": update.effective_chat.id}}, upsert=True)
    text = (
        "⚡ <b>Aegis Premium Panel</b> ⚡\n\n"
        "👑 <b>System Developer:</b> <code>Aman</code>\n"
        "🔥 <i>The Ultimate Architecture</i>\n"
        "🛡️ <i>Advanced Protection Enabled</i>\n\n"
        "👇 Select a category below:"
    )
    await update.message.reply_text(text, reply_markup=main_menu(), parse_mode='HTML')

async def set_lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return await update.message.reply_text("🚫 Admin Only.")
    if not context.args or context.args[0] not in ['en', 'hi']: return await update.message.reply_text("Usage: <code>/setlang en</code> or <code>/setlang hi</code>", parse_mode='HTML')
    lang = context.args[0]
    settings_col.update_one({"chat_id": update.effective_chat.id}, {"$set": {"lang": lang}}, upsert=True)
    await update.message.reply_text(LANGS[lang]["lang_changed"], parse_mode='HTML')

async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return await update.message.reply_text("🚫 Admin Only.")
    target = await get_target(update, context)
    if not target: return await update.message.reply_text("Reply to a user to approve.")
    approved_col.update_one({"chat_id": update.effective_chat.id, "user_id": target.id}, {"$set": {"user_id": target.id}}, upsert=True)
    await update.message.reply_text(f"✅ {target.first_name} is now Approved. They won't be auto-muted for abuse (but will be warned).")

# ============================================================
# GAMES
# ============================================================
async def trace_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in trace_games: return await update.message.reply_text("❌ A game is already running!")
    if not TRACE_WORDS: return await update.message.reply_text("❌ No trace words available in data.")
    word = random.choice(TRACE_WORDS)
    word_list = list(word)
    random.shuffle(word_list)
    trace_games[chat_id] = word
    await update.message.reply_text(f"🏃 <b>WORD TRACE!</b> 🏃\n\nUnscramble:\n👉 <code>{''.join(word_list)}</code> 👈\n\nFirst gets <b>$200</b>! (60s)", parse_mode='HTML')
    context.job_queue.run_once(trace_timeout, 60, chat_id=chat_id)

async def trace_timeout(context: ContextTypes.DEFAULT_TYPE):
    if context.job.chat_id in trace_games:
        del trace_games[context.job.chat_id]
        await context.bot.send_message(context.job.chat_id, "⏰ <b>Time Over!</b>", parse_mode='HTML')

async def trivia_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in trivia_games: return await update.message.reply_text("❌ Trivia is already running!")
    if not TRIVIA_QUESTIONS: return await update.message.reply_text("❌ No trivia questions available.")
    q_data = random.choice(TRIVIA_QUESTIONS)
    trivia_games[chat_id] = q_data["a"]
    await update.message.reply_text(f"🧠 <b>TRIVIA!</b>\n\nQuestion: {q_data['q']}\n\nFirst correct answer gets <b>$100</b>! (30s)", parse_mode='HTML')
    context.job_queue.run_once(trivia_timeout, 30, chat_id=chat_id)

async def trivia_timeout(context: ContextTypes.DEFAULT_TYPE):
    if context.job.chat_id in trivia_games:
        del trivia_games[context.job.chat_id]
        await context.bot.send_message(context.job.chat_id, "⏰ <b>Time Over!</b> No one answered.", parse_mode='HTML')

async def spin_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    members = [a.user for a in admins if not a.user.is_bot]
    if not members: return await update.message.reply_text("Could not find members to spin.")
    chosen = random.choice(members)
    await update.message.reply_text(f"🎡 <b>Spinning the wheel...</b>\n\n🎯 The chosen one is: [{chosen.first_name}](tg://user?id={chosen.id})", parse_mode='Markdown')

# ============================================================
# OWNER
# ============================================================
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("🚫 Owner Only!")
    total_chats = chats_col.count_documents({})
    total_reports = reports_log_col.count_documents({})
    text = f"👑 <b>Welcome Boss</b> 👑\n\n📊 <b>Groups:</b> {total_chats}\n📨 <b>Reports Logged:</b> {total_reports}\n💰 <b>Balance:</b> ♾️ Unlimited\n⚡ <b>Status:</b> God Mode Active\n\n<b>Commands:</b>\n<code>/broadcast &lt;msg&gt;</code>\n<code>/gban (reply)</code>\n<code>/reports</code>"
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
    if target.id == OWNER_ID: return await update.message.reply_text("🚫 Cannot gban yourself!")
    reason = " ".join(context.args) if context.args else "No reason provided"
    gbans_col.insert_one({"user_id": target.id, "reason": reason})
    chats = chats_col.find()
    for chat in chats:
        try: await context.bot.ban_chat_member(chat['chat_id'], target.id)
        except: pass
    await update.message.reply_text(f"🔨 <b>GBANNED!</b> {target.first_name}\nReason: {reason}", parse_mode='HTML')

# ============================================================
# ECONOMY
# ============================================================
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
    bal = get_user_bal(target.id)
    await update.message.reply_text(f"💰 <b>{target.first_name}</b>'s Balance: <b>{bal}</b>", parse_mode='HTML')

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_col.find_one({"user_id": user_id})
    now = datetime.utcnow()
    if user and user.get("last_daily") and now - user["last_daily"] < timedelta(hours=24):
        return await update.message.reply_text("⏳ Wait 24h for next daily.")
    update_user_bal(user_id, 500)
    users_col.update_one({"user_id": user_id}, {"$set": {"last_daily": now}}, upsert=True)
    await update.message.reply_text(f"🎁 <b>Daily Claimed!</b> Earned $500.", parse_mode='HTML')

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await get_target(update, context)
    if not target or not context.args: return await update.message.reply_text("Reply with `/pay 100`")
    try: amount = int(context.args[-1])
    except: return await update.message.reply_text("Invalid amount.")
    if update.effective_user.id != OWNER_ID and get_user_bal(update.effective_user.id) < amount: return await update.message.reply_text("❌ Insufficient funds!")
    update_user_bal(update.effective_user.id, -amount)
    update_user_bal(target.id, amount)
    await update.message.reply_text(f"💸 Sent ${amount} to {target.first_name}.", parse_mode='HTML')

async def rob_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await get_target(update, context)
    if not target or not context.args: return await update.message.reply_text("Reply with `/rob <amount>`")
    try: amount = int(context.args[-1])
    except: return await update.message.reply_text("Invalid amount.")
    if target.id == update.effective_user.id: return await update.message.reply_text("You cannot rob yourself!")
    if update.effective_user.id != OWNER_ID and get_user_bal(update.effective_user.id) < amount: return await update.message.reply_text("❌ You need more money to risk.")
    if get_user_bal(target.id) < amount: return await update.message.reply_text("😂 Target doesn't have that much!")
    success = random.choice([True, False])
    if success:
        gif = random.choice(ROB_GIFS_SUCCESS) if ROB_GIFS_SUCCESS else (fetch_gif("happy") or "https://media.tenor.com/B8J4vI8q4AAAAAC/thor-hammer.gif")
        update_user_bal(target.id, -amount)
        update_user_bal(update.effective_user.id, amount)
        caption = f"🕵️‍♂️ <b>ROBBED!</b> {update.effective_user.first_name} stole ${amount} from {target.first_name}!"
    else:
        gif = random.choice(ROB_GIFS_FAIL) if ROB_GIFS_FAIL else (fetch_gif("cry") or "https://media.tenor.com/M8J4vI8q4AAAAAC/shut-up.gif")
        update_user_bal(update.effective_user.id, -amount)
        update_user_bal(target.id, amount)
        caption = f"🚨 <b>CAUGHT!</b> {update.effective_user.first_name} failed and paid ${amount} fine!"
    await update.message.reply_animation(animation=gif, caption=caption, parse_mode='HTML')

async def kill_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await get_target(update, context)
    if not target: return await update.message.reply_text("Reply to kill.")
    if target.id == update.effective_user.id: return await update.message.reply_text("Suicide not allowed!")
    if update.effective_user.id != OWNER_ID and get_user_bal(update.effective_user.id) < 50: return await update.message.reply_text("❌ Need $50.")
    update_user_bal(update.effective_user.id, -50)
    success = random.choice([True, False])
    if success:
        gif = fetch_gif("kill") or "https://media.tenor.com/B8J4vI8q4AAAAAC/thor-hammer.gif"
        update_user_bal(update.effective_user.id, 100)
        caption = f"☠️ <b>KILLED!</b> {update.effective_user.first_name} killed {target.first_name}! Reward: $100"
    else:
        gif = fetch_gif("cry") or "https://media.tenor.com/M8J4vI8q4AAAAAC/shut-up.gif"
        caption = f"😂 <b>MISSED!</b> Attack failed! Lost $50."
    await update.message.reply_animation(animation=gif, caption=caption, parse_mode='HTML')

async def bet_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        return await update.message.reply_text(
            "🎲 <b>Dice Bet</b>\n\nUsage: <code>/bet 100</code> or <code>/bet 100 dice</code>\nEmojis: 🎲 dice, 🎯 dart, 🏀 basketball, 🎳 bowling, ⚽ football, 🎰 slot\n\nWin rule: 4+ = win 2x.",
            parse_mode='HTML'
        )
    try: amount = int(context.args[0])
    except (ValueError, IndexError): return await update.message.reply_text("❌ Invalid amount! Usage: <code>/bet 100</code>", parse_mode='HTML')
    if amount <= 0: return await update.message.reply_text("❌ Amount must be > 0!")
    emoji = "🎲"
    if len(context.args) > 1:
        choice_map = {"dice": "🎲", "dart": "🎯", "basket": "🏀", "basketball": "🏀", "bowling": "🎳", "football": "⚽", "soccer": "⚽", "slot": "🎰", "slotmachine": "🎰"}
        emoji = choice_map.get(context.args[1].lower(), "🎲")
    bal = get_user_bal(user_id)
    if bal != "♾️ Unlimited" and bal < amount:
        return await update.message.reply_text(f"❌ <b>Insufficient funds!</b> Balance: <b>{bal}</b>", parse_mode='HTML')
    dice_msg = await update.message.reply_dice(emoji=emoji)
    value = dice_msg.dice.value
    if emoji == "🎰":
        if value >= 43:
            update_user_bal(user_id, amount); result = f"🎉 <b>JACKPOT!</b> Slot: {value}\nWon <b>${amount}</b>!"
        else:
            update_user_bal(user_id, -amount); result = f"😭 <b>No luck!</b> Slot: {value}\nLost <b>${amount}</b>."
    else:
        if value >= 4:
            update_user_bal(user_id, amount); result = f"🎉 <b>You Won!</b> Rolled <b>{value}</b> (4+).\nEarned <b>${amount}</b>!"
        else:
            update_user_bal(user_id, -amount); result = f"😭 <b>You Lost!</b> Rolled <b>{value}</b> (needed 4+).\nLost <b>${amount}</b>."
    await update.message.reply_text(result, parse_mode='HTML')

async def rps_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Usage: `/rps 100`")
    try: bet = int(context.args[-1])
    except: return await update.message.reply_text("Invalid amount.")
    challenger = update.effective_user
    opponent = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if opponent and opponent.id != challenger.id:
        if update.effective_user.id != OWNER_ID and get_user_bal(challenger.id) < bet: return await update.message.reply_text("❌ Insufficient funds!")
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪨 Rock", callback_data=f"rpspvp_rock_{bet}_{challenger.id}_{opponent.id}"), InlineKeyboardButton("📄 Paper", callback_data=f"rpspvp_paper_{bet}_{challenger.id}_{opponent.id}")],
            [InlineKeyboardButton("✂️ Scissors", callback_data=f"rpspvp_scissors_{bet}_{challenger.id}_{opponent.id}")]
        ])
        await update.message.reply_text(f"⚔️ <b>PvP Challenge!</b>\n\n{challenger.first_name} vs {opponent.first_name} for ${bet}!", reply_markup=markup, parse_mode='HTML')
    else:
        if update.effective_user.id != OWNER_ID and get_user_bal(challenger.id) < bet: return await update.message.reply_text("❌ Insufficient funds!")
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪨 Rock", callback_data=f"rps_rock_{bet}"), InlineKeyboardButton("📄 Paper", callback_data=f"rps_paper_{bet}")],
            [InlineKeyboardButton("✂️ Scissors", callback_data=f"rps_scissors_{bet}")]
        ])
        await update.message.reply_text(f"✊ <b>RPS (vs Bot)</b> Bet: ${bet}", reply_markup=markup, parse_mode='HTML')

async def ttt_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id in ttt_games: return await update.message.reply_text("Game already running!")
    ttt_games[update.effective_chat.id] = (["⬜"]*9, "❌")
    await update.message.reply_text("❌ <b>Tic-Tac-Toe (vs Bot)</b>", reply_markup=generate_ttt_board(["⬜"]*9), parse_mode='HTML')

async def top_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = list(users_col.find().sort("balance", -1).limit(10))
    if not top_users: return await update.message.reply_text("No data yet!")
    text = "🏆 <b>GLOBAL LEADERBOARD</b> 🏆\n\n"
    for i, user in enumerate(top_users, 1):
        try: name = (await context.bot.get_chat(user['user_id'])).first_name
        except: name = f"User_{user['user_id']}"
        text += f"{i}. {name} - ${user['balance']}\n"
    await update.message.reply_text(text, parse_mode='HTML')

# ============================================================
# MODERATION
# ============================================================
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
    if await get_user_level(update, context) < 2: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    if target.id == OWNER_ID: return await update.message.reply_text(LANGS[lang]["owner_protection"], parse_mode='HTML')
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        prefix = LANGS[lang]["owner_respect"] if await get_user_level(update, context) == 99 else ""
        caption = f"{prefix}{LANGS[lang]['banned'].format(target.first_name)}"
        gif = random.choice(BAN_GIFS) if BAN_GIFS else fetch_gif("slap")
        if gif: await update.message.reply_animation(animation=gif, caption=caption, parse_mode='HTML')
        else: await update.message.reply_text(caption, parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 2: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)
        await update.message.reply_text(f"✅ {target.first_name} unbanned.", parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 2: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)
        gif = random.choice(BAN_GIFS) if BAN_GIFS else fetch_gif("slap")
        caption = LANGS[lang]['kicked'].format(target.first_name)
        if gif: await update.message.reply_animation(animation=gif, caption=caption, parse_mode='HTML')
        else: await update.message.reply_text(caption, parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 1: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, ChatPermissions(can_send_messages=False))
        gif = random.choice(MUTE_GIFS) if MUTE_GIFS else (fetch_gif("shh") or fetch_gif("slap"))
        caption = LANGS[lang]['muted'].format(target.first_name)
        if gif: await update.message.reply_animation(animation=gif, caption=caption, parse_mode='HTML')
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
    if not target or not context.args: return await update.message.reply_text("Usage: <code>/tmute 10m</code>")
    time_delta = extract_time(context.args[0])
    if not time_delta: return await update.message.reply_text("Invalid time. Use 10m, 1h.")
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"⏱️ {target.first_name} muted for {context.args[0]}.", parse_mode='HTML')
        context.job_queue.run_once(auto_unmute, time_delta, chat_id=update.effective_chat.id, data={'user_id': target.id})
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 1: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    if target.id == OWNER_ID: return await update.message.reply_text(LANGS[lang]["owner_protection"], parse_mode='HTML')
    chat_id, user_id = update.effective_chat.id, target.id
    data = warnings_col.find_one({"chat_id": chat_id, "user_id": user_id, "type": "manual"})
    new_count = (data.get("count", 0) + 1) if data else 1
    if data: warnings_col.update_one({"_id": data["_id"]}, {"$set": {"count": new_count}})
    else: warnings_col.insert_one({"chat_id": chat_id, "user_id": user_id, "count": new_count, "type": "manual"})
    await update.message.reply_text(f"⚠️ {target.first_name} warned! ({new_count}/3)", parse_mode='HTML')
    if new_count >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await update.message.reply_text(f"💀 {target.first_name} banned for 3 warnings!", parse_mode='HTML')
            warnings_col.delete_one({"chat_id": chat_id, "user_id": user_id, "type": "manual"})
        except: pass

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 3: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target or not context.args: return await update.message.reply_text("Usage: <code>/promote @user 1</code>")
    try: level = int(context.args[-1])
    except: level = 1
    try:
        await context.bot.promote_chat_member(chat_id=update.effective_chat.id, user_id=target.id, can_change_info=(level>=2), can_delete_messages=True, can_invite_users=True, can_restrict_members=(level>=2), can_pin_messages=(level>=2), can_promote_members=(level==3))
        admins_col.update_one({"chat_id": update.effective_chat.id, "user_id": target.id}, {"$set": {"level": level}}, upsert=True)
        await update.message.reply_text(f"✅ {target.first_name} promoted to Level {level}!", parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Failed. Error: {e}")

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(update.effective_chat.id)
    if await get_user_level(update, context) < 3: return await update.message.reply_text(LANGS[lang]["denied"], parse_mode='HTML')
    target = await get_target(update, context)
    if not target: return await update.message.reply_text(LANGS[lang]["user_not_found"], parse_mode='HTML')
    try:
        await context.bot.promote_chat_member(chat_id=update.effective_chat.id, user_id=target.id, can_change_info=False, can_delete_messages=False, can_invite_users=False, can_restrict_members=False, can_pin_messages=False, can_promote_members=False)
        admins_col.delete_one({"chat_id": update.effective_chat.id, "user_id": target.id})
        await update.message.reply_text(f"📉 {target.first_name} demoted!", parse_mode='HTML')
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def lock_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    try:
        await context.bot.set_chat_permissions(update.effective_chat.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text("🔒 Group Locked!")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}. Bot needs rights.")

async def unlock_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    try:
        await context.bot.set_chat_permissions(update.effective_chat.id, get_chat_permissions())
        await update.message.reply_text("🔓 Group Unlocked!")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}. Bot needs rights.")

async def lock_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    settings_col.update_one({"chat_id": update.effective_chat.id}, {"$set": {"stickers_locked": True}}, upsert=True)
    await update.message.reply_text("🔒 Stickers Locked!")

async def unlock_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return
    settings_col.update_one({"chat_id": update.effective_chat.id}, {"$set": {"stickers_locked": False}}, upsert=True)
    await update.message.reply_text("🔓 Stickers Unlocked!")

# ============================================================
# FUN & DESI
# ============================================================
async def action_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, action_name):
    if not update.message.reply_to_message: return await update.message.reply_text(f"Reply to someone with /{action_name}")
    target = update.message.reply_to_message.from_user
    user = update.effective_user.first_name
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

async def truth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    truth = random.choice(TRUTHS) if TRUTHS else "Truth list empty!"
    if target: await update.message.reply_text(f"🎯 <b>Truth for {target.first_name}:</b>\n\n{truth}", parse_mode='HTML')
    else: await update.message.reply_text(f"🎯 <b>Truth:</b>\n\n{truth}", parse_mode='HTML')

async def dare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    dare = random.choice(DARES) if DARES else "Dare list empty!"
    if target: await update.message.reply_text(f"🔥 <b>Dare for {target.first_name}:</b>\n\n{dare}", parse_mode='HTML')
    else: await update.message.reply_text(f"🔥 <b>Dare:</b>\n\n{dare}", parse_mode='HTML')

async def rizz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    rizz = random.choice(RIZZ) if RIZZ else "Rizz list empty!"
    if target: await update.message.reply_text(f"💘 {update.effective_user.first_name} to {target.first_name}:\n\n<i>{rizz}</i>", parse_mode='HTML')
    else: await update.message.reply_text(f"💘 <i>{rizz}</i>", parse_mode='HTML')

async def roast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    roast = random.choice(ROASTS) if ROASTS else "Roast list empty!"
    if target: await update.message.reply_text(f"😂 <b>{target.first_name}</b>, {roast}", parse_mode='HTML')
    else: await update.message.reply_text(f"😂 {roast}", parse_mode='HTML')

async def eight_ball(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers = ["Yes.", "No.", "Maybe.", "Definitely!", "Absolutely not.", "Ask again later.", "I don't know."]
    await update.message.reply_text(f"🎱 {random.choice(answers)}")

async def roll_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_dice(emoji="🎲")

async def shayari_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🖋️ <b>Shayari Menu</b>", reply_markup=shayari_menu(), parse_mode='HTML')

# ============================================================
# 🛡️ PROTECTION HANDLERS (NEW)
# ============================================================
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = settings_col.find_one({"chat_id": update.effective_chat.id})
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        welcome = data.get("welcome_text", "Welcome {name}! 👋").replace("{name}", member.first_name) if data else f"Welcome {member.first_name}! 👋"
        await update.message.reply_text(welcome)

async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete edited messages and report to admins."""
    if not update.edited_message: return
    chat = update.effective_chat or update.edited_chat
    if not chat: return
    
    # Admins exempt
    try:
        if await get_user_level(update, context) >= 2: return
    except: pass
    
    try: await update.edited_message.delete()
    except: pass
    
    chat_title = chat.title or chat.username or str(chat.id)
    user = update.edited_message.from_user
    new_text = (update.edited_message.text or update.edited_message.caption or "(media)")[:300]
    
    admin_msg = (
        f"🚨 <b>MESSAGE EDITED & DELETED</b> 🚨\n\n"
        f"👤 <b>User:</b> {user.first_name}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"💬 <b>Group:</b> {chat_title}\n"
        f"📝 <b>New content:</b> <code>{new_text}</code>\n\n"
        f"⚡ <i>Edited messages not allowed in this group.</i>"
    )
    await notify_admins(context, chat.id, admin_msg, notify_owner=False)
    
    try:
        await context.bot.send_message(
            chat.id,
            f"⚠️ {user.first_name}, editing messages is not allowed! Admins notified.",
            parse_mode='HTML'
        )
    except: pass

async def handle_gc_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    try:
        user_name = update.message.from_user.first_name
        if update.message.new_chat_title:
            await update.message.reply_text(f"⚠️ <b>{user_name}</b> changed the group name to <b>{update.message.new_chat_title}</b>!", parse_mode='HTML')
        if update.message.new_chat_photo:
            await update.message.reply_text(f"⚠️ <b>{user_name}</b> changed the group photo!", parse_mode='HTML')
    except: pass

async def report_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced /report command - shows WHO reported WHOM."""
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to a user to report.")
    target = update.message.reply_to_message.from_user
    reporter = update.effective_user
    chat = update.effective_chat
    chat_title = chat.title or chat.username or str(chat.id)
    reported_text = (update.message.reply_to_message.text or update.message.reply_to_message.caption or "(media)")[:300]
    
    report_msg = (
        f"🚨 <b>NEW REPORT!</b> 🚨\n\n"
        f"📢 <b>Reporter:</b> {reporter.first_name} (<code>{reporter.id}</code>)\n"
        f"👤 <b>Reported:</b> {target.first_name} (<code>{target.id}</code>)\n"
        f"💬 <b>Group:</b> {chat_title}\n"
        f"📝 <b>Message:</b> <code>{reported_text}</code>\n\n"
        f"⚡ <i>Admins, please review!</i>"
    )
    await notify_admins(context, chat.id, report_msg, notify_owner=True)
    reports_log_col.insert_one({
        "chat_id": chat.id, "reporter_id": reporter.id, "target_id": target.id,
        "target_name": target.first_name, "reporter_name": reporter.first_name,
        "message": reported_text, "timestamp": datetime.utcnow()
    })
    await update.message.reply_text(
        f"✅ Report submitted! Admins have been notified about <b>{target.first_name}</b>.",
        parse_mode='HTML'
    )

async def handle_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🛡️ HIGH PRIORITY: Detect and punish bad stickers."""
    if not update.message or not update.message.sticker: return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user = update.effective_user
    
    # Admins exempt
    if await get_user_level(update, context) >= 1: return
    
    sticker = update.message.sticker
    reason = check_sticker_violation(sticker)
    
    # Check stickers-locked setting
    data = settings_col.find_one({"chat_id": chat_id})
    locked = data and data.get("stickers_locked", False)
    
    if not reason and locked:
        reason = "🔒 Stickers locked in this group"
    
    if not reason: return  # Sticker is clean
    
    # Delete sticker
    try: await update.message.delete()
    except: pass
    
    # Track & punish
    count = track_violation(chat_id, user_id, "sticker")
    await punish_violator(context, chat_id, user_id, user.first_name, count, reason)
    
    # Notify admins
    chat_title = update.effective_chat.title or update.effective_chat.username or str(chat_id)
    admin_msg = (
        f"🚨 <b>STICKER VIOLATION</b> 🚨\n\n"
        f"👤 <b>User:</b> {user.first_name} (<code>{user_id}</code>)\n"
        f"💬 <b>Group:</b> {chat_title}\n"
        f"⚠️ <b>Reason:</b> {reason}\n"
        f"🎨 <b>Emoji:</b> {sticker.emoji or 'N/A'}\n"
        f"📦 <b>Pack:</b> {sticker.set_name or 'N/A'}\n"
        f"📊 <b>Violations:</b> {count}/5\n"
        f"🔖 <b>Sticker ID:</b> <code>{sticker.file_unique_id}</code>"
    )
    await notify_admins(context, chat_id, admin_msg, notify_owner=False)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🛡️ HIGH PRIORITY: Full protection pipeline, then games, then chatting."""
    if not update.message or not update.message.text: return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user = update.effective_user
    text_upper = update.message.text.upper()
    text_lower = update.message.text.lower()
    text_raw = update.message.text
    chat_title = update.effective_chat.title or update.effective_chat.username or str(chat_id)
    
    # ========== 1. GBAN CHECK (highest priority) ==========
    gban_data = gbans_col.find_one({"user_id": user_id})
    if gban_data:
        try:
            await update.message.delete()
            await context.bot.send_message(chat_id, f"⚠️ This user was banned globally. Reason: {gban_data['reason']}", parse_mode='HTML')
            return
        except: pass
    
    # ========== 2. REPORT DETECTION (reply with report word) ==========
    if update.message.reply_to_message and not update.message.reply_to_message.from_user.is_bot:
        stripped = text_lower.strip()
        is_report = (
            stripped in REPORT_TRIGGERS or
            any(stripped.startswith(t + " ") for t in ["report", "rpt"]) or
            "@admin" in stripped
        )
        if is_report:
            target = update.message.reply_to_message.from_user
            reported_text = (update.message.reply_to_message.text or update.message.reply_to_message.caption or "(media)")[:300]
            report_msg = (
                f"🚨 <b>REPORT DETECTED!</b> 🚨\n\n"
                f"📢 <b>Reporter:</b> {user.first_name} (<code>{user_id}</code>)\n"
                f"👤 <b>Reported:</b> {target.first_name} (<code>{target.id}</code>)\n"
                f"💬 <b>Group:</b> {chat_title}\n"
                f"📝 <b>Message:</b> <code>{reported_text}</code>\n\n"
                f"⚡ <i>Admins, review!</i>"
            )
            await notify_admins(context, chat_id, report_msg, notify_owner=True)
            reports_log_col.insert_one({
                "chat_id": chat_id, "reporter_id": user_id, "target_id": target.id,
                "target_name": target.first_name, "reporter_name": user.first_name,
                "message": reported_text, "timestamp": datetime.utcnow()
            })
            try:
                await update.message.reply_text(
                    f"✅ Report registered! Admins notified about <b>{target.first_name}</b>.",
                    parse_mode='HTML'
                )
            except: pass
            return
    
    # ========== 3. GAME ANSWERS (before protection to avoid false positives) ==========
    is_game_answer = False
    if chat_id in trace_games and text_upper == trace_games[chat_id]: is_game_answer = True
    if chat_id in trivia_games and text_lower == trivia_games[chat_id]: is_game_answer = True
    
    if is_game_answer:
        if chat_id in trace_games and text_upper == trace_games[chat_id]:
            del trace_games[chat_id]
            update_user_bal(user_id, 200)
            return await update.message.reply_text(f"🎉 <b>CORRECT!</b> {user.first_name} won $200!", parse_mode='HTML')
        if chat_id in trivia_games and text_lower == trivia_games[chat_id]:
            del trivia_games[chat_id]
            update_user_bal(user_id, 100)
            return await update.message.reply_text(f"🎉 <b>CORRECT!</b> {user.first_name} won $100!", parse_mode='HTML')
    
    # ========== 4. PROTECTION FOR NON-ADMINS ==========
    level = await get_user_level(update, context)
    if level < 1:
        # Anti-Drug
        if is_drug(text_lower):
            try: await update.message.delete()
            except: pass
            count = track_violation(chat_id, user_id, "drug")
            await punish_violator(context, chat_id, user_id, user.first_name, count, "🚫 Drug/illegal content")
            await notify_admins(context, chat_id,
                f"💊 <b>DRUG VIOLATION</b> 💊\n\n👤 <b>User:</b> {user.first_name} (<code>{user_id}</code>)\n💬 <b>Group:</b> {chat_title}\n📝 <b>Text:</b> <code>{text_raw[:300]}</code>\n📊 <b>Strikes:</b> {count}/5",
                notify_owner=True)
            return
        
        # Anti-NSFW
        if is_nsfw(text_lower):
            try: await update.message.delete()
            except: pass
            count = track_violation(chat_id, user_id, "nsfw")
            await punish_violator(context, chat_id, user_id, user.first_name, count, "🔞 NSFW content")
            await notify_admins(context, chat_id,
                f"🔞 <b>NSFW VIOLATION</b> 🔞\n\n👤 <b>User:</b> {user.first_name} (<code>{user_id}</code>)\n💬 <b>Group:</b> {chat_title}\n📝 <b>Text:</b> <code>{text_raw[:300]}</code>\n📊 <b>Strikes:</b> {count}/5",
                notify_owner=True)
            return
        
        # Anti-Scam
        if is_scam(text_lower):
            try: await update.message.delete()
            except: pass
            count = track_violation(chat_id, user_id, "scam")
            await punish_violator(context, chat_id, user_id, user.first_name, count, "💸 Scam/phishing")
            await notify_admins(context, chat_id,
                f"💸 <b>SCAM DETECTED</b> 💸\n\n👤 <b>User:</b> {user.first_name} (<code>{user_id}</code>)\n💬 <b>Group:</b> {chat_title}\n📝 <b>Text:</b> <code>{text_raw[:300]}</code>\n📊 <b>Strikes:</b> {count}/5",
                notify_owner=True)
            return
        
        # Anti-Abuse (shortforms + DB badwords)
        custom_badwords = list(badwords_col.find({"chat_id": chat_id}))
        has_badword = any(bw['word'] in text_lower for bw in custom_badwords)
        
        if is_abuse(text_lower) or has_badword:
            try: await update.message.delete()
            except: pass
            count = track_violation(chat_id, user_id, "abuse")
            await punish_violator(context, chat_id, user_id, user.first_name, count, "🚫 Abusive language")
            await notify_admins(context, chat_id,
                f"🚫 <b>ABUSE DETECTED</b> 🚫\n\n👤 <b>User:</b> {user.first_name} (<code>{user_id}</code>)\n💬 <b>Group:</b> {chat_title}\n📝 <b>Text:</b> <code>{text_raw[:200]}</code>\n📊 <b>Strikes:</b> {count}/5",
                notify_owner=False)
            return
        
        # Anti-Link
        if "http://" in text_lower or "https://" in text_lower or "t.me/" in text_lower:
            try:
                await update.message.delete()
                await context.bot.send_message(chat_id, f"⚠️ {user.first_name}, links not allowed!", parse_mode='HTML')
                return
            except: pass
        
        # Anti-Flood
        now = time.time()
        times = message_timestamps[user_id]
        times = [t for t in times if now - t < 10]
        times.append(now)
        message_timestamps[user_id] = times
        if len(times) >= 8:
            try: await update.message.delete()
            except: pass
            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat_id, user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=datetime.now() + timedelta(minutes=5)
                )
                return await context.bot.send_message(chat_id, f"🔇 {user.first_name} muted 5min (flooding)", parse_mode='HTML')
            except: return
    
    # ========== 5. AUTO REACTIONS ==========
    try:
        if any(w in text_lower for w in ["haha", "lol", "😂"]): await update.message.set_reaction("😂")
        elif any(w in text_lower for w in ["sad", "rona", "😭"]): await update.message.set_reaction("🥺")
        elif any(w in text_lower for w in ["gali", "bc", "mc"]): await update.message.set_reaction("🤮")
        elif any(w in text_lower for w in ["love", "pyar", "❤️"]): await update.message.set_reaction("❤️")
        elif any(w in text_lower for w in ["gussa", "angry", "😡"]): await update.message.set_reaction("🤬")
    except: pass
    
    # ========== 6. CHATTING ENGINE ==========
    for trigger, replies in CHAT_DATA.items():
        if text_lower == trigger:
            if random.random() < 0.4:
                return await update.message.reply_text(random.choice(replies))

# ============================================================
# 🆕 NEW PROTECTION COMMANDS
# ============================================================
async def protection_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 1: return await update.message.reply_text("🚫 Admin Only.")
    chat_id = update.effective_chat.id
    sticker_count = bad_stickers_col.count_documents({})
    text = (
        "🛡️ <b>PROTECTION STATUS</b> 🛡️\n\n"
        "✅ Anti-Sticker (NSFW/Abuse) — <b>Active</b>\n"
        "✅ Anti-Drug Content — <b>Active</b>\n"
        "✅ Anti-NSFW Text — <b>Active</b>\n"
        "✅ Anti-Scam — <b>Active</b>\n"
        "✅ Anti-Shortform-Gali — <b>Active</b>\n"
        "✅ Anti-Edit (delete + report) — <b>Active</b>\n"
        "✅ Anti-Link — <b>Active</b>\n"
        "✅ Anti-Flood (8/10s) — <b>Active</b>\n"
        "✅ Report Detection — <b>Active</b>\n\n"
        f"📊 <b>Blacklisted Stickers:</b> {sticker_count}\n"
        f"📝 <b>To blacklist new sticker:</b> Reply <code>/addbadsticker</code>\n\n"
        "<b>Punishment Escalation:</b>\n"
        "1-2 → ⚠️ Warn\n"
        "3-4 → 🔇 Mute 1 hour\n"
        "5+  → 🔨 Ban"
    )
    await update.message.reply_text(text, parse_mode='HTML')

async def add_bad_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return await update.message.reply_text("🚫 Admin Only.")
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        return await update.message.reply_text("Reply to a sticker with /addbadsticker")
    sticker = update.message.reply_to_message.sticker
    bad_stickers_col.update_one(
        {"file_unique_id": sticker.file_unique_id},
        {"$set": {"file_unique_id": sticker.file_unique_id, "file_id": sticker.file_id, "added_by": update.effective_user.id, "added_at": datetime.utcnow()}},
        upsert=True
    )
    await update.message.reply_text(
        f"✅ <b>Sticker blacklisted!</b>\n🔖 ID: <code>{sticker.file_unique_id}</code>\n\nBot will delete it everywhere now.",
        parse_mode='HTML'
    )

async def del_bad_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return await update.message.reply_text("🚫 Admin Only.")
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        return await update.message.reply_text("Reply to a sticker with /delbadsticker")
    sticker = update.message.reply_to_message.sticker
    result = bad_stickers_col.delete_one({"file_unique_id": sticker.file_unique_id})
    if result.deleted_count:
        await update.message.reply_text("✅ Sticker removed from blacklist.", parse_mode='HTML')
    else:
        await update.message.reply_text("⚠️ Sticker was not in blacklist.")

async def view_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return await update.message.reply_text("🚫 Owner Only!")
    reports = list(reports_log_col.find().sort("timestamp", -1).limit(20))
    if not reports: return await update.message.reply_text("No reports yet.")
    text = "🚨 <b>Recent Reports (Last 20)</b>\n\n"
    for i, r in enumerate(reports, 1):
        ts = r['timestamp'].strftime("%m-%d %H:%M") if r.get('timestamp') else "?"
        text += f"{i}. <b>{r.get('reporter_name','?')}</b> → <b>{r.get('target_name','?')}</b> | {ts}\n   <i>{r.get('message','')[:80]}</i>\n\n"
    await update.message.reply_text(text[:4000], parse_mode='HTML')

async def toggle_antiflood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await get_user_level(update, context) < 2: return await update.message.reply_text("🚫 Admin Only.")
    await update.message.reply_text("✅ Anti-Flood is always active in this bot version. No toggle needed.", parse_mode='HTML')

# ============================================================
# MAIN
# ============================================================
async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "Start Bot"), BotCommand("balance", "Check Money"), BotCommand("daily", "Claim Daily $500"),
        BotCommand("pay", "Transfer Money"), BotCommand("rob", "Rob a user"), BotCommand("kill", "Kill a user"), BotCommand("bet", "Bet On Dice"),
        BotCommand("rps", "Rock Paper Scissors"), BotCommand("ttt", "Tic-Tac-Toe"), BotCommand("trace", "Word Trace Game"),
        BotCommand("top", "Leaderboard"), BotCommand("ban", "Ban"), BotCommand("kick", "Kick"), BotCommand("mute", "Mute"),
        BotCommand("t", "Truth"), BotCommand("d", "Dare"), BotCommand("roast", "Roast"), BotCommand("shayari", "Shayari Menu"),
        BotCommand("chappal", "Chappal Maaro"), BotCommand("bhai", "Bhai Wali Vibe"), BotCommand("approve", "Approve user"),
        BotCommand("trivia", "Trivia Game"), BotCommand("spin", "Spin a member"),
        BotCommand("protection", "Protection Status"), BotCommand("addbadsticker", "Blacklist sticker"),
        BotCommand("report", "Report a user")
    ]
    await application.bot.set_my_commands(commands)

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).post_init(post_init).build()
    
    # Core
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("setlang", set_lang_cmd))
    app.add_handler(CommandHandler("owner", owner_panel))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("gban", gban_user))
    app.add_handler(CommandHandler("approve", approve_user))
    app.add_handler(CommandHandler("report", report_system))
    
    # NEW Protection commands
    app.add_handler(CommandHandler("protection", protection_status))
    app.add_handler(CommandHandler("addbadsticker", add_bad_sticker))
    app.add_handler(CommandHandler("delbadsticker", del_bad_sticker))
    app.add_handler(CommandHandler("reports", view_reports))
    app.add_handler(CommandHandler("antiflood", toggle_antiflood))
    
    # Economy
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("bal", balance))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("pay", pay))
    app.add_handler(CommandHandler("rob", rob_user))
    app.add_handler(CommandHandler("kill", kill_user))
    app.add_handler(CommandHandler("bet", bet_dice))
    app.add_handler(CommandHandler("top", top_group))
    app.add_handler(CommandHandler("globaltop", top_group))
    
    # Games
    app.add_handler(CommandHandler("rps", rps_game))
    app.add_handler(CommandHandler("ttt", ttt_game))
    app.add_handler(CommandHandler("trace", trace_game))
    app.add_handler(CommandHandler("trivia", trivia_game))
    app.add_handler(CommandHandler("spin", spin_member))
    app.add_handler(CommandHandler("8ball", eight_ball))
    app.add_handler(CommandHandler("roll", roll_dice))
    app.add_handler(CommandHandler("dice", roll_dice))
    
    # Moderation
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("kick", kick_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("tmute", tmute_user))
    app.add_handler(CommandHandler("pin", pin_message))
    app.add_handler(CommandHandler("unpin", unpin_message))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("promote", promote_user))
    app.add_handler(CommandHandler("demote", demote_user))
    app.add_handler(CommandHandler("lock", lock_group))
    app.add_handler(CommandHandler("unlock", unlock_group))
    app.add_handler(CommandHandler("lockstickers", lock_stickers))
    app.add_handler(CommandHandler("unlockstickers", unlock_stickers))
    
    # Fun & Desi
    app.add_handler(CommandHandler("t", truth_cmd))
    app.add_handler(CommandHandler("d", dare_cmd))
    app.add_handler(CommandHandler("rizz", rizz_cmd))
    app.add_handler(CommandHandler("roast", roast_cmd))
    app.add_handler(CommandHandler("shayari", shayari_cmd))
    app.add_handler(CommandHandler("hug", hug_cmd))
    app.add_handler(CommandHandler("slap", slap_cmd))
    app.add_handler(CommandHandler("kiss", kiss_cmd))
    app.add_handler(CommandHandler("punch", punch_cmd))
    app.add_handler(CommandHandler("pat", pat_cmd))
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

    # Protection handlers
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, handle_edited_message))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_TITLE | filters.StatusUpdate.NEW_CHAT_PHOTO, handle_gc_change))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_stickers))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Aegis V19.0 PROTECTED running...")
    app.run_polling()

if __name__ == '__main__':
    main()
