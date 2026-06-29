import os
import time
import threading
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)
from core.memory import init_db, clear_history
from core.reminder import get_pending_reminders, mark_sent
from core.message_bus import MessageBus
from core.channels.telegram import TelegramChannel

load_dotenv()
init_db()

# Message Bus 统一处理所有消息，不再手动管理 Agent 实例池
bus = MessageBus()
telegram_channel = TelegramChannel()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_input = update.message.text

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # 用 TelegramChannel 格式化消息，交给 MessageBus 处理
    msg = telegram_channel.format_incoming(
        {
            "user_id": user_id,
            "text": user_input,
            "chat_id": str(update.effective_chat.id),
        }
    )
    result = bus.process(msg)
    reply = result.text or "Sorry, I couldn't generate a response. Please try again."

    await update.message.reply_text(reply)


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    clear_history(user_id)
    # 同时清除 MessageBus 中的 Agent 缓存
    bus._agents.pop(user_id, None)
    await update.message.reply_text("✅ History cleared!")


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! I'm your AI assistant. How can I help you?\n\nUse /clear to reset conversation history."
    )


def start_reminder_checker(bot_app):
    """后台线程：每分钟检查一次到期的提醒"""

    def check():
        while True:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            for r in get_pending_reminders():
                if r["time"] <= now:
                    # Mark sent first to avoid duplicate delivery if send fails
                    mark_sent(r["user_id"], r["message"], r["time"])
                    try:
                        import asyncio

                        asyncio.run(
                            bot_app.bot.send_message(
                                chat_id=r["user_id"],
                                text=f"⏰ Reminder: {r['message']}",
                            )
                        )
                        print(f"  [Reminder] Sent to {r['user_id']}: {r['message']}")
                    except Exception as e:
                        print(f"  [Reminder Error] {e}")
            time.sleep(60)

    thread = threading.Thread(target=check, daemon=True)
    thread.start()


if __name__ == "__main__":
    token = os.getenv("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("clear", handle_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    start_reminder_checker(app)
    print("Telegram Bot starting...")
    app.run_polling()
