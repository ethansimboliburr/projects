"""Always-running background daemon. Never crashes — wraps everything in try/except."""
import os
import re
import sys
import time
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from config import get_config, vault_path
from utils import today, safe_write, log_brain, append_to, parse_frontmatter, update_frontmatter_field
from templates import trade_note, calendar_note

VAULT = vault_path()


# ── task router ─────────────────────────────────────────────────────────

RUFLO_TASKS = {
    "check_followups", "move_inbox", "update_status", "append_daily",
    "detect_file_type", "format_frontmatter", "check_duplicates",
    "log_brain", "morning_pull", "count_notes", "send_reminders",
    "self_heal", "convert_dates", "sort_tasks",
}

CLAUDE_TASKS = {
    "generate_cover_letter", "trade_psychology", "weekly_summary",
    "steelman_idea", "study_guide", "quiz", "sowhat", "classify_screenshot",
    "score_job_fit", "story_bullets", "creative_writing",
}


def task_router(task: str) -> str:
    if task in RUFLO_TASKS:
        log_brain(f"[RUFLO] Routing: {task}")
        return "ruflo"
    if task in CLAUDE_TASKS:
        log_brain(f"[CLAUDE] Routing: {task}")
        return "claude"
    log_brain(f"[RUFLO] Unknown task, defaulting to ruflo: {task}")
    return "ruflo"


# ── trade parser ─────────────────────────────────────────────────────────

