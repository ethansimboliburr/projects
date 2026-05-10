"""Reads My Vault Config.md and exposes all fields as a dict."""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

VAULT_PATH = Path(os.getenv("VAULT_PATH", r"C:\Users\ethan\OneDrive\Desktop\AIBrain\SecondBrain"))


def get_config() -> dict:
    config_path = VAULT_PATH / "Meta" / "My Vault Config.md"
    defaults = {
        "vault_path": str(VAULT_PATH),
        "daily_notes_enabled": False,
        "name": "Ethan",
        "skills": [],
        "writing_style": "direct, no fluff, student voice",
        "target_roles": [],
        "target_companies": [],
        "gpa": "",
        "school": "Drexel University",
        "program": "",
    }
    if not config_path.exists():
        return defaults
    text = config_path.read_text(encoding="utf-8")
    # Parse simple key: value lines and YAML-style lists
    for line in text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower().replace(" ", "_").replace("-", "_")
        val = val.strip()
        if val.lower() == "true":
            defaults[key] = True
        elif val.lower() == "false":
            defaults[key] = False
        elif val.startswith("[") and val.endswith("]"):
            items = [i.strip().strip('"\'' ) for i in val[1:-1].split(",") if i.strip()]
            defaults[key] = items
        elif val:
            defaults[key] = val
    return defaults


def vault_path() -> Path:
    return VAULT_PATH
