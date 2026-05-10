"""Shared helpers used across all tools."""
import re
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from config import vault_path

VAULT = vault_path()


def today() -> str:
    return date.today().strftime("%Y-%m-%d")


def slug(text: str) -> str:
    """Convert text to a safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s]+", "-", text).strip("-")


def safe_write(path: Path, content: str) -> Path:
    """Write content to path; versions filename if it already exists."""
    if path.exists():
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        i = 1
        while path.exists():
            path = parent / f"{stem}-{i}{suffix}"
            i += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def append_to(path: Path, content: str) -> None:
    """Append content to an existing note."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + content)


def log_brain(message: str) -> None:
    log_path = VAULT / "Meta" / "brain-log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n- {ts} — {message}")


def find_note_by_gcal_id(gcal_id: str) -> Optional[Path]:
    calendar_dir = VAULT / "Meta" / "Calendar"
    if not calendar_dir.exists():
        return None
    for md in calendar_dir.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        if f"gcal-event-id: {gcal_id}" in text:
            return md
    return None


def search_vault(query: str) -> list[tuple[Path, str]]:
    results = []
    for md in VAULT.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        if query.lower() in text.lower():
            # find first matching line for context
            for line in text.splitlines():
                if query.lower() in line.lower():
                    results.append((md, line.strip()))
                    break
    return results


def parse_frontmatter(text: str) -> dict:
    fm = {}
    if not text.startswith("---"):
        return fm
    end = text.find("---", 3)
    if end == -1:
        return fm
    block = text[3:end].strip()
    for line in block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    return fm


def update_frontmatter_field(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return
    end = text.find("---", 3)
    if end == -1:
        return
    block = text[3:end]
    if re.search(rf"^{key}:", block, re.MULTILINE):
        block = re.sub(rf"^{key}:.*", f"{key}: {value}", block, flags=re.MULTILINE)
    else:
        block = block.rstrip() + f"\n{key}: {value}\n"
    new_text = "---" + block + "---" + text[end + 3:]
    path.write_text(new_text, encoding="utf-8")
