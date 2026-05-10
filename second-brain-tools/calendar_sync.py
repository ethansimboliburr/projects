"""Google Calendar sync — pulls events and writes vault notes."""
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from config import get_config, vault_path
from utils import today, safe_write, log_brain, find_note_by_gcal_id, update_frontmatter_field
from templates import calendar_note

VAULT = vault_path()
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _get_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds_path = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
    token_path = Path("token.json")
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds), creds


def _get_gmail(creds):
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


def _event_time(event: dict) -> str:
    start = event.get("start", {})
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    return ""


def _event_date(event: dict) -> str:
    start = event.get("start", {})
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    return start.get("date", today())


def get_today_events() -> list[dict]:
    try:
        service, _ = _get_service()
        now = datetime.utcnow()
        start = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
        end = now.replace(hour=23, minute=59, second=59).isoformat() + "Z"
        result = service.events().list(
            calendarId="primary", timeMin=start, timeMax=end,
            singleEvents=True, orderBy="startTime"
        ).execute()
        events = result.get("items", [])
        return [{"time": _event_time(e), "title": e.get("summary", "")} for e in events]
    except Exception as e:
        log_brain(f"[ERROR] get_today_events: {e}")
        return []


def _smart_route(title: str, gcal_id: str, note_path: Path) -> None:
    tl = title.lower()
    # Interview/coop routing
    if "interview" in tl or "coop" in tl:
        for md in (VAULT / "Coop Search").glob("*.md"):
            if any(w in md.stem.lower() for w in tl.split()):
                update_frontmatter_field(md, "status", "Interviewing")
                log_brain(f"[RUFLO] Auto-status: {md.stem} -> Interviewing")
    # Academic routing
    if "study" in tl or "exam" in tl:
        link = f"\n\n## Linked\n[[{note_path.stem}]]"
        for md in (VAULT / "Academics").rglob("*.md"):
            if any(w in md.stem.lower() for w in tl.split() if len(w) > 3):
                from utils import append_to
                append_to(md, link)
                break
    # Contact routing
    if "call" in tl:
        for md in (VAULT / "Networking" / "People").glob("*.md"):
            if md.stem.lower() in tl:
                from utils import append_to
                append_to(md, f"\n- [ ] Call scheduled {today()}")
                break


def sync_calendar() -> None:
    try:
        service, creds = _get_service()
    except Exception as e:
        log_brain(f"[ERROR] Calendar auth failed: {e}")
        return

    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=14)).isoformat() + "Z"

    try:
        cal_list = service.calendarList().list().execute()
        calendars = [c["id"] for c in cal_list.get("items", [])]
    except Exception:
        calendars = ["primary"]

    calendar_dir = VAULT / "Meta" / "Calendar"
    calendar_dir.mkdir(parents=True, exist_ok=True)

    processed_ids = set()

    for cal_id in calendars:
        try:
            result = service.events().list(
                calendarId=cal_id, timeMin=time_min, timeMax=time_max,
                singleEvents=True, orderBy="startTime", maxResults=100
            ).execute()
            events = result.get("items", [])
        except Exception as e:
            log_brain(f"[ERROR] Calendar fetch {cal_id}: {e}")
            continue

        for event in events:
            gcal_id = event.get("id", "")
            if not gcal_id or gcal_id in processed_ids:
                continue
            processed_ids.add(gcal_id)

            title = event.get("summary", "Untitled Event")
            event_date = _event_date(event)
            location = event.get("location", "")
            description = event.get("description", "")
            status = event.get("status", "confirmed")

            existing = find_note_by_gcal_id(gcal_id)

            if status == "cancelled":
                if existing and existing.exists():
                    existing.unlink()
                    log_brain(f"[RUFLO] Deleted cancelled event note: {existing.stem}")
                continue

            if existing:
                update_frontmatter_field(existing, "due", event_date)
                update_frontmatter_field(existing, "location", location)
                log_brain(f"[RUFLO] Updated event note: {existing.stem}")
            else:
                content = calendar_note(
                    title=title,
                    due=event_date,
                    gcal_id=gcal_id,
                    calendar_name=cal_id,
                    location=location,
                    description=description,
                )
                safe_note = title.replace("/", "-").replace("\\", "-")[:60]
                note_path = safe_write(
                    calendar_dir / f"{event_date} - {safe_note}.md",
                    content
                )
                _smart_route(title, gcal_id, note_path)
                log_brain(f"[RUFLO] Created event note: {note_path.stem}")

    log_brain(f"[RUFLO] Calendar sync complete — {len(processed_ids)} events processed")


def create_study_events(course: str, schedule_md: str, exam_date: str) -> None:
    """Parse a study schedule markdown and create Google Calendar events."""
    try:
        service, _ = _get_service()
    except Exception as e:
        log_brain(f"[ERROR] Calendar auth for study events: {e}")
        return

    date_blocks = re.findall(r"## (\d{4}-\d{2}-\d{2})\n((?:- \[.\].*\n?)*)", schedule_md)
    for date_str, tasks_block in date_blocks:
        tasks = re.findall(r"- \[.\] (.+)", tasks_block)
        for task in tasks:
            event_body = {
                "summary": f"{course}: {task}",
                "description": f"[[{course}/Week]]",
                "start": {"dateTime": f"{date_str}T12:00:00", "timeZone": "America/New_York"},
                "end": {"dateTime": f"{date_str}T13:00:00", "timeZone": "America/New_York"},
                "colorId": "9",  # blueberry
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "email", "minutes": 1440}],
                },
            }
            try:
                service.events().insert(calendarId="primary", body=event_body).execute()
            except Exception as e:
                log_brain(f"[ERROR] Create study event {date_str}: {e}")


def create_assignment_events(course: str, assignments: list[dict]) -> None:
    """Create Google Calendar events for assignments with time-blocking rules."""
    try:
        service, _ = _get_service()
    except Exception as e:
        log_brain(f"[ERROR] Calendar auth for assignments: {e}")
        return

    # Group by date
    from collections import defaultdict
    by_date: dict[str, list] = defaultdict(list)
    for a in assignments:
        if not a.get("due_date"):
            log_brain(f"[RUFLO] Missing due date: {a.get('name','?')} from {course}")
            continue
        by_date[a["due_date"]].append(a)

    for due_date, items in by_date.items():
        overflow = len(items) >= 9
        for i, item in enumerate(items):
            if overflow:
                start_hour = 9 + i
            else:
                start_hour = 12 + i
            if start_hour >= 23:
                start_hour = 22
            end_hour = start_hour + 1

            event_body = {
                "summary": f"{course}: {item['name']}",
                "description": f"[[{course}/Week]]",
                "start": {"dateTime": f"{due_date}T{start_hour:02d}:00:00", "timeZone": "America/New_York"},
                "end": {"dateTime": f"{due_date}T{end_hour:02d}:00:00", "timeZone": "America/New_York"},
                "colorId": "3",  # mauve/purple
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "email", "minutes": 1440}],
                },
            }
            try:
                service.events().insert(calendarId="primary", body=event_body).execute()
                log_brain(f"[RUFLO] Assignment event: {course} - {item['name']} on {due_date}")
            except Exception as e:
                log_brain(f"[ERROR] Assignment event {due_date}: {e}")
