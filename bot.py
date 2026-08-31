import os
import logging
import sqlite3
from datetime import datetime, timedelta

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
DAILY_BONUS = 50
MIN_WITHDRAW = 1000

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
            referred_by INTEGER DEFAULT NULL,
            last_daily TEXT DEFAULT NULL
        )
    """)

    # إضافة العمود إذا كانت قاعدة البيانات القديمة لا تحتوي عليه
    try:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN last_daily TEXT DEFAULT NULL"
        )
    except sqlite3.OperationalError:
        pass

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
        SELECT balance, referrals, referred_by, last_daily
        FROM users
        WHERE user_id = ?
        """,
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

    db = get_db()
    cursor = db.cursor()

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

    if context.args:

        try:
            referrer_id = int(context.args[0])

            if referrer_id != user_id:

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
            InlineKeyboardButton("🎁 المكافأة اليومية", callback_data="daily"),
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
        message += "\n\n🎉 تم تسجيل الإحالة بنجاح!"

    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# الأزرار
# =========================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    ensure_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or ""
    )

    # =========================
    # الرصيد
    # =========================

    if query.data == "balance":

        user_data = get_user(user_id)
        balance = user_data[0] if user_data else 0

        text = (
            "💰 رصيدك\n\n"
            f"💎 الرصيد الحالي: {balance} نقطة"
        )

    # =========================
    # المهام
    # =========================

    elif query.data == "tasks":

        text = (
            "🎯 المهام\n\n"
            "🔒 لا توجد مهام متاحة حاليًا.\n\n"
            "سيتم إضافة المهام قريبًا."
        )

    # =========================
    # المكافأة اليومية
    # =========================

    elif query.data == "daily":

        user_data = get_user(user_id)

        last_daily = user_data[3] if user_data else None

        now = datetime.utcnow()

        if last_daily:

            try:
                last_time = datetime.fromisoformat(last_daily)

                next_time = last_time + timedelta(hours=24)

                if now < next_time:

                    remaining = next_time - now

                    hours = int(remaining.total_seconds() // 3600)
                    minutes = int(
                        (remaining.total_seconds() % 3600) // 60
                    )

                    text = (
                        "🎁 المكافأة اليومية\n\n"
                        "❌ لقد حصلت على مكافأتك اليوم.\n\n"
                        f"⏳ المكافأة القادمة بعد: "
                        f"{hours} ساعة و {minutes} دقيقة."
                    )

                else:

                    db = get_db()
                    cursor = db.cursor()

                    cursor.execute(
                        """
                        UPDATE users
                        SET balance = balance + ?,
                            last_daily = ?
                        WHERE user_id = ?
                        """,
                        (
                            DAILY_BONUS,
                            now.isoformat(),
                            user_id,
                        )
                    )

                    db.commit()
                    db.close()

                    text = (
                        "🎉 مبروك!\n\n"
                        f"🎁 حصلت على {DAILY_BONUS} نقطة.\n"
                        "💎 تمت إضافة النقاط إلى رصيدك."
                    )

            except ValueError:

                db = get_db()
                cursor = db.cursor()

                cursor.execute(
                    """
                    UPDATE users
                    SET balance = balance + ?,
                        last_daily = ?
                    WHERE user_id = ?
                    """,
                    (
                        DAILY_BONUS,
                        now.isoformat(),
                        user_id,
                    )
                )

                db.commit()
                db.close()

                text = (
                    "🎉 مبروك!\n\n"
                    f"🎁 حصلت على {DAILY_BONUS} نقطة."
                )

        else:

            db = get_db()
            cursor = db.cursor()

            cursor.execute(
                """
                UPDATE users
                SET balance = balance + ?,
                    last_daily = ?
                WHERE user_id = ?
                """,
                (
                    DAILY_BONUS,
                    now.isoformat(),
                    user_id,
                )
            )

            db.commit()
            db.close()

            text = (
                "🎉 مبروك!\n\n"
                f"🎁 حصلت على {DAILY_BONUS} نقطة.\n"
                "💎 تمت إضافة النقاط إلى رصيدك."
            )

    # =========================
    # الإحالة
    # =========================

    elif query.data == "referral":

        bot = await context.bot.get_me()

        text = (
            "👥 دعوة الأصدقاء\n\n"
            "🔗 رابط دعوتك الخاص:\n\n"
            f"https://t.me/{bot.username}?start={user_id}\n\n"
            f"🎁 تحصل على {REFERRAL_BONUS} نقطة "
            "عن كل إحالة ناجحة."
        )

    # =========================
    # السحب
    # =========================

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

    # =========================
    # الإحصائيات
    # =========================

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

    # =========================
    # الأدمن
    # =========================

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
