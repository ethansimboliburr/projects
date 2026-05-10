"""vault CLI — installable as the `vault` command."""
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()

from config import get_config, vault_path
from utils import (
    today, slug, safe_write, append_to, log_brain, search_vault,
    ai_available, AI_UNAVAILABLE_MSG,
)
from templates import (
    trade_note, idea_note, contact_note,
    application_note, daily_note, weekly_review_note,
)

VAULT = vault_path()


def _claude(prompt: str, max_tokens: int = 4096) -> str | None:
    """Call Claude API. Returns None if key is missing."""
    if not ai_available():
        return None
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _gcal_sync():
    from calendar_sync import sync_calendar
    sync_calendar()


@click.group()
def cli():
    """Second Brain vault CLI."""


# ── vault log ─────────────────────────────────────────────────────────────

@cli.group()
def log():
    """Log things to your vault."""


@log.command("trade")
@click.argument("details")
def log_trade(details):
    """Log a trade."""
    import re
    ticker = ""
    m = re.search(r"\b([A-Z]{1,5})\b", details)
    if m:
        ticker = m.group(1)

    content = trade_note(ticker=ticker)
    content += f"\n> Raw input: {details}\n"

    folder = VAULT / "Trading Progress"
    filename = f"{today()} - {ticker or 'Trade'} Trade.md"
    path = safe_write(folder / filename, content)
    console.print(f"[green]Trade note created:[/green] {path}")
    log_brain(f"[RUFLO] Trade note created: {filename}")


@log.command("idea")
@click.argument("details")
def log_idea(details):
    """Log an idea. Claude generates analysis if API key is set."""
    if not ai_available():
        console.print(f"[yellow]{AI_UNAVAILABLE_MSG}[/yellow]")
        title = slug(details[:40])
        content = idea_note(title=title)
        content += f"\n> Raw input: {details}\n"
    else:
        console.print("[cyan]Generating idea analysis via Claude...[/cyan]")
        prompt = (
            f"You are a critical thinking assistant. The user has this idea:\n\n{details}\n\n"
            "Respond with ONLY the following three sections (no preamble):\n"
            "TITLE: <inferred short title>\n"
            "STEELMAN: <strongest version of this idea in 2-3 sentences>\n"
            "FAILURE_MODES: <3 bullet points of ways it could fail>\n"
            "NEXT_STEP: <single most important next action>"
        )
        raw = _claude(prompt, max_tokens=512)
        lines = {}
        for line in (raw or "").splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                lines[k.strip().upper()] = v.strip()
        title = lines.get("TITLE", slug(details[:40]))
        content = idea_note(
            title=title,
            steelman=lines.get("STEELMAN", ""),
            failure_modes=lines.get("FAILURE_MODES", ""),
            next_step=lines.get("NEXT_STEP", ""),
        )

    folder = VAULT / "Ideas"
    path = safe_write(folder / f"{today()} - {slug(title)}.md", content)
    console.print(f"[green]Idea note created:[/green] {path}")
    log_brain("[CLAUDE] Idea note created" if ai_available() else "[RUFLO] Idea note created (no AI key)")


@log.command("contact")
@click.argument("details")
def log_contact(details):
    """Log a contact. Format: 'Name - context'."""
    if " - " in details:
        name, context = details.split(" - ", 1)
    else:
        name, context = details, ""
    name, context = name.strip(), context.strip()

    if ai_available():
        console.print("[cyan]Generating LinkedIn draft via Claude...[/cyan]")
        prompt = (
            f"Write a short, genuine LinkedIn connection message (under 60 words) "
            f"from a Drexel CS student to {name}. Context: {context}. "
            f"No subject line. No fluff. First-person, direct."
        )
        draft = _claude(prompt, max_tokens=200) or ""
    else:
        console.print(f"[yellow]{AI_UNAVAILABLE_MSG}[/yellow]")
        draft = "[Add LinkedIn message here]"

    folder = VAULT / "Networking" / "People"
    note_path = folder / f"{name}.md"

    if note_path.exists():
        append_to(note_path, f"\n## Follow Up — {today()}\n{context}\n")
        console.print(f"[yellow]Appended to existing note:[/yellow] {note_path}")
    else:
        content = contact_note(name=name, context=context)
        content += f"\n{draft}\n"
        note_path = safe_write(note_path, content)
        console.print(f"[green]Contact note created:[/green] {note_path}")

    encoded = name.replace(" ", "%20")
    console.print(f"\n[bold]LinkedIn search:[/bold] https://www.linkedin.com/search/results/people/?keywords={encoded}")
    if draft and draft != "[Add LinkedIn message here]":
        console.print(f"\n[bold]LinkedIn Draft:[/bold]\n{draft}")
    log_brain(f"[RUFLO] Contact note: {name}")


