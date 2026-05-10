"""Academic Grind Assistant — `vault grind` subcommands."""
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import click
from rich.console import Console

from config import vault_path
from utils import today, safe_write, log_brain
from templates import study_package_note

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


def _read_course_notes(course: str) -> str:
    folder = VAULT / "Academics" / course
    if not folder.exists():
        return ""
    parts = []
    for md in sorted(folder.rglob("*.md")):
        try:
            parts.append(md.read_text(encoding="utf-8")[:2000])
        except Exception:
            continue
    return "\n---\n".join(parts[:20])


@click.group()
def grind():
    """Academic grind tools."""


@grind.command("prep")
@click.argument("course")
def grind_prep(course):
    """Generate a prioritized study guide for a course."""
    notes = _read_course_notes(course)
    if not notes:
        console.print(f"[red]No notes found for course '{course}'.[/red]")
        return
    prompt = (
        f"You are a study assistant. Based on these course notes, generate a "
        f"prioritized study guide for {course}. Order: foundational concepts first, "
        f"complex applications last. Use ## headers for sections. Be concise.\n\n{notes}"
    )
    console.print("[cyan]Generating study guide...[/cyan]")
    result = _claude(prompt)
    folder = VAULT / "Academics" / course
    path = safe_write(folder / f"{today()} - {course} Study Guide.md", result)
    console.print(f"[green]Study guide saved:[/green] {path}")
    log_brain(f"[CLAUDE] Study guide: {course}")


@grind.command("quiz")
@click.argument("course")
@click.option("--count", default=10, show_default=True)
def grind_quiz(course, count):
    """Generate a quiz for a course."""
    notes = _read_course_notes(course)
    if not notes:
        console.print(f"[red]No notes found for course '{course}'.[/red]")
        return
    prompt = (
        f"Generate {count} quiz questions for {course} based on these notes. "
        f"Mix: multiple choice, short answer, explain-in-plain-English. "
        f"After each question put the answer in a blockquote (> Answer: ...). "
        f"Use numbered questions.\n\n{notes}"
    )
    console.print("[cyan]Generating quiz...[/cyan]")
    result = _claude(prompt)
    folder = VAULT / "Academics" / course
    path = safe_write(folder / f"{today()} - {course} Quiz.md", result)
    console.print(f"[green]Quiz saved:[/green] {path}")
    log_brain(f"[CLAUDE] Quiz generated: {course}")


@grind.command("schedule")
@click.argument("course")
@click.option("--exam-date", required=True)
def grind_schedule(course, exam_date):
    """Generate a day-by-day study schedule and add calendar events."""
    notes = _read_course_notes(course)
    exam_dt = datetime.strptime(exam_date, "%Y-%m-%d").date()
    days_left = (exam_dt - date.today()).days
    if days_left <= 0:
        console.print("[red]Exam date is in the past.[/red]")
        return

    prompt = (
        f"Create a {days_left}-day study schedule for {course} leading to exam on {exam_date}. "
        f"For each day: specific topic + estimated time. Format as:\n"
        f"## YYYY-MM-DD\n- [ ] Topic (X hours)\n\nBased on these notes:\n{notes}"
    )
    console.print("[cyan]Generating schedule...[/cyan]")
    result = _claude(prompt)

    folder = VAULT / "Academics" / course
    path = safe_write(folder / f"{course} Study Schedule.md", result)
    console.print(f"[green]Schedule saved:[/green] {path}")

    # Create Google Calendar study blocks
    try:
        from calendar_sync import create_study_events
        create_study_events(course, result, exam_date)
        console.print("[green]Calendar study blocks created.[/green]")
    except Exception as e:
        console.print(f"[yellow]Calendar events skipped: {e}[/yellow]")
    log_brain(f"[CLAUDE] Study schedule: {course} (exam {exam_date})")


@grind.command("sowhat")
@click.argument("course")
def grind_sowhat(course):
    """Answer 'So what?' for every major concept."""
    notes = _read_course_notes(course)
    if not notes:
        console.print(f"[red]No notes found for course '{course}'.[/red]")
        return
    prompt = (
        f"For each major concept in these {course} notes, answer: "
        f"'So what? Why does this matter outside this course?' "
        f"Use ## headers for each concept.\n\n{notes}"
    )
    console.print("[cyan]Generating so-what analysis...[/cyan]")
    result = _claude(prompt)
    folder = VAULT / "Academics" / course
    path = safe_write(folder / f"{course} So What.md", result)
    console.print(f"[green]So-what saved:[/green] {path}")
    log_brain(f"[CLAUDE] So-what analysis: {course}")


@grind.command("save")
@click.argument("course")
@click.option("--exam-date", required=True)
def grind_save(course, exam_date):
    """Run all grind commands and save as one Study Package."""
    notes = _read_course_notes(course)
    if not notes:
        console.print(f"[red]No notes found for course '{course}'.[/red]")
        return

    exam_dt = datetime.strptime(exam_date, "%Y-%m-%d").date()
    days_until = (exam_dt - date.today()).days

    console.print("[cyan]Generating full study package (4 Claude calls)...[/cyan]")

    def ask(task_prompt):
        return _claude(f"{task_prompt}\n\nCourse notes:\n{notes}")

    prep = ask(f"Generate a prioritized study guide for {course}. ## headers, foundational first.")
    quiz = ask(f"Generate 10 quiz questions for {course}. Mix types. Answers in > blockquotes.")
    schedule = ask(
        f"Create a {days_until}-day study schedule for {course} (exam {exam_date}). "
        f"Format: ## YYYY-MM-DD\n- [ ] Topic (X hours)"
    )
    sowhat = ask(f"For each major concept in {course}, answer 'So what? Why does this matter?' ## headers.")

    content = study_package_note(
        course=course,
        exam_date=exam_date,
        days_until=days_until,
        prep=prep,
        quiz=quiz,
        schedule=schedule,
        sowhat=sowhat,
    )
    folder = VAULT / "Academics" / course
    path = safe_write(folder / f"_Study Package.md", content)
    console.print(f"[green]Study package saved:[/green] {path}")
    log_brain(f"[CLAUDE] Study package: {course} (exam {exam_date})")
