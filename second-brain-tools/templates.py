"""All note templates. Returns formatted markdown strings."""
from datetime import date, timedelta


def _today() -> str:
    return date.today().strftime("%Y-%m-%d")


def trade_note(ticker="", entry="", exit_price="", result="", pnl="",
               emotion_before="", emotion_after="", bias_detected="") -> str:
    return f"""---
title: "{ticker} Trade - {_today()}"
date: {_today()}
type: trade
ticker: {ticker}
entry: {entry}
exit: {exit_price}
result: {result}
pnl: {pnl}
emotion-before: {emotion_before}
emotion-after: {emotion_after}
bias-detected: {bias_detected}
tags: [trading]
---

## Setup

## Execution

## Review
"""


def idea_note(title="", steelman="", failure_modes="", next_step="", tags=None) -> str:
    tags_str = ", ".join(tags or ["ideas"])
    return f"""---
title: "{title}"
date: {_today()}
type: idea
tags: [{tags_str}]
---

## Steelman
{steelman}

## Failure Modes
{failure_modes}

## Next Step
{next_step}
"""


def contact_note(name="", context="", met_at="") -> str:
    follow_up = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    return f"""---
title: "{name}"
date-met: {_today()}
type: contact
follow-up-by: {follow_up}
last-contact: {_today()}
met-at: {met_at}
tags: [networking]
---

## Context
{context}

## Notes

## LinkedIn Draft

## Follow Up
- [ ] Follow up with [[{name}]] by {follow_up}
"""


def application_note(company="", role="", cover_letter="", cold_email="",
                     story_bullets="", fit_score="", skills_have=None,
                     skills_missing=None) -> str:
    follow_up = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    have = "\n".join(f"- {s}" for s in (skills_have or []))
    missing = "\n".join(f"- {s}" for s in (skills_missing or []))
    return f"""---
title: "{company} - {role}"
date-applied: {_today()}
type: application
company: {company}
role: {role}
status: Applied
follow-up-by: {follow_up}
fit-score: {fit_score}
tags: [coop]
---

## Fit Score: {fit_score}/10

### Skills I Have
{have}

### Skills Missing
{missing}

## Cover Letter
{cover_letter}

## Cold Email
{cold_email}

## Story Bullets
{story_bullets}

## Status Log
- {_today()} — Applied
"""


def calendar_note(title="", due="", gcal_id="", calendar_name="",
                  location="", description="") -> str:
    return f"""---
title: "{title}"
date: {_today()}
type: calendar-task
due: {due}
gcal-event-id: {gcal_id}
calendar-name: {calendar_name}
location: {location}
description: {description}
status: pending
tags: [calendar]
---

## Details
{description}

## Notes
"""


def daily_note(date_str: str, events: list[dict] = None) -> str:
    events = events or []
    event_lines = ""
    for e in sorted(events, key=lambda x: x.get("time", "")):
        event_lines += f"- [ ] {e.get('time', '')} — {e.get('title', '')}\n"
    return f"""---
title: "Daily Note - {date_str}"
date: {date_str}
type: daily
tags: [daily]
---

## Calendar
{event_lines}
## Done

## Notes

## Tomorrow
"""


def weekly_review_note(date_str: str, summary: str) -> str:
    return f"""---
title: "{date_str} Weekly Review"
date: {date_str}
type: weekly-review
tags: [review]
---

## Summary
{summary}
"""


def study_package_note(course: str, exam_date: str, days_until: int,
                        prep: str, quiz: str, schedule: str, sowhat: str) -> str:
    return f"""---
title: "{course} Study Package"
date: {_today()}
type: study-package
course: {course}
exam-date: {exam_date}
days-until-exam: {days_until}
tags: [academics]
---

## Study Guide
{prep}

## Quiz
{quiz}

## Schedule
{schedule}

## So What?
{sowhat}
"""
