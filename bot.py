import os
import logging
import sqlite3
from datetime import datetime, date

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================================================
# الإعدادات
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_FILE = "faris_earn.db"

# =========================================================
# نظام النقاط والسحب
# =========================================================

# 1000 نقطة = 1 TON
POINTS_PER_TON = 1000

# الحد الأدنى للسحب
MIN_WITHDRAW_POINTS = 1000

# الحد الأقصى للسحب في اليوم لكل مستخدم
MAX_WITHDRAWALS_PER_DAY = 2

# =========================================================
# المكافآت
# =========================================================

WELCOME_BONUS = 1000
REFERRAL_BONUS = 5000
CHANNEL_BONUS = 1000
YOUTUBE_BONUS = 1000
DAILY_BONUS = 1000

# =========================================================
# الروابط
# =========================================================

TELEGRAM_CHANNEL = "@farehes"
TELEGRAM_CHANNEL_LINK = "https://t.me/farehes"
YOUTUBE_CHANNEL_LINK = "https://www.youtube.com/@VsdGggf"

# =========================================================
# Logging
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# قاعدة البيانات
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()
    cur = conn.cursor()

    # المستخدمون
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

    # طلبات السحب
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            points INTEGER,
            ton REAL,
            wallet TEXT,
            status TEXT DEFAULT 'pending',
            tx_hash TEXT,
            created_at TEXT,
            processed_at TEXT
        )
    """)

    # دعم قواعد البيانات القديمة
    user_columns = [
        row["name"]
        for row in cur.execute(
            "PRAGMA table_info(users)"
        ).fetchall()
    ]

    if "channel_bonus" not in user_columns:
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN channel_bonus INTEGER DEFAULT 0
        """)

    if "youtube_bonus" not in user_columns:
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN youtube_bonus INTEGER DEFAULT 0
        """)

    if "last_daily" not in user_columns:
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN last_daily TEXT
        """)

    withdrawal_columns = [
        row["name"]
        for row in cur.execute(
            "PRAGMA table_info(withdrawals)"
        ).fetchall()
    ]

    if "ton" not in withdrawal_columns:
        cur.execute("""
            ALTER TABLE withdrawals
            ADD COLUMN ton REAL DEFAULT 0
        """)

    if "tx_hash" not in withdrawal_columns:
        cur.execute("""
            ALTER TABLE withdrawals
            ADD COLUMN tx_hash TEXT
        """)

    if "processed_at" not in withdrawal_columns:
        cur.execute("""
            ALTER TABLE withdrawals
            ADD COLUMN processed_at TEXT
        """)

    conn.commit()
    conn.close()


# =========================================================
# المستخدم
# =========================================================

def get_user(user_id):

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    conn.close()

    return user


def create_user(
    user_id,
    username,
    first_name,
    referred_by=None
):

    conn = get_db()

    existing = conn.execute("""
        SELECT user_id
        FROM users
        WHERE user_id = ?
    """, (user_id,)).fetchone()

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

        referrer = conn.execute("""
            SELECT user_id
            FROM users
            WHERE user_id = ?
        """, (referred_by,)).fetchone()

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


# =========================================================
# حساب عدد السحوبات اليوم
# =========================================================

def get_today_withdrawal_count(user_id):

    today = date.today().isoformat()

    conn = get_db()

    result = conn.execute("""
        SELECT COUNT(*) AS count
        FROM withdrawals
        WHERE user_id = ?
        AND DATE(created_at) = ?
        AND status != 'rejected'
    """, (
        user_id,
        today
    )).fetchone()

    conn.close()

    return result["count"]


# =========================================================
# لوحة الأزرار
# =========================================================

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
                "💎 السحب",
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


# =========================================================
# /start
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

    await update.message.reply_text(
        f"""
👋 أهلاً بك {user.first_name}

🎉 مرحباً بك في Faris Earn

💰 اربح النقاط من خلال المهام والإحالات.

💎 نظام التحويل:
⭐ 1000 نقطة = 1 TON

💸 الحد الأدنى للسحب:
1000 نقطة = 1 TON

🔄 عدد السحوبات:
مرتان يومياً

🎁 مكافأة التسجيل:
{WELCOME_BONUS:,} نقطة

👥 مكافأة الإحالة:
{REFERRAL_BONUS:,} نقطة

📢 مكافأة Telegram:
{CHANNEL_BONUS:,} نقطة

📺 مكافأة YouTube:
{YOUTUBE_BONUS:,} نقطة

🎁 المكافأة اليومية:
{DAILY_BONUS:,} نقطة

اختر من القائمة 👇
""",
        reply_markup=main_keyboard()
    )


