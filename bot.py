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
REFERRAL_BONUS = 100
MIN_WITHDRAW = 1000

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


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


def ensure_user(user_id, username, first_name):
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
        """
        SELECT balance, referrals, referred_by
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    )

    result = cursor.fetchone()
    db.close()

    return result


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id

    db = get_db()
    cursor = db.cursor()

    # إنشاء المستخدم إذا لم يكن موجودًا
    cursor.execute(
        "SELECT user_id, referred_by FROM users WHERE user_id = ?",
        (user_id,)
    )

    existing = cursor.fetchone()

    if not existing:

        cursor.execute(
            """
            INSERT INTO users
            (user_id, username, first_name, balance, referrals)
            VALUES (?, ?, ?, 0, 0)
            """,
            (
                user_id,
                user.username or "",
                user.first_name or "",
            )
        )

        existing_referred_by = None

    else:
        existing_referred_by = existing[1]

        # تحديث بيانات المستخدم
        cursor.execute(
            """
            UPDATE users
            SET username = ?, first_name = ?
            WHERE user_id = ?
            """,
            (
                user.username or "",
                user.first_name or "",
                user_id,
            )
        )

    referral_added = False
    referrer_id = None

    # معالجة رابط الإحالة
    if context.args:

        try:
            referrer_id = int(context.args[0])

            # منع إحالة النفس
            if referrer_id != user_id:

                # لا نضيف إحالة إذا كان لديه محيل سابق
                if existing_referred_by is None:

                    cursor.execute(
                        "SELECT user_id FROM users WHERE user_id = ?",
                        (referrer_id,)
                    )

                    referrer_exists = cursor.fetchone()

                    if referrer_exists:

                        cursor.execute(
                            """
                            UPDATE users
                            SET referred_by = ?
                            WHERE user_id = ?
                            """,
                            (referrer_id, user_id)
                        )

                        cursor.execute(
                            """
                            UPDATE users
                            SET balance = balance + ?,
                                referrals = referrals + 1
                            WHERE user_id = ?
                            """,
                            (REFERRAL_BONUS, referrer_id)
                        )

                        referral_added = True

        except ValueError:
            pass

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

    message = (
        "🤖 أهلاً بك في FarisEarnBot 💎\n\n"
        "💎 اكسب النقاط من المهام ودعوة الأصدقاء.\n\n"
        "اختر من القائمة:"
    )

    if referral_added:
        message += (
            "\n\n🎉 تم تسجيلك عن طريق رابط إحالة!"
        )

    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    ensure_user(
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

        text = (
            "👥 دعوة الأصدقاء\n\n"
            "🔗 رابط دعوتك الخاص:\n\n"
            f"https://t.me/{bot.username}?start={user_id}\n\n"
            f"🎁 تحصل على {REFERRAL_BONUS} نقطة عن كل إحالة ناجحة."
        )

    elif query.data == "withdraw":

        user_data = get_user(user_id)
        balance = user_data[0] if user_data else 0

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
        balance = user_data[0] if user_data else 0

        db.close()

        text = (
            "📊 إحصائياتك\n\n"
            f"👥 إحالاتك: {referrals}\n"
            f"💎 رصيدك: {balance} نقطة\n\n"
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