@log.command("app")
@click.argument("details")
def log_app(details):
    """Log a job application. Format: 'Company - Role'."""
    if " - " in details:
        company, role = details.split(" - ", 1)
    else:
        company, role = details, "Role"
    company, role = company.strip(), role.strip()

    content = application_note(company=company, role=role)
    folder = VAULT / "Coop Search"
    filename = f"{company} - {role}.md"
    path = safe_write(folder / filename, content)
    console.print(f"[green]Application note created:[/green] {path}")
    log_brain(f"[RUFLO] Application logged: {company} - {role}")


# ── vault daily ───────────────────────────────────────────────────────────

@cli.command()
def daily():
    """Create today's daily note (only if daily_notes_enabled)."""
    cfg = get_config()
    if not cfg.get("daily_notes_enabled", False):
        console.print("Daily notes disabled. Set daily_notes_enabled: true in My Vault Config.md to enable.")
        return
    from calendar_sync import get_today_events
    events = get_today_events()
    content = daily_note(today(), events)
    folder = VAULT / "Meta" / "Calendar"
    path = safe_write(folder / f"{today()}.md", content)
    console.print(f"[green]Daily note created:[/green] {path}")


# ── vault sync-cal ────────────────────────────────────────────────────────

@cli.command("sync-cal")
def sync_cal():
    """Manually trigger Google Calendar sync."""
    console.print("[cyan]Syncing Google Calendar...[/cyan]")
    _gcal_sync()
    console.print("[green]Sync complete.[/green]")


# ── vault weekly ──────────────────────────────────────────────────────────

@cli.command()
def weekly():
    """Generate a weekly review summary."""
    if not ai_available():
        console.print(f"[yellow]{AI_UNAVAILABLE_MSG}[/yellow]")
        console.print("vault weekly requires ANTHROPIC_API_KEY.")
        return

    from datetime import timedelta
    cutoff = date.today() - timedelta(days=7)
    notes = []
    for md in VAULT.rglob("*.md"):
        try:
            mtime = date.fromtimestamp(md.stat().st_mtime)
            if mtime >= cutoff:
                notes.append(md.read_text(encoding="utf-8")[:300])
        except Exception:
            continue

    combined = "\n---\n".join(notes[:30])
    prompt = (
        f"Based on these vault notes from the past 7 days, write a concise weekly "
        f"summary paragraph (200 words max). Focus on: progress made, themes, "
        f"open loops to close.\n\n{combined}"
    )
    console.print("[cyan]Generating weekly review via Claude...[/cyan]")
    summary = _claude(prompt, max_tokens=400) or ""
    content = weekly_review_note(today(), summary)
    path = safe_write(VAULT / "Meta" / f"{today()} Weekly Review.md", content)
    console.print(f"[green]Weekly review saved:[/green] {path}")
    log_brain("[CLAUDE] Weekly review generated")


# ── vault find ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("query")
def find(query):
    """Search all vault notes."""
    results = search_vault(query)
    if not results:
        console.print(f"No results for '{query}'.")
        return
    for path, line in results:
        rel = path.relative_to(VAULT)
        console.print(f"[bold]{rel}[/bold]\n  {line}\n")


# ── vault start ───────────────────────────────────────────────────────────

@cli.command()
def start():
    """Launch brain.py as a background daemon."""
    here = Path(__file__).parent
    brain = here / "brain.py"
    proc = subprocess.Popen(
        [sys.executable, str(brain)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    console.print(f"[green]brain.py started (PID {proc.pid}).[/green]")
    if not ai_available():
        console.print("[yellow]Note: ANTHROPIC_API_KEY not set — AI features disabled. Calendar sync and all RUFLO tasks will run normally.[/yellow]")
    console.print("Calendar sync running now. Everything watches automatically.")
    log_brain(f"[RUFLO] brain.py launched (PID {proc.pid})")


from coop_bot import coop
cli.add_command(coop)

from academic_assistant import grind
cli.add_command(grind)


if __name__ == "__main__":
    cli()
