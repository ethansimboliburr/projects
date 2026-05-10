# Second Brain Tools

A unified personal life automation system integrating your Obsidian vault with Google Calendar, Gmail, and the Claude API.

## Installation

```bash
cd second-brain-tools
pip install -e .
```

This makes `vault` available as a global CLI command.

## First-time Setup

### 1. Environment variables

Copy `.env.example` to `.env` and fill in your values:

```
ANTHROPIC_API_KEY=sk-ant-...
VAULT_PATH=C:\Users\ethan\OneDrive\Desktop\AIBrain\SecondBrain
GOOGLE_CREDENTIALS_PATH=credentials.json
```

### 2. Google Calendar OAuth2

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Calendar API**, **Gmail API**, **Drive API**
3. Create OAuth2 credentials → Download as `credentials.json` → place in `second-brain-tools/`
4. Run any `vault sync-cal` command — a browser window will open for one-time auth
5. `token.json` is cached automatically after that

Required scopes (already configured in `calendar_sync.py`):
- `calendar.readonly`
- `gmail.send`
- `gmail.modify`
- `drive.readonly`

### 3. Start the daemon

```bash
vault start
```

This launches `brain.py` in the background. It runs a calendar sync immediately and then again every morning at 8am.

## All Commands

### Logging

```bash
vault log trade "NQ long 21050 exit 21100 +250"
vault log idea "what if there was an app that..."
vault log contact "Jane Smith - met at Drexel career fair, ML engineer at Shopify"
vault log app "Shopify - Backend Engineer Coop"
```

### Calendar

```bash
vault sync-cal          # Force a full Google Calendar sync
vault daily             # Create today's daily note (if enabled in config)
```

### Review

```bash
vault weekly            # Generate AI weekly summary
vault find "query"      # Search all vault notes
```

### Coop Applications

```bash
vault coop add "https://jobs.shopify.com/..."
vault coop add "[paste raw job posting text]"
vault coop status "Shopify" "Interviewing"
vault coop digest
vault coop digest --draft
```

### Academic Grind

```bash
vault grind prep "CS375"
vault grind quiz "CS375" --count 15
vault grind schedule "CS375" --exam-date 2026-04-15
vault grind sowhat "CS375"
vault grind save "CS375" --exam-date 2026-04-15
```

### Daemon

```bash
vault start             # Launch brain.py in background
```

## Auto-run brain.py on Startup

### Windows (Task Scheduler)

```
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: At log on
4. Action: Start a program
   Program: python
   Arguments: C:\path\to\second-brain-tools\brain.py
   Start in: C:\path\to\second-brain-tools
```

Or use the vault command: `vault start` — the PID is logged to brain-log.md.

### Mac (launchd)

Create `~/Library/LaunchAgents/com.secondbrain.brain.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.secondbrain.brain</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/python3</string>
    <string>/path/to/second-brain-tools/brain.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>WorkingDirectory</key><string>/path/to/second-brain-tools</string>
</dict>
</plist>
```

Then: `launchctl load ~/Library/LaunchAgents/com.secondbrain.brain.plist`

### Linux (systemd)

Create `/etc/systemd/system/secondbrain.service`:

```ini
[Unit]
Description=Second Brain Daemon

[Service]
ExecStart=/usr/bin/python3 /path/to/second-brain-tools/brain.py
WorkingDirectory=/path/to/second-brain-tools
Restart=always

[Install]
WantedBy=default.target
```

Then: `systemctl enable secondbrain && systemctl start secondbrain`

## Vault Structure Requirements

Your vault must have these folders:

```
SecondBrain/
├── _Dashboard/
├── Academics/
├── Coop Search/
├── Ideas/
├── Inbox/
├── Meta/
│   └── Calendar/
├── Networking/
│   └── People/
├── Trading Progress/
│   └── Futures/
│       ├── SESSION_LOG.md
│       └── SUBMIT_TRADE.md
```

## How brain.py Works

| When | What |
|------|------|
| Startup | Full calendar sync + trade log scan |
| Every 30s | Vault file change detection |
| 8am daily | Morning pull (calendar + trade logs + optional daily note) |
| Every hour | Gmail scan for syllabus attachments |
| 1st of month | Dead note report |
| Always | Inbox watcher (any file dropped → auto-processed) |
| Always | Flask server at localhost:5002 for external text ingestion |

## Routing: RUFLO vs Claude API

Every task goes through `task_router()` in `brain.py`:

- **RUFLO** (zero API cost): file moves, status updates, frontmatter fixes, daily note appends, calendar pulls, duplicate checks
- **Claude API** (spend wisely): cover letters, trade psychology, weekly summary, idea steelmanning, study guides, quizzes, screenshot classification

All routing decisions are logged to `Meta/brain-log.md`.

## Inbox Drop Rules

Drop any file in `Inbox/` and it is processed automatically:

| File type | Action |
|-----------|--------|
| `.png/.jpg/.webp` | Claude vision → classified → routed to correct note type |
| `.txt` | Content detected → routed to trade/contact/application/idea/daily |
| `.pdf` | Text extracted → same as `.txt` (install `pypdf` for best results) |

All files are moved to `Inbox/Processed/` after handling.