# =========================================================
# الرصيد
# =========================================================

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    if not user:
        return

    points = user["points"]
    ton = points / POINTS_PER_TON

    count = get_today_withdrawal_count(
        query.from_user.id
    )

    remaining = max(
        0,
        MAX_WITHDRAWALS_PER_DAY - count
    )

    await query.message.reply_text(
        f"""
💰 رصيدك

⭐ النقاط:
{points:,}

💎 القيمة:
{ton:.4f} TON

📌 التحويل:
1000 نقطة = 1 TON

💸 الحد الأدنى:
1 TON

🔄 السحب اليومي:
{count}/{MAX_WITHDRAWALS_PER_DAY}

📤 السحوبات المتبقية اليوم:
{remaining}
""",
        reply_markup=main_keyboard()
    )


# =========================================================
# الإحالة
# =========================================================

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    bot = await context.bot.get_me()

    referral_link = (
        f"https://t.me/{bot.username}"
        f"?start={query.from_user.id}"
    )

    await query.message.reply_text(
        f"""
👥 نظام الإحالة

🎁 اربح {REFERRAL_BONUS:,} نقطة
عن كل شخص يسجل عن طريق رابطك.

💎 القيمة:
{REFERRAL_BONUS / POINTS_PER_TON:.2f} TON

🔗 رابط الإحالة:

{referral_link}

📢 شارك الرابط مع أصدقائك.
""",
        reply_markup=main_keyboard()
    )


# =========================================================
# المهام
# =========================================================

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

    await query.message.reply_text(
        f"""
🎁 المهام

📢 Telegram
⭐ +{CHANNEL_BONUS:,} نقطة

📺 YouTube
⭐ +{YOUTUBE_BONUS:,} نقطة

🎁 المكافأة اليومية
⭐ +{DAILY_BONUS:,} نقطة

👥 الإحالات
⭐ +{REFERRAL_BONUS:,} نقطة

نفذ المهام واحصل على النقاط 👇
""",
        reply_markup=keyboard
    )


# =========================================================
# التحقق من Telegram
# =========================================================

async def check_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    user_id = query.from_user.id

    await query.answer()

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
                "ℹ️ حصلت على المكافأة مسبقاً.",
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
            f"🎉 +{CHANNEL_BONUS:,} نقطة!",
            show_alert=True
        )

        await query.message.reply_text(
            f"""
✅ تم التحقق بنجاح!

🎁 المكافأة:
+{CHANNEL_BONUS:,} نقطة
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


# =========================================================
# YouTube
# =========================================================

async def youtube_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

🎁 المكافأة:
+{YOUTUBE_BONUS:,} نقطة

⚠️ البوت لا يستطيع التحقق تلقائياً من اشتراك YouTube.
""",
        reply_markup=main_keyboard()
    )


