"""Coop Application Autopilot — `vault coop` subcommands."""
import os
from datetime import date, timedelta
from pathlib import Path

import click
from rich.console import Console

from config import get_config, vault_path
from utils import today, safe_write, append_to, log_brain, search_vault
from templates import application_note

console = Console()
VAULT = vault_path()


def _claude(prompt: str, max_tokens: int = 4096) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _fetch_url(url: str) -> str:
    import requests
    from bs4 import BeautifulSoup
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:6000]


@click.group()
def coop():
    """Coop application tools."""


@coop.command("add")
@click.argument("source")
def coop_add(source):
    """Add a job posting. Pass a URL or paste raw text."""
    cfg = get_config()

    if source.startswith("http"):
        console.print("[cyan]Fetching URL...[/cyan]")
        text = _fetch_url(source)
    else:
        text = source

    my_skills = ", ".join(cfg.get("skills", []))
    style = cfg.get("writing_style", "direct, no fluff, student voice")
    name = cfg.get("name", "Ethan")
    school = cfg.get("school", "Drexel University")

    console.print("[cyan]Analyzing and generating materials via Claude...[/cyan]")
    prompt = f"""You are a job application assistant. Analyze this job posting:

{text}

My skills: {my_skills}
My writing style: {style}
My name: {name}, student at {school}

Respond in this exact format:
COMPANY: <company name>
ROLE: <role title>
SKILLS_HAVE: <comma-separated skills I have from the posting>
SKILLS_MISSING: <comma-separated skills I'm missing>
FIT_SCORE: <1-10 integer>
COVER_LETTER:
<3 paragraphs, direct tone, no fluff, student voice>
COLD_EMAIL:
<under 100 words, specific, clear ask>
STORY_BULLETS:
<3 bullet points starting with '-'>
"""
    raw = _claude(prompt)

    # Parse response
    fields = {}
    current_key = None
    current_lines = []
    for line in raw.splitlines():
        if any(line.startswith(k + ":") for k in
               ["COMPANY", "ROLE", "SKILLS_HAVE", "SKILLS_MISSING",
                "FIT_SCORE", "COVER_LETTER", "COLD_EMAIL", "STORY_BULLETS"]):
            if current_key:
                fields[current_key] = "\n".join(current_lines).strip()
            k, _, v = line.partition(":")
            current_key = k.strip()
            current_lines = [v.strip()] if v.strip() else []
        else:
            current_lines.append(line)
    if current_key:
        fields[current_key] = "\n".join(current_lines).strip()

    company = fields.get("COMPANY", "Company")
    role = fields.get("ROLE", "Role")
    have = [s.strip() for s in fields.get("SKILLS_HAVE", "").split(",") if s.strip()]
    missing = [s.strip() for s in fields.get("SKILLS_MISSING", "").split(",") if s.strip()]

    content = application_note(
        company=company,
        role=role,
        cover_letter=fields.get("COVER_LETTER", ""),
        cold_email=fields.get("COLD_EMAIL", ""),
        story_bullets=fields.get("STORY_BULLETS", ""),
        fit_score=fields.get("FIT_SCORE", ""),
        skills_have=have,
        skills_missing=missing,
    )

    folder = VAULT / "Coop Search"
    filename = f"{company} - {role} - {today()}.md"
    path = safe_write(folder / filename, content)
    console.print(f"[green]Application created:[/green] {path}")
    console.print(f"Fit Score: [bold]{fields.get('FIT_SCORE', '?')}/10[/bold]")
    log_brain(f"[CLAUDE] Coop application: {company} - {role}")


@coop.command("status")
@click.argument("company")
@click.argument("new_status")
def coop_status(company, new_status):
    """Update status of an application."""
    valid = {"Applied", "Interviewing", "Offer", "Rejected"}
    if new_status not in valid:
        console.print(f"[red]Invalid status. Choose from: {', '.join(valid)}[/red]")
        return

    results = search_vault(company)
    matched = [
        (p, l) for p, l in results
        if "Coop Search" in str(p) and company.lower() in p.stem.lower()
    ]
    if not matched:
        console.print(f"[red]No application found for '{company}'.[/red]")
        return

    note_path = matched[0][0]
    from utils import update_frontmatter_field
    update_frontmatter_field(note_path, "status", new_status)
    append_to(note_path, f"- {today()} — Status updated to: {new_status}")
    console.print(f"[green]Updated {note_path.stem} → {new_status}[/green]")
    log_brain(f"[RUFLO] Status update: {company} -> {new_status}")


@coop.command("digest")
@click.option("--draft", is_flag=True, help="Generate follow-up emails via Claude.")
def coop_digest(draft):
    """Show applications with no update in 7+ days."""
    from datetime import datetime
    from utils import parse_frontmatter
    folder = VAULT / "Coop Search"
    stale = []
    for md in folder.glob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            applied = fm.get("date-applied", "")
            if not applied:
                continue
            d = datetime.strptime(applied, "%Y-%m-%d").date()
            if (date.today() - d).days >= 7:
                stale.append((md, fm))
        except Exception:
            continue

    if not stale:
        console.print("[green]No stale applications.[/green]")
        return

    console.print(f"[yellow]{len(stale)} application(s) need follow-up:[/yellow]")
    for md, fm in stale:
        console.print(f"  {md.stem} — status: {fm.get('status', '?')}")
        if draft:
            prompt = (
                f"Write a short follow-up email (under 80 words) for a "
                f"{fm.get('role','role')} application at {fm.get('company','company')}. "
                f"Applied {fm.get('date-applied','')}. Status: {fm.get('status','')}. "
                f"Student voice, direct, specific ask."
            )
            email = _claude(prompt, max_tokens=200)
            console.print(f"\n[bold]Draft email:[/bold]\n{email}\n")
            log_brain(f"[CLAUDE] Follow-up draft: {md.stem}")
