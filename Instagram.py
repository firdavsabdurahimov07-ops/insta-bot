import json
import os
import re
import requests
from dotenv import load_dotenv
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Iltimos .env faylga BOT_TOKEN qo'ying")

DATA_FILE = Path("users.json")

# --- Data helpers
def load_data():
    if not DATA_FILE.exists():
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def ensure_user(data, chat_id, user_info=None):
    key = str(chat_id)
    if key not in data:
        data[key] = {
            "referrals": 0,
            "invited_by": None,
            "is_allowed": False,
            "first_name": user_info.get("first_name") if user_info else None
        }
    return key

# --- Simple referral check on /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    user_key = ensure_user(data, user.id, {"first_name": user.first_name})
    args = context.args

    # If user came via /start <referrer_id>
    if args:
        ref = args[0]
        # Prevent self-referral
        if ref != str(user.id) and ref in data:
            if data[user_key]["invited_by"] is None:
                data[user_key]["invited_by"] = ref
                # award referral to inviter (only once)
                data[ref]["referrals"] = data[ref].get("referrals", 0) + 1
                # mark inviter allowed when they reach >=1 referral
                if data[ref]["referrals"] >= 1:
                    data[ref]["is_allowed"] = True

    save_data(data)

    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user.id}"
    my_referrals = data[user_key].get("referrals", 0)
    allowed = data[user_key].get("is_allowed", False)

    text = (
        f"👋 Salom, {user.first_name}!\n\n"
        f"Sening referal havolang:\n{ref_link}\n\n"
        f"🔗 Taklif qilganlar: {my_referrals}\n"
        f"{'✅ Siz video yuklab olishingiz mumkin.' if allowed else '❌ Avval 1 do‘stni taklif qiling, keyin video yuklab olasiz.'}\n\n"
        "Instagram video yuklab olish uchun:\n"
        "/download <instagram_link>\n\n"
        "Masalan: /download https://www.instagram.com/reel/XXXXXXXXX/"
    )
    await update.message.reply_text(text)

# --- Simple command to show stats (admin only can be enforced)
ADMIN_IDS = set()  # agar kerak bo'lsa, shu yerga admin id qo'y

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ADMIN_IDS and user.id not in ADMIN_IDS:
        await update.message.reply_text("Ruxsat yo'q.")
        return
    data = load_data()
    total = len(data)
    total_allowed = sum(1 for v in data.values() if v.get("is_allowed"))
    await update.message.reply_text(f"Registratsiyalangan chatlar/foydalanuvchilar: {total}\nRuxsat olganlar: {total_allowed}")

# --- Simple Instagram downloader wrapper (placeholder)
# 1) Bu yerda uchinchi tomon 'free' API'ga so'rov yuborish mumkin.
# 2) Mana bir oddiy yakun: API natijasida video URL qaytaradi deb hisoblaymiz.
# 3) Sen o'zing yoqtirgan API bilan ushbu funksiya ichini almashtir.

FREE_DOWNLOADER_API = "https://saveitbackend.example/api/download?url={}"  # <-- O'zgartir

def extract_instagram_url(text):
    # oddiy regex to find instagram url in text
    patterns = [
        r"(https?://(?:www\.)?instagram\.com/[^\s]+)",
        r"(https?://instagr\.am/[^\s]+)"
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return None

def fetch_video_link_from_api(insta_url):
    """
    SaveInsta API orqali Instagram video yoki rasm yuklab olish.
    """
    try:
        api_url = "https://saveinsta.io/api.php?url=" + insta_url
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        resp = requests.get(api_url, headers=headers, timeout=25)

        if resp.status_code == 200:
            try:
                j = resp.json()
            except:
                print("⚠️ JSON format emas, matn sifatida qaytdi.")
                return None

            video_url = j.get("url") or j.get("video") or j.get("result")
            if video_url:
                return video_url
            else:
                print("⚠️ API javobida video topilmadi:", j)
                return None
        else:
            print("⚠️ API status:", resp.status_code)
            return None

    except Exception as e:
        print("fetch_video_link_from_api xatolik:", e)
        return None

# --- /download handler
async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    key = str(user.id)
    ensure_user(data, user.id, {"first_name": user.first_name})

    if not data[key].get("is_allowed", False):
        await update.message.reply_text("❌ Avval 1 do‘st chaqiring — keyin video yuklab olishingiz mumkin.")
        return

    # get link either from args or message
    text = " ".join(context.args) if context.args else (update.message.reply_to_message.text if update.message.reply_to_message else "")
    insta_url = extract_instagram_url(text or update.message.text)
    if not insta_url:
        await update.message.reply_text("Iltimos, Instagram post/reel linkini yuboring: /download <link>")
        return

    # Tell user we're starting
    msg = await update.message.reply_text("🎬 Yuklanmoqda... Iltimos kuting.")

    # Call placeholder API function
    video_url = fetch_video_link_from_api(insta_url)

    if not video_url:
        await msg.edit_text("❌ Video topilmadi yoki API xatosi. Admin bilan bog'laning.")
        return

    # Option A: Agar API bergan to'g'ridan-to'g'ri fayl URL bo'lsa, telegramga yuborish:
    try:
        # Agar fayl juda katta bo'lsa, Telegram cheklovlariga e'tibor ber (50MB cheklovi yoki botga tegishli)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎥 Yuklash tugadi. Mana link:\n{video_url}")
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"Xatolik faylni jo'natishda: {e}")

# --- Save chat id on any message (register)
async def register_on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    chat = update.effective_chat
    user = update.effective_user
    key = ensure_user(data, chat.id, {"first_name": user.first_name if user else None})

    # If chat is a new group/channel registration, invited_by stays None
    # Save first_name if available
    if user:
        data[key]["first_name"] = user.first_name

    save_data(data)

# --- Main
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("download", download))
    app.add_handler(CommandHandler("stats", stats))
    # register any text to keep list updated
    app.add_handler(MessageHandler(filters.ALL, register_on_message))

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()