# =========================================================
# المكافأة اليومية
# =========================================================

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user = get_user(user_id)

    if not user:
        return

    today = date.today().isoformat()

    if user["last_daily"] == today:

        await query.message.reply_text(
            "⏳ لقد استلمت المكافأة اليومية اليوم.",
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

🎁 المكافأة اليومية:
+{DAILY_BONUS:,} نقطة

💎 القيمة:
{DAILY_BONUS / POINTS_PER_TON:.2f} TON
""",
        reply_markup=main_keyboard()
    )


# =========================================================
# القائمة الرئيسية
# =========================================================

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "🏠 القائمة الرئيسية",
        reply_markup=main_keyboard()
    )


# =========================================================
# الإحصائيات
# =========================================================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

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
    ton = points / POINTS_PER_TON

    today_count = get_today_withdrawal_count(
        query.from_user.id
    )

    await query.message.reply_text(
        f"""
📊 إحصائياتك

⭐ النقاط:
{points:,}

👥 الإحالات:
{referrals}

💎 القيمة:
{ton:.4f} TON

🔄 سحوبات اليوم:
{today_count}/{MAX_WITHDRAWALS_PER_DAY}
""",
        reply_markup=main_keyboard()
    )


# =========================================================
# السحب
# =========================================================

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user = get_user(user_id)

    if not user:
        return

    # -----------------------------------------------------
    # التحقق من عدد السحوبات اليوم
    # -----------------------------------------------------

    today_count = get_today_withdrawal_count(user_id)

    if today_count >= MAX_WITHDRAWALS_PER_DAY:

        await query.message.reply_text(
            f"""
⛔ وصلت إلى الحد الأقصى للسحب اليوم.

🔄 الحد اليومي:
{MAX_WITHDRAWALS_PER_DAY} سحوبات

📊 استخدمت:
{today_count}/{MAX_WITHDRAWALS_PER_DAY}

🕐 يمكنك السحب مرة أخرى غداً.
""",
            reply_markup=main_keyboard()
        )

        return

    # -----------------------------------------------------
    # الرصيد
    # -----------------------------------------------------

    points = int(user["points"])

    if points < MIN_WITHDRAW_POINTS:

        missing = MIN_WITHDRAW_POINTS - points

        await query.message.reply_text(
            f"""
❌ لا يمكنك السحب حالياً.

⭐ رصيدك:
{points:,} نقطة

💸 الحد الأدنى:
{MIN_WITHDRAW_POINTS:,} نقطة

💎 الحد الأدنى:
1 TON

📌 تحتاج إلى:
{missing:,} نقطة إضافية.
""",
            reply_markup=main_keyboard()
        )

        return

    # -----------------------------------------------------
    # منع طلب سحب آخر قيد المعالجة
    # -----------------------------------------------------

    conn = get_db()

    pending = conn.execute("""
        SELECT id
        FROM withdrawals
        WHERE user_id = ?
        AND status IN ('pending', 'processing')
        LIMIT 1
    """, (
        user_id,
    )).fetchone()

    conn.close()

    if pending:

        await query.message.reply_text(
            """
⏳ لديك طلب سحب قيد المراجعة أو التحويل.

انتظر معالجة الطلب الحالي أولاً.
""",
            reply_markup=main_keyboard()
        )

        return

    context.user_data["withdraw_step"] = "wallet"

    await query.message.reply_text(
        f"""
💎 طلب سحب TON

🔄 السحوبات اليوم:
{today_count}/{MAX_WITHDRAWALS_PER_DAY}

💰 الحد الأدنى:
1 TON

👛 أرسل عنوان محفظة TON الخاصة بك.

مثال:
EQ...

أو:
UQ...

⚠️ تأكد من صحة العنوان.

❌ للإلغاء:
 /cancel
"""
    )


# =========================================================
# فحص عنوان TON
# =========================================================

def looks_like_ton_wallet(wallet):

    wallet = wallet.strip()

    if wallet.startswith("EQ") or wallet.startswith("UQ"):
        return len(wallet) >= 40

    if wallet.startswith("0:"):
        return len(wallet) >= 60

    return False


# =========================================================
# استقبال المحفظة
# =========================================================

async def receive_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if context.user_data.get("withdraw_step") != "wallet":
        return

    wallet = update.message.text.strip()

    if not looks_like_ton_wallet(wallet):

        await update.message.reply_text(
            """
❌ عنوان TON يبدو غير صحيح.

أرسل عنوان TON صحيحاً.

مثال:
EQ...

أو:
UQ...

/cancel للإلغاء
"""
        )

        return

    db_user = get_user(user.id)

    if not db_user:
        return

    # -----------------------------------------------------
    # إعادة التحقق من حد السحب
    # -----------------------------------------------------

    today_count = get_today_withdrawal_count(user.id)

    if today_count >= MAX_WITHDRAWALS_PER_DAY:

        context.user_data.clear()

        await update.message.reply_text(
            """
⛔ وصلت إلى الحد الأقصى للسحب اليوم.

🕐 حاول غداً.
""",
            reply_markup=main_keyboard()
        )

        return

    points = int(db_user["points"])

    if points < MIN_WITHDRAW_POINTS:

        context.user_data.clear()

        await update.message.reply_text(
            "❌ رصيدك أقل من الحد الأدنى للسحب.",
            reply_markup=main_keyboard()
        )

        return

    conn = get_db()

    # منع طلب آخر قيد المعالجة
    pending = conn.execute("""
        SELECT id
        FROM withdrawals
        WHERE user_id = ?
        AND status IN ('pending', 'processing')
        LIMIT 1
    """, (
        user.id,
    )).fetchone()

    if pending:

        conn.close()
        context.user_data.clear()

        await update.message.reply_text(
            """
⏳ لديك طلب سحب قيد المراجعة بالفعل.
""",
            reply_markup=main_keyboard()
        )

        return

    ton = points / POINTS_PER_TON

    # -----------------------------------------------------
    # إنشاء طلب السحب
    # -----------------------------------------------------

    cursor = conn.execute("""
        INSERT INTO withdrawals
        (
            user_id,
            points,
            ton,
            wallet,
            status,
            tx_hash,
            created_at,
            processed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user.id,
        points,
        ton,
        wallet,
        "pending",
        None,
        datetime.now().isoformat(),
        None
    ))

    withdrawal_id = cursor.lastrowid

    # خصم النقاط وحجزها
    conn.execute("""
        UPDATE users
        SET points = points - ?
        WHERE user_id = ?
    """, (
        points,
        user.id
    ))

    conn.commit()
    conn.close()

    context.user_data.clear()

    await update.message.reply_text(
        f"""
✅ تم تسجيل طلب السحب.

🆔 رقم الطلب:
#{withdrawal_id}

💎 المبلغ:
{ton:.4f} TON

⭐ النقاط:
{points:,}

👛 المحفظة:
{wallet}

⏳ الحالة:
قيد المراجعة

🔄 السحوبات اليوم:
{today_count + 1}/{MAX_WITHDRAWALS_PER_DAY}
""",
        reply_markup=main_keyboard()
    )

    # -----------------------------------------------------
    # إشعار الأدمن
    # -----------------------------------------------------

    if ADMIN_ID:

        try:

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ قبول السحب",
                        callback_data=f"approve_{withdrawal_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ رفض السحب",
                        callback_data=f"reject_{withdrawal_id}"
                    )
                ]
            ])

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"""
🚨 طلب سحب TON جديد

🆔 الطلب:
#{withdrawal_id}

👤 المستخدم:
{user.first_name}

🆔 User ID:
{user.id}

⭐ النقاط:
{points:,}

💎 المبلغ:
{ton:.4f} TON

👛 محفظة TON:
{wallet}

🔄 سحوبات اليوم:
{today_count + 1}/{MAX_WITHDRAWALS_PER_DAY}

⏳ الحالة:
PENDING
""",
                reply_markup=keyboard
            )

        except Exception as e:

            logger.error(
                f"Admin notification error: {e}"
            )


