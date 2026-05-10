"""Parses images via Claude vision API and routes to correct vault note type."""
import base64
import os
from pathlib import Path

from config import vault_path
from utils import today, safe_write, log_brain, ai_available

VAULT = vault_path()


def _claude_vision(image_path: Path, prompt: str) -> str | None:
    if not ai_available():
        return None
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    data = base64.standard_b64encode(image_path.read_bytes()).decode()
    ext = image_path.suffix.lstrip(".").lower()
    media_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                  "png": "image/png", "gif": "image/gif",
                  "webp": "image/webp"}.get(ext, "image/png")
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return msg.content[0].text


def _detect_type_from_filename(image_path: Path) -> str:
    """Heuristic routing from filename when AI is unavailable."""
    name = image_path.stem.lower()
    if any(w in name for w in ["trade", "chart", "pnl", "nq", "es", "spy"]):
        return "trade"
    if any(w in name for w in ["job", "posting", "role", "coop"]):
        return "application"
    if any(w in name for w in ["syllabus", "course", "schedule"]):
        return "syllabus"
    if any(w in name for w in ["card", "contact", "person"]):
        return "contact"
    return "misc"


def _detect_type(raw: str) -> str:
    rl = raw.lower()
    if any(w in rl for w in ["ticker", "entry", "exit", "pnl", "trade", "bought", "sold", "profit", "loss"]):
        return "trade"
    if any(w in rl for w in ["job", "role", "company", "apply", "requirements", "qualifications"]):
        return "application"
    if any(w in rl for w in ["syllabus", "course", "week", "assignment", "due date", "lecture"]):
        return "syllabus"
    if any(w in rl for w in ["name", "email", "phone", "linkedin", "title"]):
        return "contact"
    return "misc"


def process_image(image_path: Path) -> None:
    if not ai_available():
        # Fall back to filename-based routing, create a stub note
        content_type = _detect_type_from_filename(image_path)
        log_brain(f"[RUFLO] Screenshot (no AI key) filename-routed: {image_path.name} -> {content_type}")
        _route_no_ai(image_path, content_type)
        _archive(image_path)
        return

    prompt = (
        "Analyze this screenshot. Identify what type of content it is "
        "(trade/brokerage data, job posting, business card/contact, syllabus, or other). "
        "Then extract all relevant information in a structured way."
    )
    try:
        raw = _claude_vision(image_path, prompt) or ""
    except Exception as e:
        log_brain(f"[ERROR] Vision API failed for {image_path.name}: {e}")
        return

    content_type = _detect_type(raw)
    log_brain(f"[CLAUDE] Screenshot parsed: {image_path.name} -> {content_type}")

    if content_type == "trade":
        _route_trade(image_path, raw)
    elif content_type == "application":
        _route_application(raw)
    elif content_type == "syllabus":
        _route_syllabus(raw)
    elif content_type == "contact":
        _route_contact(raw)
    else:
        _route_misc(image_path, raw)

    _archive(image_path)


def _route_no_ai(image_path: Path, content_type: str) -> None:
    """Create a stub note when no AI key is available."""
    content = (
        f"---\ntitle: \"{image_path.stem}\"\ndate: {today()}\ntype: {content_type}\ntags: [inbox]\n---\n\n"
        f"## Screenshot\nFile: {image_path.name}\n\n"
        f"[Add ANTHROPIC_API_KEY to .env to enable automatic content extraction]\n"
    )
    dest_map = {
        "trade": VAULT / "Trading Progress",
        "application": VAULT / "Coop Search",
        "contact": VAULT / "Networking" / "People",
        "syllabus": VAULT / "Academics",
    }
    folder = dest_map.get(content_type, VAULT / "Meta")
    safe_write(folder / f"{today()} - {image_path.stem}.md", content)


def _route_trade(image_path: Path, raw: str) -> None:
    from templates import trade_note
    import re
    ticker = ""
    m = re.search(r"\b([A-Z]{1,5})\b", raw)
    if m:
        ticker = m.group(1)
    content = trade_note(ticker=ticker)
    content += f"\n## Screenshot Analysis\n{raw}\n"
    folder = VAULT / "Trading Progress"
    path = safe_write(folder / f"{today()} - {ticker or 'Screenshot'} Trade.md", content)
    log_brain(f"[RUFLO] Screenshot trade note: {path.stem}")


def _route_application(raw: str) -> None:
    from templates import application_note
    import re
    fields = {}
    for line in raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip().upper()] = v.strip()
    company = fields.get("COMPANY", "Company")
    role = fields.get("ROLE", "Role")
    content = application_note(company=company, role=role)
    folder = VAULT / "Coop Search"
    path = safe_write(folder / f"{company} - {role}.md", content)
    log_brain(f"[RUFLO] Screenshot application note: {path.stem}")


def _route_syllabus(raw: str) -> None:
    import re
    from calendar_sync import create_assignment_events
    course_match = re.search(r"(?:course|class)[:\s]+([A-Za-z0-9 ]+)", raw, re.I)
    course = course_match.group(1).strip() if course_match else "Unknown Course"
    folder = VAULT / "Academics" / course
    folder.mkdir(parents=True, exist_ok=True)
    path = safe_write(folder / "_Course Breakdown.md", f"# {course}\n\n{raw}")
    log_brain(f"[RUFLO] Syllabus note: {path}")
    assignments = []
    for line in raw.splitlines():
        date_m = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})", line)
        if date_m and len(line) > 10:
            raw_date = date_m.group(1)
            try:
                if "/" in raw_date:
                    parts = raw_date.split("/")
                    if len(parts[2]) == 2:
                        parts[2] = "20" + parts[2]
                    due = f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"
                else:
                    due = raw_date
                name = re.sub(r"[\d/\-]", "", line).strip()[:80]
                if name:
                    assignments.append({"name": name, "due_date": due})
            except Exception:
                continue
    if assignments:
        create_assignment_events(course, assignments)


def _route_contact(raw: str) -> None:
    from templates import contact_note
    import re
    name_m = re.search(r"(?:name)[:\s]+([A-Za-z ]+)", raw, re.I)
    name = name_m.group(1).strip() if name_m else "Unknown Contact"
    content = contact_note(name=name, context=raw[:300])
    folder = VAULT / "Networking" / "People"
    path = safe_write(folder / f"{name}.md", content)
    log_brain(f"[RUFLO] Screenshot contact note: {path.stem}")


def _route_misc(image_path: Path, raw: str) -> None:
    content = f"---\ntitle: \"{image_path.stem}\"\ndate: {today()}\ntype: misc\ntags: [inbox]\n---\n\n{raw}\n"
    path = safe_write(VAULT / "Meta" / f"{today()} - {image_path.stem}.md", content)
    log_brain(f"[RUFLO] Misc screenshot note: {path.stem}")


def _archive(image_path: Path) -> None:
    processed = VAULT / "Inbox" / "Processed"
    processed.mkdir(parents=True, exist_ok=True)
    dest = processed / image_path.name
    i = 1
    while dest.exists():
        dest = processed / f"{image_path.stem}-{i}{image_path.suffix}"
        i += 1
    image_path.rename(dest)
