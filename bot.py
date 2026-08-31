import os
import logging
import sqlite3

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_FILE = "faris_earn.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


# =========================
# قاعدة البيانات
# =========================

def get_db():
    return sqlite3.connect(DB_FILE)


def init_db():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            referrals INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL
        )
    """)

    db.commit()
    db.close()


def add_user(user_id, username, first_name):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,)
    )

    if not cursor.fetchone():
        cursor.execute(
            """
            INSERT INTO users
            (user_id, username, first_name, balance, referrals)
            VALUES (?, ?, ?, 0, 0)
            """,
            (user_id, username, first_name)
        )

    db.commit()
    db.close()


def get_user(user_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT balance, referrals FROM users WHERE user_id = ?",
        (user_id,)
    )

    result = cursor.fetchone()
    db.close()

    return result


# =========================
# /start
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id

    # إنشاء المستخدم إذا كان جديدًا
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,)
    )

    existing_user = cursor.fetchone()

    if not existing_user:

        referred_by = None

        # فحص رابط الإحالة
        if context.args:
            try:
                referrer_id = int(context.args[0])

                if referrer_id != user_id:
                    cursor.execute(
                        "SELECT user_id FROM users WHERE user_id = ?",
                        (referrer_id,)
                    )

                    referrer_exists = cursor.fetchone()

                    if referrer_exists:
                        referred_by = referrer_id

            except ValueError:
                pass

        cursor.execute(
            """
            INSERT INTO users
            (user_id, username, first_name, balance, referrals, referred_by)
            VALUES (?, ?, ?, 0, 0, ?)
            """,
            (
                user_id,
                user.username or "",
                user.first_name or "",
                referred_by,
            )
        )

        # مكافأة الإحالة
        if referred_by:

            REFERRAL_BONUS = 100

            cursor.execute(
                """
                UPDATE users
                SET balance = balance + ?,
                    referrals = referrals + 1
                WHERE user_id = ?
                """,
                (REFERRAL_BONUS, referred_by)
            )

    db.commit()
    db.close()

    keyboard = [
        [
            InlineKeyboardButton("💰 رصيدي", callback_data="balance"),
            InlineKeyboardButton("🎯 المهام", callback_data="tasks"),
        ],
        [
            InlineKeyboardButton("👥 دعوة الأصدقاء", callback_data="referral"),
            InlineKeyboardButton("💳 السحب", callback_data="withdraw"),
        ],
        [
            InlineKeyboardButton("📊 الإحصائيات", callback_data="stats"),
        ],
    ]

    if user_id == ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton(
                "👑 لوحة الأدمن",
                callback_data="admin"
            )
        ])

    await update.message.reply_text(
        "🤖 أهلاً بك في FarisEarnBot 💎\n\n"
        "اكسب النقاط من المهام ودعوة الأصدقاء.\n\n"
        "اختر من القائمة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# الأزرار
# =========================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    # تأكد أن المستخدم موجود
    add_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or ""
    )

    if query.data == "balance":

        user_data = get_user(user_id)
        balance = user_data[0] if user_data else 0

        text = (
            "💰 رصيدك\n\n"
            f"💎 الرصيد الحالي: {balance} نقطة"
        )

    elif query.data == "tasks":

        text = (
            "🎯 المهام\n\n"
            "🔒 لا توجد مهام متاحة حاليًا.\n\n"
            "سيتم إضافة المهام قريبًا."
        )

    elif query.data == "referral":

        bot = await context.bot.get_me()
        bot_username = bot.username

        text = (
            "👥 دعوة الأصدقاء\n\n"
            "🔗 رابط دعوتك الخاص:\n\n"
            f"https://t.me/{bot_username}?start={user_id}\n\n"
            "🎁 عندما ينضم شخص جديد من رابطك تحصل على 100 نقطة."
        )

    elif query.data == "withdraw":

        user_data = get_user(user_id)
        balance = user_data[0] if user_data else 0

        MIN_WITHDRAW = 1000

        if balance >= MIN_WITHDRAW:

            text = (
                "💳 طلب السحب\n\n"
                f"💎 رصيدك: {balance} نقطة\n"
                f"📌 الحد الأدنى للسحب: {MIN_WITHDRAW} نقطة\n\n"
                "سيتم تجهيز نظام السحب قريبًا."
            )

        else:

            text = (
                "💳 السحب\n\n"
                f"💎 رصيدك: {balance} نقطة\n"
                f"📌 الحد الأدنى للسحب: {MIN_WITHDRAW} نقطة\n\n"
                "❌ رصيدك غير كافٍ للسحب حاليًا."
            )

    elif query.data == "stats":

        db = get_db()
        cursor = db.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0

        user_data = get_user(user_id)
        referrals = user_data[1] if user_data else 0

        db.close()

        text = (
            "📊 إحصائياتك\n\n"
            f"👥 إحالاتك: {referrals}\n"
            f"💎 رصيدك: {user_data[0]} نقطة\n\n"
            f"👤 إجمالي المستخدمين: {users_count}\n"
            f"💰 إجمالي النقاط: {total_balance}"
        )

    elif query.data == "admin":

        if user_id != ADMIN_ID:

            text = "⛔ غير مصرح لك."

        else:

            db = get_db()
            cursor = db.cursor()

            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = cursor.fetchone()[0]

            cursor.execute("SELECT SUM(balance) FROM users")
            total_balance = cursor.fetchone()[0] or 0

            db.close()

            text = (
                "👑 لوحة الأدمن\n\n"
                f"👥 المستخدمون: {users_count}\n"
                f"💎 إجمالي النقاط: {total_balance}\n\n"
                "⚙️ سيتم إضافة إدارة المهام والسحب لاحقًا."
            )

    else:

        text = "❌ أمر غير معروف."

    await query.edit_message_text(text)


# =========================
# تشغيل البوت
# =========================

def main():

    if not TOKEN:
        raise ValueError("BOT_TOKEN غير موجود")

    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))

    print("FarisEarnBot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