# =========================================================
# قبول السحب
# =========================================================

async def approve_withdrawal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "❌ غير مصرح لك.",
            show_alert=True
        )

        return

    await query.answer()

    try:
        withdrawal_id = int(
            query.data.split("_")[1]
        )
    except:
        return

    conn = get_db()

    withdrawal = conn.execute("""
        SELECT *
        FROM withdrawals
        WHERE id = ?
    """, (
        withdrawal_id,
    )).fetchone()

    if not withdrawal:

        conn.close()

        await query.message.reply_text(
            "❌ الطلب غير موجود."
        )

        return

    if withdrawal["status"] != "pending":

        conn.close()

        await query.message.reply_text(
            f"""
⚠️ تمت معالجة هذا الطلب مسبقاً.

الحالة:
{withdrawal["status"]}
"""
        )

        return

    conn.execute("""
        UPDATE withdrawals
        SET status = 'processing'
        WHERE id = ?
        AND status = 'pending'
    """, (
        withdrawal_id,
    ))

    conn.commit()
    conn.close()

    await query.message.edit_reply_markup(
        reply_markup=None
    )

    context.user_data["admin_action"] = "tx_hash"
    context.user_data["withdrawal_id"] = withdrawal_id

    await query.message.reply_text(
        f"""
✅ تم قبول طلب السحب #{withdrawal_id}

💎 المبلغ:
{withdrawal["ton"]:.4f} TON

👛 المحفظة:
{withdrawal["wallet"]}

📌 قم الآن بتحويل المبلغ من محفظة الدفع.

بعد نجاح التحويل:
أرسل Transaction Hash هنا.

⚠️ لا ترسل Seed Phrase أو Private Key.
"""
    )


