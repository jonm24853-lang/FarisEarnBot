import os
import logging
import sqlite3
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# الإعدادات
# =========================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_FILE = "faris_earn.db"

# =========================
# نظام النقاط
# =========================

# 5000 نقطة = 1 USDT
POINTS_PER_USDT = 5000

# الحد الأدنى للسحب
# 5000 نقطة = 1 USDT
MIN_WITHDRAW_POINTS = 5000

# مكافأة التسجيل
WELCOME_BONUS = 100

# مكافأة الإحالة
REFERRAL_BONUS = 500


# =========================
# Logging
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================
# قاعدة البيانات
# =========================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            points INTEGER DEFAULT 0,
            referred_by INTEGER,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            points INTEGER,
            usdt REAL,
            wallet TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# =========================
# المستخدم
# =========================

def get_user(user_id):
    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    conn.close()

    return user


def create_user(
    user_id,
    username,
    first_name,
    referred_by=None
):
    conn = get_db()

    existing = conn.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    if existing:
        conn.close()
        return False

    conn.execute("""
        INSERT INTO users
        (
            user_id,
            username,
            first_name,
            points,
            referred_by,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        username or "",
        first_name or "",
        WELCOME_BONUS,
        referred_by,
        datetime.now().isoformat(),
    ))

    # مكافأة صاحب رابط الإحالة
    if referred_by and referred_by != user_id:

        # نتأكد أن صاحب الإحالة موجود
        referrer = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (referred_by,)
        ).fetchone()

        if referrer:
            conn.execute("""
                UPDATE users
                SET points = points + ?
                WHERE user_id = ?
            """, (
                REFERRAL_BONUS,
                referred_by
            ))

    conn.commit()
    conn.close()

    return True


def add_points(user_id, points):
    conn = get_db()

    conn.execute("""
        UPDATE users
        SET points = points + ?
        WHERE user_id = ?
    """, (
        points,
        user_id
    ))

    conn.commit()
    conn.close()


# =========================
# لوحة الأزرار
# =========================

def main_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💰 رصيدي",
                callback_data="balance"
            ),
            InlineKeyboardButton(
                "👥 الإحالة",
                callback_data="referral"
            ),
        ],
        [
            InlineKeyboardButton(
                "🎁 المهام",
                callback_data="tasks"
            ),
            InlineKeyboardButton(
                "💸 السحب",
                callback_data="withdraw"
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 إحصائياتي",
                callback_data="stats"
            ),
        ],
    ])


# =========================
# /start
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    referred_by = None

    if context.args:

        try:
            referred_by = int(context.args[0])

        except ValueError:
            referred_by = None

    created = create_user(
        user.id,
        user.username,
        user.first_name,
        referred_by
    )

    text = f"""
👋 أهلاً بك {user.first_name}

🎉 مرحباً بك في Faris Earn

💰 اربح النقاط من خلال المهام والإحالات.

💎 نظام التحويل:

⭐ 5000 نقطة = 1 USDT

💸 الحد الأدنى للسحب:

5000 نقطة = 1 USDT

🎁 مكافأة التسجيل:

{WELCOME_BONUS} نقطة

👥 مكافأة الإحالة:

{REFERRAL_BONUS} نقطة

اختر من القائمة 👇
"""

    await update.message.reply_text(
        text,
        reply_markup=main_keyboard()
    )


# =========================
# الرصيد
# =========================

async def balance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user = get_user(query.from_user.id)

    if not user:

        await query.message.reply_text(
            "❌ لم يتم العثور على حسابك."
        )

        return

    points = user["points"]

    usdt = points / POINTS_PER_USDT

    text = f"""
💰 رصيدك

⭐ النقاط:
{points:,}

💵 القيمة:

{usdt:.4f} USDT

📌 نظام التحويل:

5000 نقطة = 1 USDT

💸 الحد الأدنى للسحب:

5000 نقطة = 1 USDT
"""

    await query.message.reply_text(
        text,
        reply_markup=main_keyboard()
    )


# =========================
# الإحالة
# =========================

async def referral(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    bot = await context.bot.get_me()

    referral_link = (
        f"https://t.me/{bot.username}"
        f"?start={query.from_user.id}"
    )

    text = f"""
👥 نظام الإحالة

🎁 اربح {REFERRAL_BONUS} نقطة
عن كل شخص يسجل عن طريق رابطك.

🔗 رابط الإحالة الخاص بك:

{referral_link}

📢 شارك الرابط مع أصدقائك.
"""

    await query.message.reply_text(
        text,
        reply_markup=main_keyboard()
    )


# =========================
# المهام
# =========================

async def tasks(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    text = """
🎁 المهام

حالياً يمكنك الربح من خلال:

👥 دعوة الأصدقاء

🎁 مكافأة التسجيل

⚙️ سيتم إضافة المزيد من المهام لاحقاً.
"""

    await query.message.reply_text(
        text,
        reply_markup=main_keyboard()
    )


# =========================
# الإحصائيات
# =========================

async def stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user = get_user(query.from_user.id)

    if not user:
        return

    conn = get_db()

    referrals = conn.execute("""
        SELECT COUNT(*) AS count
        FROM users
        WHERE referred_by = ?
    """, (
        query.from_user.id,
    )).fetchone()["count"]

    conn.close()

    points = user["points"]

    usdt = points / POINTS_PER_USDT

    text = f"""
📊 إحصائياتك

⭐ النقاط:

{points:,}

👥 عدد الإحالات:

{referrals}

💵 القيمة:

{usdt:.4f} USDT
"""

    await query.message.reply_text(
        text,
        reply_markup=main_keyboard()
    )


# =========================
# السحب
# =========================

async def withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user = get_user(query.from_user.id)

    if not user:
        return

    points = user["points"]

    if points < MIN_WITHDRAW_POINTS:

        missing = (
            MIN_WITHDRAW_POINTS - points
        )

        text = f"""
❌ لا يمكنك السحب حالياً.

⭐ رصيدك:

{points:,} نقطة

💸 الحد الأدنى:

{MIN_WITHDRAW_POINTS:,} نقطة

💵 الحد الأدنى:

1 USDT

📌 تحتاج إلى:

{missing:,} نقطة إضافية.
"""

        await query.message.reply_text(
            text,
            reply_markup=main_keyboard()
        )

        return

    context.user_data[
        "withdraw_step"
    ] = "wallet"

    await query.message.reply_text(
        """
💳 طلب السحب

أرسل الآن عنوان محفظة USDT
التي تريد استلام المبلغ عليها.

⚠️ تأكد من صحة العنوان قبل الإرسال.
"""
    )


# =========================
# استقبال المحفظة
# =========================

async def receive_wallet(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if context.user_data.get(
        "withdraw_step"
    ) != "wallet":

        return

    wallet = update.message.text.strip()

    if len(wallet) < 10:

        await update.message.reply_text(
            "❌ عنوان المحفظة يبدو غير صحيح.\n"
            "أرسل عنواناً صحيحاً."
        )

        return

    db_user = get_user(user.id)

    if not db_user:
        return

    points = db_user["points"]

    if points < MIN_WITHDRAW_POINTS:

        context.user_data.clear()

        await update.message.reply_text(
            "❌ رصيدك أصبح أقل من الحد الأدنى للسحب.",
            reply_markup=main_keyboard()
        )

        return

    usdt = points / POINTS_PER_USDT

    conn = get_db()

    conn.execute("""
        INSERT INTO withdrawals
        (
            user_id,
            points,
            usdt,
            wallet,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user.id,
        points,
        usdt,
        wallet,
        "pending",
        datetime.now().isoformat()
    ))

    # تصفير الرصيد بعد تسجيل الطلب
    conn.execute("""
        UPDATE users
        SET points = 0
        WHERE user_id = ?
    """, (
        user.id,
    ))

    conn.commit()
    conn.close()

    context.user_data.clear()

    await update.message.reply_text(
        f"""
✅ تم تسجيل طلب السحب.

💵 المبلغ:

{usdt:.4f} USDT

⭐ النقاط:

{points:,}

💳 المحفظة:

{wallet}

⏳ الحالة:

قيد المراجعة

سيتم مراجعة الطلب من الإدارة.
""",
        reply_markup=main_keyboard()
    )

    # إرسال إشعار للإدارة
    if ADMIN_ID:

        try:

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"""
🚨 طلب سحب جديد

👤 المستخدم:

{user.first_name}

🆔 ID:

{user.id}

⭐ النقاط:

{points:,}

💵 المبلغ:

{usdt:.4f} USDT

💳 المحفظة:

{wallet}

⏳ الحالة:

Pending
"""
            )

        except Exception as e:

            logger.error(
                f"Admin notification error: {e}"
            )


