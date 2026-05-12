# Project Context — Weekly Planner CLI

> **Repo note:** `scheduling/` previously lived as a standalone GitHub repo (`simonhansedasi/scheduling`), then moved into `OmaElu/scheduling/` in March 2026, then into `dada_science/scheduling/` in May 2026 when OmaElu was retired.

## What this is

A personal CLI weekly planner built in Python. Started as a trip planner for a family holiday in Waikoloa, Big Island, Hawaii, and generalised into an ongoing weekly planning tool used before transferring to a paper planner.

The core workflow: draft the week in the terminal, review it, push to Google Calendar for phone access and real-time edits on the go.

---

## Why it was built

The owner wanted a programmable, archivable planning layer between thinking-about-the-week and committing it to a paper planner. Key constraints:

- Family with a toddler (Heiki): recurring weekly themes shape each day
- All weeks kept as structured archive for later data mining
- Google Calendar integration so the plan is accessible on a phone and family members can see it

---

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.7 |
| Terminal UI | `rich` — panels, rules, coloured text |
| Interactive prompts | `questionary` (`<2.0` for Python 3.7 compat) |
| Data storage | JSON files, one per week (`weeks/YYYY-WXX.json`) |
| Calendar sync | Google Calendar API v3 via `google-api-python-client` |
| Auth | OAuth2, `google-auth-oauthlib`, token stored locally |

---

## Architecture

```
plan.py      CLI entry point + all commands
gcal.py      Google Calendar integration (auth, push, pull)
config.json  Global config: weekly themes, GCal settings
weeks/       Append-only archive of week files (YYYY-WXX.json)
archive/     Historical data (original Waikoloa trip itinerary)
credentials/ OAuth token + client secret (gitignored)
```

### Week file format

Each week is a self-contained JSON file keyed by ISO date. Activities carry an optional `gcal_event_id` written back after a push, enabling idempotent re-pushes.

```json
{
  "week": "2026-W17",
  "start": "2026-04-20",
  "end": "2026-04-26",
  "days": {
    "2026-04-20": {
      "activities": [
        {
          "id": "m20a1",
          "time": "09:00",
          "title": "Dry cleaning pickup",
          "notes": "Morning errands run",
          "location": "",
          "tags": ["🧒"],
          "gcal_event_id": "abc123"
        }
      ]
    }
  }
}
```

---

## Google Calendar integration

### Multi-account pull

The owner has three Google accounts:
- `simonhansedasi` — authenticated account (business/tertiary)
- `woses21` — personal account with recurring events
- `vitruviansandwich` — shared account used by wife

`woses21` and `vitruviansandwich` calendars were shared into `simonhansedasi`. The `pull` command queries all three calendar IDs in parallel and deduplicates by event ID. Pulled events are displayed inline with plan activities, sorted by time, labelled by source account.

Push targets the primary calendar of the authenticated account only.

### Timezone handling

Pulled events are converted to `Pacific/Honolulu` (HST, UTC-10, no DST) regardless of the timezone they were created in.

### Idempotent push

On first push, event IDs returned by the API are written back into the week JSON. Subsequent pushes call `events.update()` rather than `events.insert()`.

---

## CLI commands

```
plan show week [YYYY-WXX]   Week view (defaults to current)
plan show next / prev        Navigate weeks
plan show today              Day view
plan show YYYY-MM-DD         Specific day
plan add                     Interactive activity creation
plan edit                    Interactive edit / delete
plan check                   Outstanding ⚠️ items across all weeks
plan auth                    Google OAuth setup
plan whoami                  Show authenticated Google account
plan calendars               List all calendars visible to that account
plan push [YYYY-WXX]         Push week to Google Calendar
plan pull [YYYY-WXX]         Pull GCal events into week JSON and show
```

---

## Notable decisions

**Append-only week archive** — week files are never deleted or overwritten wholesale. Intentional design for future data mining.

**No ORM, no database** — plain JSON files. Small dataset, human-readable, trivially diffable in git.

**`questionary<2.0` pin** — `questionary` 2.0 dropped Python 3.7 support. Pinned to `>=1.10,<2.0`.

**Location / Maps** — activities have an optional `location` field. Renders as a clickable 📍 Google Maps link. Included in GCal push and captured on pull.

**Pull writes to JSON** — `plan pull` writes GCal events as activities with `"gcal_source": true`. Appears in magenta with 📅 marker. Pull is idempotent. `push` skips `gcal_source` activities.

---

## Changelog

**2026-04-20 — Nap windows removed**
- `config["nap"]` removed from config.json
- `nap_for()`, `_edit_nap()`, `cmd_nap()` removed from plan.py
- `plan nap` command removed
- Nap injection removed from `cmd_show_week`, `cmd_show_day`, `cmd_edit`
- `gcal.py` `push_week()` no longer pushes nap events; `pushed_event_ids()` no longer tracks `gcal_nap_event_id`
- Day objects are now just `{"activities": [...]}` — no `nap_override` field
- Existing week files may still have `nap_override` keys — safely ignored

---

## Owner profile

Geophysicist. Family of three with a toddler (Heiki). Weekly themes: Mission Monday, Library Tuesday, Crafting Wednesday, Café Thursday, Adventure Friday, Relief & Planning (Sat/Sun). The planner is a personal productivity tool, not production software.
