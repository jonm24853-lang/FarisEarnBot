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
    MessageHandler,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_FILE = "faris_earn.db"

REFERRAL_BONUS = 100
DAILY_BONUS = 50
MIN_WITHDRAW = 1000

# القناة المطلوبة للاشتراك
CHANNEL_USERNAME = "@farehes"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


# ==================================================
# قاعدة البيانات
# ==================================================

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            reward INTEGER NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS completed_tasks (
            user_id INTEGER,
            task_id INTEGER,
            completed_at TEXT,
            PRIMARY KEY (user_id, task_id)
        )
    """)

    db.commit()
    db.close()


# ==================================================
# المستخدم
# ==================================================

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
            (
                user_id,
                username,
                first_name,
            )
        )

    else:

        cursor.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?
            WHERE user_id = ?
            """,
            (
                username,
                first_name,
                user_id,
            )
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


# ==================================================
# /start
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT user_id, referred_by
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    )

    existing = cursor.fetchone()

    referral_added = False

    # مستخدم جديد
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
            SET username = ?,
                first_name = ?
            WHERE user_id = ?
            """,
            (
                user.username or "",
                user.first_name or "",
                user_id,
            )
        )

    # ==================================================
    # الإحالة
    # ==================================================

    if context.args:

        try:

            referrer_id = int(context.args[0])

            if (
                referrer_id != user_id
                and existing_referred_by is None
            ):

                cursor.execute(
                    """
                    SELECT user_id
                    FROM users
                    WHERE user_id = ?
                    """,
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
                        (
                            referrer_id,
                            user_id,
                        )
                    )

                    cursor.execute(
                        """
                        UPDATE users
                        SET balance = balance + ?,
                            referrals = referrals + 1
                        WHERE user_id = ?
                        """,
                        (
                            REFERRAL_BONUS,
                            referrer_id,
                        )
                    )

                    referral_added = True

        except ValueError:
            pass

    db.commit()
    db.close()

    # ==================================================
    # القائمة
    # ==================================================

    keyboard = [

        [
            InlineKeyboardButton(
                "💰 رصيدي",
                callback_data="balance"
            ),
            InlineKeyboardButton(
                "🎯 المهام",
                callback_data="tasks"
            ),
        ],

        [
            InlineKeyboardButton(
                "🎁 المكافأة اليومية",
                callback_data="daily"
            ),
        ],

        [
            InlineKeyboardButton(
                "👥 دعوة الأصدقاء",
                callback_data="referral"
            ),
            InlineKeyboardButton(
                "💳 السحب",
                callback_data="withdraw"
            ),
        ],

        [
            InlineKeyboardButton(
                "📊 الإحصائيات",
                callback_data="stats"
            ),
        ],
    ]

    # لوحة الأدمن
    if user_id == ADMIN_ID:

        keyboard.append(
            [
                InlineKeyboardButton(
                    "👑 لوحة الأدمن",
                    callback_data="admin"
                )
            ]
        )

    message = (
        "🤖 أهلاً بك في FarisEarnBot 💎\n\n"
        "💎 اكسب النقاط من المهام ودعوة الأصدقاء.\n\n"
        "اختر من القائمة:"
    )

    if referral_added:

        message += (
            "\n\n🎉 تم تسجيل الإحالة بنجاح!"
        )

    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==================================================
# عرض المهام
# ==================================================

async def show_tasks(query, user_id):

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT id, title, link, reward
        FROM tasks
        WHERE active = 1
        ORDER BY id DESC
        """
    )

    tasks = cursor.fetchall()

    if not tasks:

        db.close()

        await query.edit_message_text(
            "🎯 المهام\n\n"
            "❌ لا توجد مهام متاحة حاليًا."
        )

        return

    keyboard = []

    for task_id, title, link, reward in tasks:

        cursor.execute(
            """
            SELECT 1
            FROM completed_tasks
            WHERE user_id = ?
            AND task_id = ?
            """,
            (
                user_id,
                task_id
            )
        )

        completed = cursor.fetchone()

        if completed:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"✅ {title}",
                        callback_data="already_done"
                    )
                ]
            )

        else:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🎯 {title} (+{reward})",
                        callback_data=f"task_{task_id}"
                    )
                ]
            )

    db.close()

    await query.edit_message_text(
        "🎯 المهام المتاحة\n\n"
        "اختر مهمة للحصول على التفاصيل:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==================================================
# لوحة الأدمن
# ==================================================

async def admin_panel(query):

    keyboard = [

        [
            InlineKeyboardButton(
                "➕ إضافة مهمة",
                callback_data="add_task"
            )
        ],

        [
            InlineKeyboardButton(
                "📋 إدارة المهام",
                callback_data="manage_tasks"
            )
        ],

    ]

    await query.edit_message_text(
        "👑 لوحة الأدمن\n\n"
        "اختر العملية المطلوبة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==================================================
# الأزرار
# ==================================================

async def buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    ensure_user(
        user_id,
        query.from_user.username or "",
        query.from_user.first_name or ""
    )

    # ==================================================
    # الرصيد
    # ==================================================

    if query.data == "balance":

        user_data = get_user(user_id)

        balance = (
            user_data[0]
            if user_data
            else 0
        )

        await query.edit_message_text(
            "💰 رصيدك\n\n"
            f"💎 الرصيد الحالي: {balance} نقطة"
        )

    # ==================================================
    # المهام
    # ==================================================

    elif query.data == "tasks":

        await show_tasks(
            query,
            user_id
        )

    # ==================================================
    # المهمة مكتملة
    # ==================================================

    elif query.data == "already_done":

        await query.answer(
            "✅ حصلت على مكافأة هذه المهمة مسبقًا.",
            show_alert=True
        )

    # ==================================================
    # تفاصيل المهمة
    # ==================================================

    elif query.data.startswith("task_"):

        task_id = int(
            query.data.split("_")[1]
        )

        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """
            SELECT title, link, reward
            FROM tasks
            WHERE id = ?
            AND active = 1
            """,
            (task_id,)
        )

        task = cursor.fetchone()

        db.close()

        if not task:

            await query.edit_message_text(
                "❌ هذه المهمة غير متاحة."
            )

            return

        title, link, reward = task

        keyboard = [

            [
                InlineKeyboardButton(
                    "🔗 فتح المهمة",
                    url=link
                )
            ],

            [
                InlineKeyboardButton(
                    "✅ تحقق واستلام النقاط",
                    callback_data=f"claim_{task_id}"
                )
            ],

        ]

        await query.edit_message_text(
            f"🎯 {title}\n\n"
            f"💎 المكافأة: {reward} نقطة\n\n"
            "1️⃣ اشترك في القناة.\n"
            "2️⃣ اضغط «تحقق واستلام النقاط».\n\n"
            "⚠️ لن تُضاف النقاط إلا بعد التحقق من الاشتراك.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ==================================================
    # استلام النقاط + التحقق من الاشتراك
    # ==================================================

    elif query.data.startswith("claim_"):

        task_id = int(
            query.data.split("_")[1]
        )

        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """
            SELECT title, reward, link
            FROM tasks
            WHERE id = ?
            AND active = 1
            """,
            (task_id,)
        )

        task = cursor.fetchone()

        if not task:

            db.close()

            await query.edit_message_text(
                "❌ هذه المهمة غير متاحة."
            )

            return

        title, reward, link = task

        # ==================================================
        # التحقق من الاشتراك
        # ==================================================

        try:

            member = await context.bot.get_chat_member(
                chat_id=CHANNEL_USERNAME,
                user_id=user_id
            )

            if member.status in (
                "left",
                "kicked"
            ):

                db.close()

                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔗 الاشتراك في القناة",
                            url=link
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🔄 تحقق مرة أخرى",
                            callback_data=f"claim_{task_id}"
                        )
                    ],
                ]

                await query.edit_message_text(
                    "❌ لم يتم العثور على اشتراكك في القناة.\n\n"
                    "اشترك أولًا ثم اضغط «تحقق مرة أخرى».",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

                return

        except Exception as e:

            db.close()

            logging.error(
                f"Subscription check error: {e}"
            )

            await query.edit_message_text(
                "⚠️ تعذر التحقق من الاشتراك حاليًا.\n\n"
                "تأكد أن البوت مشرف في القناة ثم حاول مرة أخرى."
            )

            return

        # ==================================================
        # منع تكرار المكافأة
        # ==================================================

        cursor.execute(
            """
            SELECT 1
            FROM completed_tasks
            WHERE user_id = ?
            AND task_id = ?
            """,
            (
                user_id,
                task_id
            )
        )

        if cursor.fetchone():

            db.close()

            await query.edit_message_text(
                "❌ حصلت على مكافأة هذه المهمة مسبقًا."
            )

            return

        # ==================================================
        # تسجيل المهمة كمكتملة
        # ==================================================

        cursor.execute(
            """
            INSERT INTO completed_tasks
            (user_id, task_id, completed_at)
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                task_id,
                datetime.utcnow().isoformat()
            )
        )

        # ==================================================
        # إضافة النقاط
        # ==================================================

        cursor.execute(
            """
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ?
            """,
            (
                reward,
                user_id
            )
        )

        db.commit()
        db.close()

        await query.edit_message_text(
            "🎉 تم التحقق بنجاح!\n\n"
            f"🎯 المهمة: {title}\n"
            f"💎 المكافأة: {reward} نقطة\n\n"
            "✅ اشتراكك مؤكد.\n"
            "💰 تمت إضافة النقاط إلى رصيدك."
        )

    # ==================================================
    # المكافأة اليومية
    # ==================================================

    elif query.data == "daily":

        user_data = get_user(user_id)

        last_daily = (
            user_data[3]
            if user_data
            else None
        )

        now = datetime.utcnow()

        if last_daily:

            try:

                last_time = datetime.fromisoformat(
                    last_daily
                )

                next_time = (
                    last_time +
                    timedelta(hours=24)
                )

                if now < next_time:

                    remaining = (
                        next_time - now
                    )

                    hours = int(
                        remaining.total_seconds()
                        // 3600
                    )

                    minutes = int(
                        (
                            remaining.total_seconds()
                            % 3600
                        ) // 60
                    )

                    await query.edit_message_text(
                        "🎁 المكافأة اليومية\n\n"
                        "❌ لقد حصلت على مكافأتك اليوم.\n\n"
                        f"⏳ المكافأة القادمة بعد: "
                        f"{hours} ساعة و {minutes} دقيقة."
                    )

                    return

            except ValueError:
                pass

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
                user_id
            )
        )

        db.commit()
        db.close()

        await query.edit_message_text(
            "🎉 مبروك!\n\n"
            f"🎁 حصلت على {DAILY_BONUS} نقطة.\n"
            "💎 تمت إضافة النقاط إلى رصيدك."
        )

    # ==================================================
    # الإحالة
    # ==================================================

    elif query.data == "referral":

        bot = await context.bot.get_me()

        await query.edit_message_text(
            "👥 دعوة الأصدقاء\n\n"
            "🔗 رابط دعوتك الخاص:\n\n"
            f"https://t.me/{bot.username}?start={user_id}\n\n"
            f"🎁 تحصل على {REFERRAL_BONUS} نقطة "
            "عن كل إحالة ناجحة."
        )

    # ==================================================
    # السحب
    # ==================================================

    elif query.data == "withdraw":

        user_data = get_user(user_id)

        balance = (
            user_data[0]
            if user_data
            else 0
        )

        await query.edit_message_text(
            "💳 السحب\n\n"
            f"💎 رصيدك: {balance} نقطة\n"
            f"📌 الحد الأدنى: {MIN_WITHDRAW} نقطة\n\n"
            "سيتم تجهيز نظام السحب قريبًا."
        )

    # ==================================================
    # الإحصائيات
    # ==================================================

    elif query.data == "stats":

        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM users"
        )

        users_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT SUM(balance) FROM users"
        )

        total_balance = (
            cursor.fetchone()[0]
            or 0
        )

        db.close()

        user_data = get_user(user_id)

        balance = (
            user_data[0]
            if user_data
            else 0
        )

        referrals = (
            user_data[1]
            if user_data
            else 0
        )

        await query.edit_message_text(
            "📊 إحصائياتك\n\n"
            f"💎 رصيدك: {balance} نقطة\n"
            f"👥 إحالاتك: {referrals}\n\n"
            f"👤 إجمالي المستخدمين: {users_count}\n"
            f"💰 إجمالي النقاط: {total_balance}"
        )

    # ==================================================
    # لوحة الأدمن
    # ==================================================

    elif query.data == "admin":

        if user_id != ADMIN_ID:

            await query.edit_message_text(
                "⛔ غير مصرح لك."
            )

            return

        await admin_panel(query)

    # ==================================================
    # إضافة مهمة
    # ==================================================

    elif query.data == "add_task":

        if user_id != ADMIN_ID:
            return

        context.user_data["admin_action"] = "task_title"

        await query.edit_message_text(
            "➕ إضافة مهمة\n\n"
            "أرسل الآن اسم المهمة.\n\n"
            "مثال:\n"
            "📢 الاشتراك في قناة Fares"
        )

    # ==================================================
    # إدارة المهام
    # ==================================================

    elif query.data == "manage_tasks":

        if user_id != ADMIN_ID:
            return

        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """
            SELECT id, title, reward, active
            FROM tasks
            ORDER BY id DESC
            """
        )

        tasks = cursor.fetchall()

        db.close()

        if not tasks:

            await query.edit_message_text(
                "📋 إدارة المهام\n\n"
                "❌ لا توجد مهام حتى الآن."
            )

            return

        text = "📋 المهام الحالية:\n\n"

        for task_id, title, reward, active in tasks:

            status = (
                "🟢"
                if active
                else "🔴"
            )

            text += (
                f"{status} #{task_id} {title}\n"
                f"💎 المكافأة: {reward} نقطة\n\n"
            )

        await query.edit_message_text(text)


# ==================================================
# استقبال بيانات المهمة
# ==================================================

async def admin_messages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        return

    action = context.user_data.get(
        "admin_action"
    )

    if not action:
        return

    message = update.message.text.strip()

    # ==================================================
    # اسم المهمة
    # ==================================================

    if action == "task_title":

        context.user_data["task_title"] = message

        context.user_data["admin_action"] = "task_link"

        await update.message.reply_text(
            "🔗 ممتاز.\n\n"
            "أرسل الآن رابط المهمة.\n\n"
            "مثال:\n"
            "https://t.me/farehes"
        )

    # ==================================================
    # رابط المهمة
    # ==================================================

    elif action == "task_link":

        if not (
            message.startswith("https://t.me/")
            or message.startswith("http://t.me/")
        ):

            await update.message.reply_text(
                "❌ أرسل رابط تيليجرام صحيح يبدأ بـ:\n"
                "https://t.me/"
            )

            return

        context.user_data["task_link"] = message

        context.user_data["admin_action"] = "task_reward"

        await update.message.reply_text(
            "💎 أرسل الآن عدد النقاط للمهمة.\n\n"
            "مثال:\n"
            "100"
        )

    # ==================================================
    # نقاط المهمة
    # ==================================================

    elif action == "task_reward":

        try:

            reward = int(message)

            if reward <= 0:
                raise ValueError

        except ValueError:

            await update.message.reply_text(
                "❌ أدخل رقمًا صحيحًا أكبر من صفر.\n\n"
                "مثال: 100"
            )

            return

        title = context.user_data["task_title"]
        link = context.user_data["task_link"]

        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """
            INSERT INTO tasks
            (title, link, reward, active)
            VALUES (?, ?, ?, 1)
            """,
            (
                title,
                link,
                reward
            )
        )

        db.commit()
        db.close()

        context.user_data.clear()

        await update.message.reply_text(
            "✅ تم إنشاء المهمة بنجاح!\n\n"
            f"🎯 المهمة: {title}\n"
            f"💎 المكافأة: {reward} نقطة\n"
            f"🔗 الرابط: {link}\n\n"
            "يمكن للمستخدمين الآن رؤية المهمة."
        )


# ==================================================
# تشغيل البوت
# ==================================================

def main():

    if not TOKEN:

        raise ValueError(
            "BOT_TOKEN غير موجود"
        )

    init_db()

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            buttons
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_messages
        )
    )

    print(
        "FarisEarnBot is running..."
    )

    app.run_polling()


if __name__ == "__main__":
    main()
