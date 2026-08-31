import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    if update.effective_user.id == ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("👑 لوحة الأدمن", callback_data="admin")
        ])

    await update.message.reply_text(
        "🤖 أهلاً بك في FarisEarnBot\n\n"
        "💎 اكسب النقاط من المهام ودعوة الأصدقاء.\n"
        "اختر من القائمة:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "balance":
        text = "💰 رصيدك الحالي: 0 نقطة"

    elif query.data == "tasks":
        text = "🎯 المهام\n\nلا توجد مهام حاليًا."

    elif query.data == "referral":
        user_id = query.from_user.id
        text = (
            "👥 نظام الإحالة\n\n"
            f"🔗 رابط دعوتك:\n"
            f"https://t.me/YourBotUsername?start={user_id}\n\n"
            "🎁 ادعُ أصدقاءك لتحصل على المكافآت."
        )

    elif query.data == "withdraw":
        text = (
            "💳 السحب\n\n"
            "رصيدك غير كافٍ للسحب حاليًا."
        )

    elif query.data == "stats":
        text = "📊 الإحصائيات\n\n👥 المستخدمون: 0\n💰 الأرباح الموزعة: 0"

    elif query.data == "admin":
        if query.from_user.id != ADMIN_ID:
            text = "⛔ غير مصرح لك."
        else:
            text = (
                "👑 لوحة تحكم الأدمن\n\n"
                "سيتم إضافة إدارة المستخدمين والمهام والسحب هنا."
            )

    else:
        text = "❌ أمر غير معروف."

    await query.edit_message_text(text)


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN غير موجود")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))

    print("FarisEarnBot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
