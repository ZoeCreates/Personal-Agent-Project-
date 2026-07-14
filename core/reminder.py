import json
import os
from pathlib import Path
from datetime import datetime, timedelta

REMINDERS_FILE = Path.home() / ".my-agent" / "reminders.jsonl"
# Reminder past due more than this many hours is discarded (not delivered).
MAX_OVERDUE_HOURS = int(os.getenv("REMINDER_MAX_OVERDUE_HOURS", "2"))
TIME_FMT = "%Y-%m-%d %H:%M"


def save_reminder(user_id: str, message: str, remind_time: str) -> str:
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {"user_id": user_id, "message": message, "time": remind_time, "sent": False}
    with open(REMINDERS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return remind_time


def _parse_remind_time(remind_time: str) -> datetime | None:
    try:
        return datetime.strptime(remind_time, TIME_FMT)
    except (TypeError, ValueError):
        return None


def _is_stale(remind_time: str, now: datetime | None = None) -> bool:
    """True if remind_time is more than MAX_OVERDUE_HOURS in the past."""
    due_at = _parse_remind_time(remind_time)
    if due_at is None:
        return True
    now = now or datetime.now()
    return due_at < now - timedelta(hours=MAX_OVERDUE_HOURS)


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


def discard_stale_reminders(now: datetime | None = None) -> int:
    """Mark unsent, overdue-beyond-limit reminders as sent. Returns how many discarded."""
    now = now or datetime.now()
    discarded = 0
    for r in get_pending_reminders():
        if _is_stale(r.get("time", ""), now):
            mark_sent(r["user_id"], r["message"], r["time"])
            discarded += 1
            print(
                f"  [Reminder] Discarded stale (> {MAX_OVERDUE_HOURS}h): "
                f"{r['user_id']} @ {r['time']}: {r['message']}"
            )
    return discarded


def get_due_reminders(user_id: str | None = None, now: datetime | None = None) -> list:
    """Return due reminders that are still within the overdue window.

    Stale reminders (past due more than MAX_OVERDUE_HOURS) are discarded first.
    """
    now = now or datetime.now()
    discard_stale_reminders(now)
    now_str = now.strftime(TIME_FMT)
    due = []
    for r in get_pending_reminders():
        if user_id is not None and r.get("user_id") != user_id:
            continue
        if r.get("time", "") <= now_str and not _is_stale(r.get("time", ""), now):
            due.append(r)
    return due


def mark_sent(user_id: str, message: str, remind_time: str):
    if not REMINDERS_FILE.exists():
        return
    lines = REMINDERS_FILE.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        try:
            r = json.loads(line)
            if (
                r["user_id"] == user_id
                and r["message"] == message
                and r["time"] == remind_time
            ):
                r["sent"] = True
            new_lines.append(json.dumps(r, ensure_ascii=False))
        except json.JSONDecodeError:
            new_lines.append(line)
    REMINDERS_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
