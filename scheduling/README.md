# scheduling

CLI weekly planner with Google Calendar sync — draft your week in the terminal, push to Google Calendar, and pull external events into the plan.

## What it does

Interactive terminal planner for building and managing a weekly schedule. Activities are stored in per-week JSON files (append-only archive). A nap window is injected at display time from config — not stored in data files — so changing it is a one-line edit with instant global effect.

Google Calendar integration supports push (plan → GCal, idempotent re-push), pull (GCal events written into the week JSON as `gcal_source` activities, never pushed back), and multi-account pull with timezone normalisation. Pulled events display in magenta with a 📍 location link.

Activities support an optional location field that renders as a clickable Google Maps hyperlink in the terminal and is included in the GCal event's native location field on push.

## Tech

Python, Google Calendar API, OAuth2, Rich, questionary, JSON

## Commands

```
plan show week [YYYY-WXX]   Week view (defaults to current)
plan show next / prev        Navigate weeks
plan show today              Day view
plan show YYYY-MM-DD         Specific day
plan add                     Interactive activity creation (title, time, notes, location, tags)
plan edit                    Interactive edit / delete (incl. nap override)
plan nap                     Update global nap window
plan check                   Outstanding ⚠️ items across all weeks
plan auth                    Google OAuth setup
plan whoami                  Show authenticated Google account
plan calendars               List all calendars visible to that account
plan push [YYYY-WXX|next|prev]   Push week to Google Calendar
plan pull [YYYY-WXX|next|prev]   Pull GCal events into week JSON and show
```

## Setup

```bash
pip install -r requirements.txt
```

Place `client_secret.json` in `credentials/`, then:

```bash
python plan.py auth
```

## Architecture

```
plan.py          CLI entry point + all commands
gcal.py          Google Calendar integration (auth, push, pull)
config.json      Global config: nap times, weekly themes, GCal settings
weeks/           Append-only archive of week files (YYYY-WXX.json)
archive/         Historical data
credentials/     OAuth token + client secret (gitignored)
```