# =========================
# لوحة الإدارة
# =========================

async def admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ غير مصرح لك."
        )

        return

    conn = get_db()

    users = conn.execute("""
        SELECT COUNT(*) AS count
        FROM users
    """).fetchone()["count"]

    pending = conn.execute("""
        SELECT COUNT(*) AS count
        FROM withdrawals
        WHERE status = 'pending'
    """).fetchone()["count"]

    conn.close()

    await update.message.reply_text(
        f"""
👑 لوحة الإدارة

👥 عدد المستخدمين:

{users}

💸 طلبات السحب المعلقة:

{pending}

💎 نظام التحويل:

5000 نقطة = 1 USDT
"""
    )


# =========================
# إضافة نقاط
# =========================

async def addpoints(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ غير مصرح لك."
        )

        return

    if len(context.args) != 2:

        await update.message.reply_text(
            "الاستخدام:\n"
            "/addpoints USER_ID POINTS"
        )

        return

    try:

        user_id = int(context.args[0])

        points = int(context.args[1])

    except ValueError:

        await update.message.reply_text(
            "❌ البيانات غير صحيحة."
        )

        return

    user = get_user(user_id)

    if not user:

        await update.message.reply_text(
            "❌ المستخدم غير موجود."
        )

        return

    add_points(
        user_id,
        points
    )

    await update.message.reply_text(
        f"""
✅ تمت إضافة النقاط.

👤 المستخدم:

{user_id}

⭐ النقاط المضافة:

{points:,}
"""
    )


# =========================
# إلغاء
# =========================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data.clear()

    await update.message.reply_text(
        "❌ تم إلغاء العملية.",
        reply_markup=main_keyboard()
    )


# =========================
# تشغيل البوت
# =========================

def main():

    if not TOKEN:

        raise ValueError(
            "BOT_TOKEN غير موجود في Environment Variables"
        )

    init_db()

    application = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # الأوامر
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin
        )
    )

    application.add_handler(
        CommandHandler(
            "addpoints",
            addpoints
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel
        )
    )

    # الأزرار
    application.add_handler(
        CallbackQueryHandler(
            balance,
            pattern="^balance$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            referral,
            pattern="^referral$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            tasks,
            pattern="^tasks$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            withdraw,
            pattern="^withdraw$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            stats,
            pattern="^stats$"
        )
    )

    # استقبال عنوان المحفظة
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_wallet
        )
    )

    print(
        "Faris Earn Bot is running..."
    )

    application.run_polling()


# =========================
# START
# =========================

if __name__ == "__main__":
    main()
