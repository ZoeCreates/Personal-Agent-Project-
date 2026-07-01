import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", str(PROJECT_ROOT / "agent_data")))

SESSIONS_DIR = DATA_DIR / "sessions"
MEMORY_FILE = DATA_DIR / "MEMORY.md"
SOUL_FILE = DATA_DIR / "SOUL.md"
REMINDERS_FILE = DATA_DIR / "reminders.jsonl"

LEGACY_DATA_DIR = Path.home() / ".my-agent"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def migrate_legacy_data() -> None:
    """Move data from ~/.my-agent to project-visible agent_data directory once."""
    if not LEGACY_DATA_DIR.exists():
        ensure_data_dirs()
        return

    ensure_data_dirs()

    legacy_sessions = LEGACY_DATA_DIR / "sessions"
    if legacy_sessions.exists() and not any(SESSIONS_DIR.iterdir()):
        for src in legacy_sessions.glob("*.jsonl"):
            dst = SESSIONS_DIR / src.name
            if not dst.exists():
                shutil.copy2(src, dst)

    for src, dst in (
        (LEGACY_DATA_DIR / "MEMORY.md", MEMORY_FILE),
        (LEGACY_DATA_DIR / "SOUL.md", SOUL_FILE),
        (LEGACY_DATA_DIR / "reminders.jsonl", REMINDERS_FILE),
    ):
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
