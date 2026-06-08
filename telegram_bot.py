import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from core.agent import Agent
from core.memory import init_db, clear_history

load_dotenv()
init_db()

# 每个用户一个独立的 Agent 实例
user_agents = {}

def get_agent(user_id: str) -> Agent:
    if user_id not in user_agents:
        user_agents[user_id] = Agent(user_id=user_id)
    return user_agents[user_id]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_input = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    agent = get_agent(user_id)
    response = agent.run(user_input)

    await update.message.reply_text(response)

async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    clear_history(user_id)
    if user_id in user_agents:
        del user_agents[user_id]
    await update.message.reply_text("✅ 对话历史已清空！")

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 你好！我是你的 AI 助手，有什么可以帮你的？\n\n发送 /clear 可以清空对话历史。")

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("clear", handle_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Telegram Bot 启动中...")
    app.run_polling()