# =========================================================
# رفض السحب
# =========================================================

async def reject_withdrawal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.from_user.id != ADMIN_ID:

        await query.answer(
            "❌ غير مصرح لك.",
            show_alert=True
        )

        return

    await query.answer()

    try:
        withdrawal_id = int(
            query.data.split("_")[1]
        )
    except:
        return

    conn = get_db()

    withdrawal = conn.execute("""
        SELECT *
        FROM withdrawals
        WHERE id = ?
    """, (
        withdrawal_id,
    )).fetchone()

    if not withdrawal:

        conn.close()

        await query.message.reply_text(
            "❌ الطلب غير موجود."
        )

        return

    if withdrawal["status"] != "pending":

        conn.close()

        await query.message.reply_text(
            "⚠️ تمت معالجة الطلب مسبقاً."
        )

        return

    # إعادة النقاط
    conn.execute("""
        UPDATE users
        SET points = points + ?
        WHERE user_id = ?
    """, (
        withdrawal["points"],
        withdrawal["user_id"]
    ))

    conn.execute("""
        UPDATE withdrawals
        SET status = 'rejected',
            processed_at = ?
        WHERE id = ?
        AND status = 'pending'
    """, (
        datetime.now().isoformat(),
        withdrawal_id
    ))

    conn.commit()
    conn.close()

    await query.message.edit_reply_markup(
        reply_markup=None
    )

    await query.message.reply_text(
        f"""
❌ تم رفض طلب السحب #{withdrawal_id}

⭐ تمت إعادة:
{withdrawal["points"]:,} نقطة

👤 User ID:
{withdrawal["user_id"]}
"""
    )

    try:

        await context.bot.send_message(
            chat_id=withdrawal["user_id"],
            text=f"""
❌ تم رفض طلب السحب #{withdrawal_id}.

⭐ تمت إعادة:
{withdrawal["points"]:,} نقطة

💰 يمكنك استخدام رصيدك مرة أخرى.
""",
            reply_markup=main_keyboard()
        )

    except Exception as e:

        logger.error(
            f"User rejection notification error: {e}"
        )


# =========================================================
# Transaction Hash
# =========================================================

async def receive_tx_hash(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    if context.user_data.get("admin_action") != "tx_hash":
        return

    tx_hash = update.message.text.strip()

    withdrawal_id = context.user_data.get(
        "withdrawal_id"
    )

    if not withdrawal_id:

        context.user_data.clear()
        return

    if len(tx_hash) < 10:

        await update.message.reply_text(
            "❌ Transaction Hash غير صحيح."
        )

        return

    conn = get_db()

    withdrawal = conn.execute("""
        SELECT *
        FROM withdrawals
        WHERE id = ?
    """, (
        withdrawal_id,
    )).fetchone()

    if not withdrawal:

        conn.close()
        context.user_data.clear()

        await update.message.reply_text(
            "❌ الطلب غير موجود."
        )

        return

    if withdrawal["status"] != "processing":

        conn.close()
        context.user_data.clear()

        await update.message.reply_text(
            "⚠️ الطلب ليس في حالة التحويل."
        )

        return

    conn.execute("""
        UPDATE withdrawals
        SET status = 'paid',
            tx_hash = ?,
            processed_at = ?
        WHERE id = ?
        AND status = 'processing'
    """, (
        tx_hash,
        datetime.now().isoformat(),
        withdrawal_id
    ))

    conn.commit()
    conn.close()

    context.user_data.clear()

    await update.message.reply_text(
        f"""
✅ تم تسجيل التحويل.

🆔 الطلب:
#{withdrawal_id}

💎 المبلغ:
{withdrawal["ton"]:.4f} TON

👛 المحفظة:
{withdrawal["wallet"]}

🔗 Transaction Hash:
{tx_hash}

✅ الحالة:
PAID
"""
    )

    try:

        await context.bot.send_message(
            chat_id=withdrawal["user_id"],
            text=f"""
🎉 تم تنفيذ طلب السحب!

🆔 الطلب:
#{withdrawal_id}

💎 المبلغ:
{withdrawal["ton"]:.4f} TON

✅ الحالة:
تم التحويل

🔗 Transaction Hash:
{tx_hash}
""",
            reply_markup=main_keyboard()
        )

    except Exception as e:

        logger.error(
            f"Payment notification error: {e}"
        )


# =========================================================
# /withdrawals
# =========================================================

async def withdrawals_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ غير مصرح لك."
        )

        return

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM withdrawals
        WHERE status IN ('pending', 'processing')
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()

    conn.close()

    if not rows:

        await update.message.reply_text(
            "📭 لا توجد طلبات سحب معلقة."
        )

        return

    for row in rows:

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ قبول",
                    callback_data=f"approve_{row['id']}"
                ),
                InlineKeyboardButton(
                    "❌ رفض",
                    callback_data=f"reject_{row['id']}"
                )
            ]
        ])

        await update.message.reply_text(
            f"""
💎 طلب سحب

🆔 #{row["id"]}

👤 User ID:
{row["user_id"]}

⭐ النقاط:
{row["points"]:,}

💎 TON:
{row["ton"]:.4f}

👛 المحفظة:
{row["wallet"]}

⏳ الحالة:
{row["status"]}
""",
            reply_markup=keyboard
        )