def _parse_trade_block(block: str) -> dict:
    """Extract trade fields from a Claude message block in SESSION_LOG/SUBMIT_TRADE."""
    fields = {}
    patterns = {
        "ticker": r"(?:ticker|symbol)[:\s]+([A-Z]{1,6})",
        "entry": r"entry[:\s]+([\d.]+)",
        "exit": r"exit[:\s]+([\d.]+)",
        "pnl": r"(?:pnl|p&l|profit|loss)[:\s]+([\-\d.]+)",
        "result": r"(?:result|outcome)[:\s]+(\w+)",
        "emotion_before": r"emotion.before[:\s]+([^\n]+)",
        "emotion_after": r"emotion.after[:\s]+([^\n]+)",
        "bias": r"bias[:\s]+([^\n]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, block, re.I)
        if m:
            fields[key] = m.group(1).strip()
    # Also try to detect ticker from uppercase words
    if not fields.get("ticker"):
        m = re.search(r"\b([A-Z]{2,5})\b", block)
        if m:
            fields["ticker"] = m.group(1)
    return fields


def _get_processed_blocks(log_path: Path) -> set:
    """Return set of block hashes already turned into trade notes."""
    marker_path = log_path.with_suffix(".processed")
    if marker_path.exists():
        return set(marker_path.read_text().splitlines())
    return set()


def _mark_block_processed(log_path: Path, block_hash: str) -> None:
    marker_path = log_path.with_suffix(".processed")
    with open(marker_path, "a") as f:
        f.write(block_hash + "\n")


def _process_trade_log(log_path: Path) -> None:
    if not log_path.exists():
        return
    text = log_path.read_text(encoding="utf-8")
    # Split on Claude message block separator (--- or ===)
    blocks = re.split(r"(?:^|
)(?:---+|===+)
", text)
    processed = _get_processed_blocks(log_path)

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 20:
            continue
        bh = str(hash(block))
        if bh in processed:
            continue
        fields = _parse_trade_block(block)
        if not fields.get("ticker") and not fields.get("entry"):
            continue
        content = trade_note(
            ticker=fields.get("ticker", ""),
            entry=fields.get("entry", ""),
            exit_price=fields.get("exit", ""),
            result=fields.get("result", ""),
            pnl=fields.get("pnl", ""),
            emotion_before=fields.get("emotion_before", ""),
            emotion_after=fields.get("emotion_after", ""),
            bias_detected=fields.get("bias", ""),
        )
        content += f"\n## Source\n> From: {log_path.name}\n\n{block[:500]}\n"
        ticker = fields.get("ticker", "Trade")
        folder = VAULT / "Trading Progress" / "Futures"
        filename = f"{today()} - {ticker} Trade.md"
        path = safe_write(folder / filename, content)
        _mark_block_processed(log_path, bh)
        log_brain(f"[RUFLO] Trade note auto-created from {log_path.name}: {path.stem}")


# ── self-healing ──────────────────────────────────────────────────────────

REQUIRED_FIELDS = {
    "trade": ["title", "date", "type", "ticker", "tags"],
    "application": ["title", "date-applied", "type", "company", "role", "status", "tags"],
    "contact": ["title", "date-met", "type", "follow-up-by", "tags"],
    "calendar-task": ["title", "date", "type", "due", "gcal-event-id", "status", "tags"],
    "study-package": ["title", "date", "type", "course", "exam-date", "tags"],
}


def _self_heal_note(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        note_type = fm.get("type", "")
        required = REQUIRED_FIELDS.get(note_type, ["title", "date", "type", "tags"])
        changed = False
        for field in required:
            if field not in fm:
                update_frontmatter_field(path, field, "")
                changed = True
        # Fix date format
        raw_date = fm.get("date", "")
        if raw_date and not re.match(r"\d{4}-\d{2}-\d{2}", str(raw_date)):
            try:
                fixed = datetime.strptime(str(raw_date), "%m/%d/%Y").strftime("%Y-%m-%d")
                update_frontmatter_field(path, "date", fixed)
                changed = True
            except Exception:
                pass
        if changed:
            log_brain(f"[RUFLO] Self-healed: {path.stem}")
    except Exception as e:
        log_brain(f"[ERROR] Self-heal {path.name}: {e}")


# ── dead note detector ─────────────────────────────────────────────────────

EXCLUDED_NOTES = {
    "SESSION_LOG", "SUBMIT_TRADE", "TRADING_MODEL",
    "CLAUDE", "Goals", "LIFE_STRATEGY", "OPPORTUNITY_LOG",
    "INTERVIEW_PREP", "OFFER_TRACKER",
}
EXCLUDED_DIRS = {"Skills (Claude's commands)"}


def _run_dead_note_detector() -> None:
    try:
        cutoff = datetime.now() - timedelta(days=90)
        all_notes = list(VAULT.rglob("*.md"))

        # Build wikilink index
        wikilinks: set[str] = set()
        for md in all_notes:
            try:
                text = md.read_text(encoding="utf-8")
                for link in re.findall(r"\[\[([^\]]+)\]\]", text):
                    wikilinks.add(link.split("|")[0].strip())
            except Exception:
                pass

        dead: dict[str, list] = {}
        for md in all_notes:
            if md.stem in EXCLUDED_NOTES or md.stem.endswith("TEMPLATE"):
                continue
            if any(exc in str(md) for exc in EXCLUDED_DIRS):
                continue
            try:
                fm = parse_frontmatter(md.read_text(encoding="utf-8"))
                if fm.get("type") in {"daily", "calendar-task"}:
                    continue
                mtime = datetime.fromtimestamp(md.stat().st_mtime)
                if mtime > cutoff:
                    continue
                if md.stem in wikilinks:
                    continue
                days_old = (datetime.now() - mtime).days
                section = md.relative_to(VAULT).parts[0] if md.relative_to(VAULT).parts else "Other"
                dead.setdefault(section, []).append((md.stem, days_old))
            except Exception:
                continue

        if not dead:
            log_brain("[RUFLO] Dead note scan complete — 0 candidates found")
            return

        total = sum(len(v) for v in dead.values())
        month_str = datetime.now().strftime("%Y-%m")
        lines = [f"---\ntitle: Dead Notes - {month_str}\ndate: {today()}\ntype: report\ntags: [meta]\n---\n"]
        lines.append(f"## Dead Notes — {month_str}\n")
        for section, notes in dead.items():
            lines.append(f"### {section}")
            for stem, days in notes:
                lines.append(f"- [[{stem}]] — last modified {days} days ago")
        lines.append("\n## Suggested Actions")
        for section, notes in dead.items():
            for stem, _ in notes:
                lines.append(f"- [ ] Archive or delete [[{stem}]]")

        report = "\n".join(lines) + "\n"
        path = safe_write(VAULT / "Meta" / f"Dead Notes - {month_str}.md", report)
        log_brain(f"[RUFLO] Dead note scan complete — {total} candidates found → {path.stem}")
    except Exception as e:
        log_brain(f"[ERROR] Dead note scan: {e}")


# ── vault watcher ──────────────────────────────────────────────────────────

class VaultChangeHandler:
    """Minimal vault watcher using polling for cross-platform reliability."""
    def __init__(self):
        self._last_mtimes: dict[str, float] = {}

    def check(self):
        for md in VAULT.rglob("*.md"):
            try:
                mtime = md.stat().st_mtime
                key = str(md)
                if self._last_mtimes.get(key) != mtime:
                    self._last_mtimes[key] = mtime
                    if key in self._last_mtimes:  # skip first scan
                        self._on_change(md)
            except Exception:
                pass

    def _on_change(self, path: Path) -> None:
        try:
            # Self-heal any changed note
            _self_heal_note(path)
            # Watch trading logs
            if path.stem in ("SESSION_LOG", "SUBMIT_TRADE"):
                _process_trade_log(path)
            # Application status cross-update
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
            if fm.get("type") == "application":
                status = fm.get("status", "")
                if status:
                    log_brain(f"[RUFLO] Application status observed: {path.stem} -> {status}")
        except Exception as e:
            log_brain(f"[ERROR] Vault change handler: {e}")


# ── Flask listener ───────────────────────────────────────────────────────────

def _start_flask() -> None:
    try:
        from flask import Flask, request, jsonify
        app = Flask(__name__)

        @app.route("/ingest", methods=["POST"])
        def ingest():
            data = request.get_json(force=True)
            text = data.get("text", "")
            if not text:
                return jsonify({"error": "no text"}), 400
            from inbox_watcher import _detect_text_type, _process_text
            import tempfile
            tmp = Path(tempfile.mktemp(suffix=".txt"))
            tmp.write_text(text, encoding="utf-8")
            _process_text(tmp)
            return jsonify({"ok": True})

        app.run(host="127.0.0.1", port=5002, debug=False, use_reloader=False)
    except Exception as e:
        log_brain(f"[ERROR] Flask listener: {e}")


# ── Gmail watcher ───────────────────────────────────────────────────────────

def _check_gmail_syllabus() -> None:
    try:
        from calendar_sync import _get_service
        _, creds = _get_service()
        from googleapiclient.discovery import build
        gmail = build("gmail", "v1", credentials=creds)
        results = gmail.users().messages().list(
            userId="me",
            q="subject:[SYLLABUS] OR filename:syllabus is:unread",
            maxResults=10,
        ).execute()
        messages = results.get("messages", [])
        for msg_ref in messages:
            msg = gmail.users().messages().get(userId="me", id=msg_ref["id"]).execute()
            # Check for PDF attachments
            parts = msg.get("payload", {}).get("parts", [])
            for part in parts:
                filename = part.get("filename", "")
                if filename.lower().endswith(".pdf") or "syllabus" in filename.lower():
                    att_id = part["body"].get("attachmentId")
                    if att_id:
                        att = gmail.users().messages().attachments().get(
                            userId="me", messageId=msg_ref["id"], id=att_id
                        ).execute()
                        import base64
                        data = base64.urlsafe_b64decode(att["data"])
                        dest = VAULT / "Inbox" / filename
                        dest.write_bytes(data)
                        log_brain(f"[RUFLO] Gmail syllabus downloaded: {filename}")
                        # Mark as read
                        gmail.users().messages().modify(
                            userId="me", id=msg_ref["id"],
                            body={"removeLabelIds": ["UNREAD"]}
                        ).execute()
    except Exception as e:
        log_brain(f"[ERROR] Gmail syllabus check: {e}")


# ── morning pull ───────────────────────────────────────────────────────────

def morning_pull() -> None:
    task_router("morning_pull")
    try:
        from calendar_sync import sync_calendar
        sync_calendar()
    except Exception as e:
        log_brain(f"[ERROR] Morning calendar sync: {e}")

    # Read trade logs
    for filename in ("SESSION_LOG.md", "SUBMIT_TRADE.md"):
        path = VAULT / "Trading Progress" / "Futures" / filename
        try:
            _process_trade_log(path)
        except Exception as e:
            log_brain(f"[ERROR] Trade log {filename}: {e}")

    # Optional daily note
    cfg = get_config()
    if cfg.get("daily_notes_enabled", False):
        try:
            from calendar_sync import get_today_events
            from templates import daily_note
            events = get_today_events()
            content = daily_note(today(), events)
            path = safe_write(VAULT / "Meta" / "Calendar" / f"{today()}.md", content)
            log_brain(f"[RUFLO] Daily note created: {path.stem}")
        except Exception as e:
            log_brain(f"[ERROR] Daily note: {e}")

    log_brain(f"[RUFLO] Morning pull complete")


# ── main loop ────────────────────────────────────────────────────────────

def main() -> None:
    log_brain("[RUFLO] brain.py starting")

    # Start inbox watcher
    try:
        from inbox_watcher import start_inbox_watcher
        inbox_observer = start_inbox_watcher()
    except Exception as e:
        log_brain(f"[ERROR] Inbox watcher start: {e}")
        inbox_observer = None

    # Start Flask in background thread
    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()

    # Run morning pull immediately on startup
    morning_pull()

    vault_handler = VaultChangeHandler()
    last_morning = datetime.now().date()
    last_gmail_check = datetime.now()
    last_dead_note_check = datetime.now().date().replace(day=1)

    log_brain("[RUFLO] brain.py fully running")

    while True:
        try:
            now = datetime.now()

            # Morning pull at 8am
            if now.date() > last_morning and now.hour >= 8:
                morning_pull()
                last_morning = now.date()

            # Gmail check every hour
            if (now - last_gmail_check).seconds >= 3600:
                _check_gmail_syllabus()
                last_gmail_check = now

            # Dead note scan on 1st of each month
            first_of_month = now.date().replace(day=1)
            if first_of_month > last_dead_note_check:
                _run_dead_note_detector()
                last_dead_note_check = first_of_month

            # Vault change polling every 30 seconds
            vault_handler.check()

        except Exception as e:
            log_brain(f"[ERROR] Main loop: {e}")

        time.sleep(30)


if __name__ == "__main__":
    main()
