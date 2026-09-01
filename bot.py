import os
import logging
import sqlite3
from datetime import datetime, date

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

# 1000 نقطة = 1 USDT
POINTS_PER_USDT = 1000

# الحد الأدنى للسحب = 1000 نقطة = 1 USDT
MIN_WITHDRAW_POINTS = 1000

WELCOME_BONUS = 100

REFERRAL_BONUS = 500

CHANNEL_BONUS = 100

YOUTUBE_BONUS = 100

DAILY_BONUS = 100

# =========================
# الروابط
# =========================

TELEGRAM_CHANNEL = "@farehes"

TELEGRAM_CHANNEL_LINK = "https://t.me/farehes"

YOUTUBE_CHANNEL_LINK = "https://www.youtube.com/@VsdGggf"

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
            created_at TEXT,
            channel_bonus INTEGER DEFAULT 0,
            youtube_bonus INTEGER DEFAULT 0,
            last_daily TEXT
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

    columns = [
        row["name"]
        for row in cur.execute(
            "PRAGMA table_info(users)"
        ).fetchall()
    ]

    if "channel_bonus" not in columns:
        cur.execute(
            "ALTER TABLE users "
            "ADD COLUMN channel_bonus INTEGER DEFAULT 0"
        )

    if "youtube_bonus" not in columns:
        cur.execute(
            "ALTER TABLE users "
            "ADD COLUMN youtube_bonus INTEGER DEFAULT 0"
        )

    if "last_daily" not in columns:
        cur.execute(
            "ALTER TABLE users "
            "ADD COLUMN last_daily TEXT"
        )

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
            created_at,
            channel_bonus,
            youtube_bonus,
            last_daily
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        username or "",
        first_name or "",
        WELCOME_BONUS,
        referred_by,
        datetime.now().isoformat(),
        0,
        0,
        None,
    ))

    # مكافأة الإحالة

    if referred_by and referred_by != user_id:

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

    create_user(
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
⭐ 1000 نقطة = 1 USDT

💸 الحد الأدنى للسحب:
1000 نقطة = 1 USDT

🎁 مكافأة التسجيل:
{WELCOME_BONUS} نقطة

👥 مكافأة الإحالة:
{REFERRAL_BONUS} نقطة

📢 مكافأة Telegram:
{CHANNEL_BONUS} نقطة

📺 مكافأة YouTube:
{YOUTUBE_BONUS} نقطة

🎁 المكافأة اليومية:
{DAILY_BONUS} نقطة

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
1000 نقطة = 1 USDT

💸 الحد الأدنى للسحب:
1000 نقطة = 1 USDT
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

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 اشترك في Telegram",
                url=TELEGRAM_CHANNEL_LINK
            )
        ],
        [
            InlineKeyboardButton(
                "✅ تحقق من Telegram",
                callback_data="check_channel"
            )
        ],
        [
            InlineKeyboardButton(
                "📺 افتح YouTube",
                url=YOUTUBE_CHANNEL_LINK
            )
        ],
        [
            InlineKeyboardButton(
                "✅ احصل على مكافأة YouTube",
                callback_data="youtube_bonus"
            )
        ],
        [
            InlineKeyboardButton(
                "🎁 المكافأة اليومية",
                callback_data="daily_bonus"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 دعوة الأصدقاء",
                callback_data="referral"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 القائمة الرئيسية",
                callback_data="main_menu"
            )
        ],
    ])

    text = f"""
🎁 المهام

📢 اشتراك Telegram
⭐ +{CHANNEL_BONUS} نقطة

📺 قناة YouTube
⭐ +{YOUTUBE_BONUS} نقطة

🎁 المكافأة اليومية
⭐ +{DAILY_BONUS} نقطة
مرة واحدة يومياً

👥 دعوة الأصدقاء
⭐ +{REFERRAL_BONUS} نقطة
لكل إحالة ناجحة

نفذ المهام واحصل على النقاط 👇
"""

    await query.message.reply_text(
        text,
        reply_markup=keyboard
    )


# =========================
# التحقق من Telegram
# =========================