# =========================================================
# لوحة الإدارة
# =========================================================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

    processing = conn.execute("""
        SELECT COUNT(*) AS count
        FROM withdrawals
        WHERE status = 'processing'
    """).fetchone()["count"]

    paid = conn.execute("""
        SELECT COUNT(*) AS count
        FROM withdrawals
        WHERE status = 'paid'
    """).fetchone()["count"]

    rejected = conn.execute("""
        SELECT COUNT(*) AS count
        FROM withdrawals
        WHERE status = 'rejected'
    """).fetchone()["count"]

    conn.close()

    await update.message.reply_text(
        f"""
👑 لوحة الإدارة

👥 المستخدمون:
{users}

⏳ قيد المراجعة:
{pending}

💸 قيد التحويل:
{processing}

✅ المدفوعة:
{paid}

❌ المرفوضة:
{rejected}

💎 التحويل:
1000 نقطة = 1 TON

🔄 السحب:
{MAX_WITHDRAWALS_PER_DAY} مرات يومياً

📌 عرض الطلبات:
/withdrawals
"""
    )


# =========================================================
# إضافة نقاط
# =========================================================

async def addpoints(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ غير مصرح لك."
        )

        return

    if len(context.args) != 2:

        await update.message.reply_text(
            "الاستخدام:\n/addpoints USER_ID POINTS"
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

⭐ النقاط:
+{points:,}

💎 القيمة:
{points / POINTS_PER_TON:.4f} TON
"""
    )


# =========================================================
# إلغاء
# =========================================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()

    await update.message.reply_text(
        "❌ تم إلغاء العملية.",
        reply_markup=main_keyboard()
    )


# =========================================================
# تشغيل البوت
# =========================================================

def main():

    if not TOKEN:

        raise ValueError(
            "BOT_TOKEN غير موجود في Environment Variables"
        )

    if not ADMIN_ID:

        raise ValueError(
            "ADMIN_ID غير موجود أو يساوي 0"
        )

    init_db()

    application = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # =====================================================
    # الأوامر
    # =====================================================

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("admin", admin)
    )

    application.add_handler(
        CommandHandler("withdrawals", withdrawals_command)
    )

    application.add_handler(
        CommandHandler("addpoints", addpoints)
    )

    application.add_handler(
        CommandHandler("cancel", cancel)
    )

    # =====================================================
    # أزرار المستخدم
    # =====================================================

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

    # =====================================================
    # أزرار الأدمن
    # =====================================================

    application.add_handler(
        CallbackQueryHandler(
            approve_withdrawal,
            pattern=r"^approve_\d+$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            reject_withdrawal,
            pattern=r"^reject_\d+$"
        )
    )

    # =====================================================
    # استقبال النصوص
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_tx_hash
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_wallet
        )
    )

    print(
        "Faris Earn TON Bot is running..."
    )

    application.run_polling()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
