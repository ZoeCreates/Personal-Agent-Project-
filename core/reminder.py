import json
from pathlib import Path
from datetime import datetime

REMINDERS_FILE = Path.home() / ".my-agent" / "reminders.jsonl"

def save_reminder(user_id: str, message: str, remind_time: str) -> str:
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "user_id": user_id,
        "message": message,
        "time": remind_time,
        "sent": False
    }
    with open(REMINDERS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return remind_time

def get_pending_reminders() -> list:
    if not REMINDERS_FILE.exists():
        return []
    reminders = []
    for line in REMINDERS_FILE.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if not r.get("sent"):
                reminders.append(r)
        except json.JSONDecodeError:
            continue
    return reminders

def mark_sent(user_id: str, message: str, remind_time: str):
    if not REMINDERS_FILE.exists():
        return
    lines = REMINDERS_FILE.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        try:
            r = json.loads(line)
            if r["user_id"] == user_id and r["message"] == message and r["time"] == remind_time:
                r["sent"] = True
            new_lines.append(json.dumps(r, ensure_ascii=False))
        except json.JSONDecodeError:
            new_lines.append(line)
    REMINDERS_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
