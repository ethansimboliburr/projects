"""Watches Inbox/ and processes every dropped file automatically."""
import os
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config import vault_path
from utils import today, safe_write, log_brain, append_to

VAULT = vault_path()
INBOX = VAULT / "Inbox"
PROCESSED = INBOX / "Processed"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _detect_text_type(text: str) -> str:
    tl = text.lower()
    if any(w in tl for w in ["ticker", "entry", "exit", "pnl", "bought", "sold"]):
        return "trade"
    if any(w in tl for w in ["met", "talked", "connected with", "linkedin"]):
        return "contact"
    if any(w in tl for w in ["applied", "application", "coop", "internship", "job"]):
        return "application"
    if any(w in tl for w in ["exam", "quiz", "study", "lecture", "assignment", "due"]):
        return "academic"
    if any(w in tl for w in ["idea", "what if", "concept", "could build"]):
        return "idea"
    return "daily"


def process_file(path: Path) -> None:
    if not path.exists() or path.parent.name == "Processed":
        return
    ext = path.suffix.lower()
    try:
        if ext in IMAGE_EXTS:
            from screenshot_parser import process_image
            process_image(path)
        elif ext == ".txt":
            _process_text(path)
        elif ext == ".pdf":
            _process_pdf(path)
        else:
            log_brain(f"[RUFLO] Unknown file type in Inbox: {path.name}")
            _archive(path)
    except Exception as e:
        log_brain(f"[ERROR] Inbox processing failed for {path.name}: {e}")


def _process_text(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    content_type = _detect_text_type(text)
    log_brain(f"[RUFLO] Text file detected as: {content_type}")

    if content_type == "trade":
        from templates import trade_note
        content = trade_note()
        content += f"\n## Raw Input\n{text}\n"
        safe_write(VAULT / "Trading Progress" / f"{today()} - Text Trade.md", content)
    elif content_type == "contact":
        import re
        m = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+)", text)
        name = m.group(1) if m else "Unknown"
        from templates import contact_note
        safe_write(VAULT / "Networking" / "People" / f"{name}.md", contact_note(name=name, context=text[:300]))
    elif content_type == "application":
        from templates import application_note
        safe_write(VAULT / "Coop Search" / f"{today()} - Application.md", application_note())
    elif content_type == "idea":
        from templates import idea_note
        safe_write(VAULT / "Ideas" / f"{today()} - Inbox Idea.md", idea_note(title=path.stem, steelman=text[:300]))
    else:
        daily = VAULT / "Meta" / "Calendar" / f"{today()}.md"
        if daily.exists():
            append_to(daily, f"\n## Inbox Drop\n{text}\n")
        else:
            safe_write(VAULT / "Inbox" / "Docs" / f"{today()} - drop.md",
                       f"---\ntitle: Inbox Drop\ndate: {today()}\ntype: daily\ntags: [inbox]\n---\n\n{text}\n")
    _archive(path)


def _process_pdf(path: Path) -> None:
    try:
        import importlib.util
        if importlib.util.find_spec("pypdf") is not None:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            text = " ".join(page.extract_text() or "" for page in reader.pages)
        else:
            text = f"PDF: {path.name} (install pypdf to extract text)"
    except Exception as e:
        text = f"PDF extraction failed: {e}"
        log_brain(f"[ERROR] PDF extraction: {path.name}: {e}")

    # Treat extracted text same as .txt
    tmp = path.with_suffix(".txt")
    tmp.write_text(text, encoding="utf-8")
    _process_text(tmp)
    tmp.unlink(missing_ok=True)
    _archive(path)


def _archive(path: Path) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    dest = PROCESSED / path.name
    i = 1
    while dest.exists():
        dest = PROCESSED / f"{path.stem}-{i}{path.suffix}"
        i += 1
    try:
        path.rename(dest)
    except Exception:
        pass


class InboxHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        # Small delay so file is fully written before reading
        time.sleep(1.5)
        process_file(path)


def start_inbox_watcher() -> Observer:
    INBOX.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(InboxHandler(), str(INBOX), recursive=False)
    observer.start()
    log_brain("[RUFLO] Inbox watcher started")
    return observer