async def check_channel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    user_id = query.from_user.id

    try:

        member = await context.bot.get_chat_member(
            chat_id=TELEGRAM_CHANNEL,
            user_id=user_id
        )

        if member.status not in [
            "member",
            "administrator",
            "creator"
        ]:

            await query.answer(
                "❌ اشترك في القناة أولاً.",
                show_alert=True
            )

            return

        user = get_user(user_id)

        if not user:
            return

        if user["channel_bonus"] == 1:

            await query.answer(
                "ℹ️ حصلت على مكافأة Telegram مسبقاً.",
                show_alert=True
            )

            return

        conn = get_db()

        conn.execute("""
            UPDATE users
            SET points = points + ?,
                channel_bonus = 1
            WHERE user_id = ?
        """, (
            CHANNEL_BONUS,
            user_id
        ))

        conn.commit()
        conn.close()

        await query.answer(
            f"🎉 +{CHANNEL_BONUS} نقطة!",
            show_alert=True
        )

        await query.message.reply_text(
            f"""
✅ تم التحقق بنجاح!

📢 اشتراك Telegram مؤكد.

🎁 المكافأة:
+{CHANNEL_BONUS} نقطة
""",
            reply_markup=main_keyboard()
        )

    except Exception as e:

        logger.error(
            f"Telegram verification error: {e}"
        )

        await query.answer(
            "❌ حدث خطأ أثناء التحقق.",
            show_alert=True
        )


# =========================
# مكافأة YouTube
# =========================

async def youtube_bonus(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    user = get_user(user_id)

    if not user:
        return

    if user["youtube_bonus"] == 1:

        await query.message.reply_text(
            "ℹ️ حصلت على مكافأة YouTube مسبقاً.",
            reply_markup=main_keyboard()
        )

        return

    conn = get_db()

    conn.execute("""
        UPDATE users
        SET points = points + ?,
            youtube_bonus = 1
        WHERE user_id = ?
    """, (
        YOUTUBE_BONUS,
        user_id
    ))

    conn.commit()
    conn.close()

    await query.message.reply_text(
        f"""
🎉 تم تسجيل مهمة YouTube!

📺 شكراً لدعم القناة.

🎁 المكافأة:
+{YOUTUBE_BONUS} نقطة

⚠️ ملاحظة:
البوت لا يستطيع التحقق تلقائياً من اشتراك YouTube.
""",
        reply_markup=main_keyboard()
    )


# =========================
# المكافأة اليومية
# =========================

async def daily_bonus(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    user = get_user(user_id)

    if not user:
        return

    today = date.today().isoformat()

    if user["last_daily"] == today:

        await query.message.reply_text(
            """
⏳ لقد استلمت المكافأة اليومية اليوم.

🎁 عد غداً للحصول على مكافأتك.
""",
            reply_markup=main_keyboard()
        )

        return

    conn = get_db()

    conn.execute("""
        UPDATE users
        SET points = points + ?,
            last_daily = ?
        WHERE user_id = ?
    """, (
        DAILY_BONUS,
        today,
        user_id
    ))

    conn.commit()
    conn.close()

    await query.message.reply_text(
        f"""
🎉 مبروك!

🎁 حصلت على المكافأة اليومية.

⭐ +{DAILY_BONUS} نقطة

📅 عد غداً للحصول على مكافأة جديدة.
""",
        reply_markup=main_keyboard()
    )


# =========================
# القائمة الرئيسية
# =========================

async def main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.message.reply_text(
        "🏠 القائمة الرئيسية",
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

أرسل الآن عنوان محفظة USDT.

⚠️ تأكد من صحة العنوان قبل الإرسال.

لإلغاء العملية استخدم:
 /cancel
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

    # إشعار الإدارة

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

💎 التحويل:
1000 نقطة = 1 USDT

🎁 التسجيل:
{WELCOME_BONUS} نقطة

👥 الإحالة:
{REFERRAL_BONUS} نقطة

📢 Telegram:
{CHANNEL_BONUS} نقطة

📺 YouTube:
{YOUTUBE_BONUS} نقطة

🎁 اليومية:
{DAILY_BONUS} نقطة
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

    if points <= 0:

        await update.message.reply_text(
            "❌ يجب أن تكون النقاط أكبر من صفر."
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

    application.add_handler(
        CallbackQueryHandler(
            check_channel,
            pattern="^check_channel$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            youtube_bonus,
            pattern="^youtube_bonus$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            daily_bonus,
            pattern="^daily_bonus$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            main_menu,
            pattern="^main_menu$"
        )
    )

    # استقبال المحفظة

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
