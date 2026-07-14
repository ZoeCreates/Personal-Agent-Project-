"""Skills loader — discover SKILL.md files and expose summaries / full bodies."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

SKILLS_HOME = Path.home() / ".my-agent" / "skills"
# Built-in examples shipped with the repo (overridden by user skills of same name)
BUILTIN_SKILLS = Path(__file__).resolve().parent.parent / "skills"

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path
    disabled: bool = False


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text.strip())
    if not match:
        return {}, text.strip()

    meta: dict = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip("'\"")

    return meta, match.group(2).strip()


def _parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _load_skill_file(path: Path) -> Skill | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None

    meta, body = _parse_frontmatter(raw)
    name = (meta.get("name") or path.parent.name).strip()
    if not name:
        return None

    description = (meta.get("description") or "").strip() or f"Skill: {name}"
    return Skill(
        name=name,
        description=description,
        body=body or raw.strip(),
        path=path,
        disabled=_parse_bool(meta.get("disabled"), False),
    )


def _scan_dir(root: Path) -> dict[str, Skill]:
    found: dict[str, Skill] = {}
    if not root.exists():
        return found

    for skill_md in sorted(root.glob("*/SKILL.md")):
        skill = _load_skill_file(skill_md)
        if skill is None:
            continue
        found[skill.name] = skill
    return found


class SkillsLoader:
    """Load skills from repo builtins + ~/.my-agent/skills (user wins on name clash)."""

    def __init__(
        self,
        user_dir: Path | None = None,
        builtin_dir: Path | None = None,
    ):
        self.user_dir = user_dir or SKILLS_HOME
        self.builtin_dir = builtin_dir or BUILTIN_SKILLS
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        skills = _scan_dir(self.builtin_dir)
        skills.update(_scan_dir(self.user_dir))  # user overrides builtin

        disabled_env = {
            s.strip()
            for s in (os.getenv("DISABLED_SKILLS") or "").split(",")
            if s.strip()
        }
        self._skills = {
            name: skill
            for name, skill in skills.items()
            if not skill.disabled and name not in disabled_env
        }

    def list_skills(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def get_summary_text(self) -> str:
        skills = self.list_skills()
        if not skills:
            return ""
        lines = ["## Available skills"]
        for skill in skills:
            lines.append(f"- {skill.name}: {skill.description}")
        lines.append(
            "If a user task matches a skill, call load_skill with that skill name "
            "and follow the returned instructions. Do not load skills for greetings "
            "or unrelated small talk."
        )
        return "\n".join(lines)

    def load_body(self, name: str) -> str:
        skill = self.get(name)
        if skill is None:
            available = ", ".join(s.name for s in self.list_skills()) or "(none)"
            return f"Unknown skill '{name}'. Available skills: {available}"
        header = f"# Skill: {skill.name}\n{skill.description}\n\n"
        return header + skill.body


# Module-level singleton used by tools / agent
_loader: SkillsLoader | None = None


def get_skills_loader() -> SkillsLoader:
    global _loader
    if _loader is None:
        _loader = SkillsLoader()
    return _loader
