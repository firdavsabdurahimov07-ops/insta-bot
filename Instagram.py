# Instagram.py
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
import requests

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --- Config
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # agar servisda webhook ishlatmoqchi bo'lsang
PORT = int(os.getenv("PORT", 8080))

if not BOT_TOKEN:
    raise RuntimeError("Iltimos .env faylga BOT_TOKEN ni qo'ying")

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
            "downloads": 0,  # nechta video yuklagan
            "first_name": user_info.get("first_name") if user_info else None,
        }
    return key

# --- Utility: extract instagram url
def extract_instagram_url(text):
    if not text:
        return None
    patterns = [
        r"(https?://(?:www\.)?instagram\.com/[^\s]+)",
        r"(https?://instagr\.am/[^\s]+)"
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return None

# --- MOCK fetch function (sinov uchun)
def fetch_video_mock(insta_url):
    """
    Mock: haqiqiy yuklab oluvchi kodni keyin shu bilan almashtirasiz.
    Hozirda test uchun ishlatiladi — real video URL qaytaradi.
    """
    # sample video (1MB) — faqat sinov uchun
    return "https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_1mb.mp4"

# Agar hohlasang keyingi bosqichda bu funksiyani scraping yoki API qilaiz:
# def fetch_video_real(insta_url, proxies=None): ...

# --- /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    user_key = ensure_user(data, user.id, {"first_name": user.first_name})
    args = context.args or []

    # referralni qabul qilish (agar /start <ref> bilan kelsa)
    if args:
        ref = args[0]
        if ref != str(user.id) and ref in data:
            if data[user_key]["invited_by"] is None:
                data[user_key]["invited_by"] = ref
                data[ref]["referrals"] = data[ref].get("referrals", 0) + 1
                # agar referrer 1 yoki undan ortiq bo'lsa, unga ruxsat bering
                if data[ref]["referrals"] >= 1:
                    data[ref]["is_allowed"] = True

    save_data(data)

    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user.id}"
    my_referrals = data[user_key]["referrals"]
    downloads = data[user_key]["downloads"]
    allowed = data[user_key]["is_allowed"]

    text = (
    f"👋 Salom, {user.first_name}!\n\n"
    f"Sening referral havolang:\n{ref_link}\n\n"
    f"🔗 Taklif qilganlar: {my_referrals}\n"
    f"📥 Yuklagan videolar: {downloads}\n\n"
    f"{'✅ Siz ruxsatga egasiz va cheksiz yuklab olishingiz mumkin.' if allowed else '⚠️ Siz hozir 1 marta bepul yuklab olasiz. Keyin 1 do‘st taklif qilmaguningizcha yana yuklab bo‘lmaydi.'}\n\n"
    "Video yuklash uchun linkni to‘g‘ridan-to‘g‘ri yuboring yoki /download <instagram_link> komandasi orqali yuboring."
)
    await update.message.reply_text(text)

# --- /download
async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    key = ensure_user(data, user.id, {"first_name": user.first_name})

    user_data = data[key]
    downloads = user_data.get("downloads", 0)
    allowed = user_data.get("is_allowed", False)

    # agar allaqachon 1 ta yuklagan va ruxsat yo'q bo'lsa - rad et
    if not allowed and downloads >= 1:
        await update.message.reply_text(
            "❌ Siz allaqachon 1 marta video yuklab olgansiz. Endi do‘st taklif qilmaguningizcha yana yuklab bo‘lmaydi."
        )
        return

    # linkni aniqlash: args yoki message matni
    text = " ".join(context.args) if context.args else (update.message.text if update.message else "")
    insta_url = extract_instagram_url(text)
    if not insta_url:
        # agar foydalanuvchi reply qildi va reply-da link bo'lsa tekshir
        if update.message and update.message.reply_to_message and update.message.reply_to_message.text:
            insta_url = extract_instagram_url(update.message.reply_to_message.text)

    if not insta_url:
        await update.message.reply_text("❗ Iltimos, to'g'ri Instagram link yuboring: /download <link>")
        return

    msg = await update.message.reply_text("🎬 Yuklanmoqda... Iltimos kuting.")

    # hozir mock ishlatamiz — keyin realni shu bilan almashtirasiz
    video_url = fetch_video_mock(insta_url)

    if not video_url:
        await msg.edit_text("❌ Video topilmadi yoki yuklab olishda xato yuz berdi.")
        return

    # foydalanuvchiga link yuborish (agar xohlasang faylni to'g'ridan-to'g'ri yuborishni keyin qo'shamiz)
    try:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎥 Yuklandi:\n{video_url}")
        # update download count
        user_data["downloads"] = downloads + 1
        data[key] = user_data
        save_data(data)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"Xatolik: {e}")

# --- /stats (faqat admin)
ADMIN_IDS = {123456789}  # 👉 bu yerga o'z Telegram ID'ingni yoz

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # faqat admin ko'ra oladi
    if ADMIN_IDS and user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Sizda bu ma'lumotni ko'rish uchun ruxsat yo'q.")
        return

    data = load_data()
    total = len(data)
    total_allowed = sum(1 for v in data.values() if v.get("is_allowed"))

    await update.message.reply_text(
        f"📊 Jami foydalanuvchilar: {total}\n"
        f"✅ Ruxsatga ega: {total_allowed}\n"
        f"📥 Jami yuklangan videolar: {total_downloads}"
    )

# --- register any message (saqlash uchun)
async def register_on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    chat = update.effective_chat
    user = update.effective_user
    ensure_user(data, chat.id, {"first_name": user.first_name if user else None})
    save_data(data)

# --- main: polling yoki webhookga mos
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("download", download))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), register_on_message))

    print("✅ Bot tayyor. Polling yoki webhook rejimiga qarab ishga tushadi...")

    if WEBHOOK_URL:
        # webhook rejimi (servisda ishlatish uchun)
        print("🔗 Webhook rejimi: ", WEBHOOK_URL)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
        )
    else:
        # lokal test uchun polling
        app.run_polling()

if __name__ == "__main__":
    main()

