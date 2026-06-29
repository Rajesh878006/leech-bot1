import telebot
import requests
import os
import tempfile
import sqlite3
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ===================== কনফিগ (হার্ডকোড করা) =====================
BOT_TOKEN = "8337412189:AAFTjD1IzHlTcNxrX05FIOcQlUbEaee5aQs"
API_URL = "https://gdmax.xyz/download/telegram.php/"
SERVICE_ACCOUNT_FILE = "service_account.json"
STORAGE_CHANNEL_ID = -1003604032906  # আপনার স্ক্রিনশট থেকে নেওয়া
# ================================================================

bot = telebot.TeleBot(BOT_TOKEN)

# SQLite ডাটাবেস (টোকেন ↔ মেসেজ আইডি)
conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS files (token TEXT PRIMARY KEY, msg_id INTEGER)''')
conn.commit()

@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        token = message.text.split()[1]
    except:
        bot.reply_to(message, "❌ ভুল লিংক! টোকেন নেই।")
        return

    status_msg = bot.reply_to(message, "⏳ ফাইল খুঁজে বের করা হচ্ছে...")

    # ১. SQLite-তে টোকেন খোঁজো
    c.execute("SELECT msg_id FROM files WHERE token = ?", (token,))
    row = c.fetchone()

    if row:
        try:
            bot.edit_message_text("📤 ফাইল পাওয়া গেছে, পাঠানো হচ্ছে...", message.chat.id, status_msg.message_id)
            bot.forward_message(message.chat.id, STORAGE_CHANNEL_ID, row[0])
            bot.delete_message(message.chat.id, status_msg.message_id)
            bot.send_message(message.chat.id, "✅ ফাইল সফলভাবে পাঠানো হয়েছে!")
            return
        except Exception as e:
            bot.edit_message_text(f"⚠️ ফরওয়ার্ড করতে সমস্যা, নতুন করে ডাউনলোড করা হচ্ছে...", message.chat.id, status_msg.message_id)

    # ২. টোকেন ভেরিফাই (ওয়েবসাইটের API)
    try:
        response = requests.get(API_URL + token, timeout=10)
        data = response.json()
    except:
        bot.edit_message_text("❌ API সংযোগ সমস্যা", message.chat.id, status_msg.message_id)
        return

    if data.get('status') != 'success':
        bot.edit_message_text("❌ টোকেন মেলেনি বা মেয়াদ শেষ", message.chat.id, status_msg.message_id)
        return

    drive_id = data['drive_id']
    filename = data['file_name']

    # ৩. গুগল ড্রাইভ থেকে ডাউনলোড
    try:
        bot.edit_message_text("📥 গুগল ড্রাইভ থেকে ডাউনলোড হচ্ছে...", message.chat.id, status_msg.message_id)

        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        drive_service = build('drive', 'v3', credentials=creds)
        request = drive_service.files().get_media(fileId=drive_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp_file:
            downloader = MediaIoBaseDownload(tmp_file, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            tmp_file_path = tmp_file.name

        # ৪. চ্যানেলে আপলোড (স্টোরেজ)
        bot.edit_message_text("📤 ফাইল চ্যানেলে সংরক্ষণ করা হচ্ছে...", message.chat.id, status_msg.message_id)
        with open(tmp_file_path, 'rb') as f:
            sent_msg = bot.send_document(STORAGE_CHANNEL_ID, (filename, f), timeout=600)

        # ৫. SQLite-তে সেভ
        c.execute("INSERT OR REPLACE INTO files (token, msg_id) VALUES (?, ?)", (token, sent_msg.message_id))
        conn.commit()

        # ৬. ইউজারকে ফরওয়ার্ড
        bot.edit_message_text("📤 আপনার ফাইল পাঠানো হচ্ছে...", message.chat.id, status_msg.message_id)
        bot.forward_message(message.chat.id, STORAGE_CHANNEL_ID, sent_msg.message_id)

        bot.delete_message(message.chat.id, status_msg.message_id)
        bot.send_message(message.chat.id, "✅ ফাইল সফলভাবে পাঠানো হয়েছে!")

    except Exception as e:
        bot.edit_message_text(f"❌ সমস্যা: {str(e)}", message.chat.id, status_msg.message_id)
    finally:
        if os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)

print("🤖 বট চালু আছে...")
bot.infinity_polling()
