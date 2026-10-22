#!/bin/sh
# APP_MODE=web 启动 Web UI；默认启动 Telegram Bot
if [ "$APP_MODE" = "web" ]; then
    # 单 worker：会话、审批等状态保存在进程内存里
    exec gunicorn web_ui:app \
        --bind "0.0.0.0:${PORT:-5001}" \
        --workers 1 --threads 8 --timeout 300
fi
exec python telegram_bot.py
