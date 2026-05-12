"""Google Calendar integration for the weekly planner."""

from __future__ import annotations

from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Optional, Dict

from rich.console import Console

ROOT        = Path(__file__).parent
CREDS_DIR   = ROOT / "credentials"
TOKEN_FILE  = CREDS_DIR / "token.json"
SECRET_FILE = CREDS_DIR / "client_secret.json"
SCOPES      = ["https://www.googleapis.com/auth/calendar"]

console = Console()


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_credentials():
    """Return valid OAuth2 credentials, running the auth flow if needed."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not SECRET_FILE.exists():
                console.print(
                    "[red]credentials/client_secret.json not found.[/red]\n"
                    "Run [cyan]plan auth[/cyan] for setup instructions."
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        CREDS_DIR.mkdir(exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


def get_service():
    """Return an authenticated Google Calendar API service, or None."""
    from googleapiclient.discovery import build
    creds = get_credentials()
    if creds is None:
        return None
    return build("calendar", "v3", credentials=creds)


def is_authenticated() -> bool:
    return TOKEN_FILE.exists()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _time_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m

def _minutes_diff(start: str, end: str) -> int:
    return _time_to_minutes(end) - _time_to_minutes(start)

def _build_event_body(title: str, notes: str, tags: List[str],
                      date_str: str, start_time: str, duration_min: int,
                      timezone: str, location: str = "") -> dict:
    start_dt = datetime.strptime(f"{date_str}T{start_time}:00", "%Y-%m-%dT%H:%M:%S")
    end_dt   = start_dt + timedelta(minutes=duration_min)

    tag_str     = " ".join(tags)
    description = f"{notes}\n\n{tag_str}".strip() if tag_str else notes

    body = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": timezone},
    }
    if location:
        body["location"] = location
    return body

def _upsert_event(service, calendar_id: str, event_id: Optional[str],
                  body: dict) -> str:
    """Create or update an event. Returns the event ID."""
    from googleapiclient.errors import HttpError
    if event_id:
        try:
            service.events().update(
                calendarId=calendar_id, eventId=event_id, body=body
            ).execute()
            return event_id
        except HttpError as e:
            if e.resp.status != 404:
                raise
            # Deleted on GCal side — fall through to create
    result = service.events().insert(calendarId=calendar_id, body=body).execute()
    return result["id"]


# ── Push ──────────────────────────────────────────────────────────────────────

def push_week(week_data: dict, config: dict) -> dict:
    """
    Push all activities to Google Calendar.
    Stores gcal_event_id back into each activity for future updates.
    Returns the mutated week_data.
    """
    service = get_service()
    if service is None:
        return week_data

    cal_id  = config.get("gcal_calendar_id", "primary")
    tz      = config.get("timezone", "Pacific/Honolulu")
    created = updated = 0

    for date_str, day_data in week_data.get("days", {}).items():
        for act in day_data.get("activities", []):
            if act.get("gcal_source"):
                continue  # imported from GCal — don't push back
            duration = act.get("duration_min", 60)
            body = _build_event_body(
                title=act["title"],
                notes=act.get("notes", ""),
                tags=act.get("tags", []),
                date_str=date_str,
                start_time=act["time"],
                duration_min=duration,
                timezone=tz,
                location=act.get("location", ""),
            )
            old_id = act.get("gcal_event_id")
            new_id = _upsert_event(service, cal_id, old_id, body)
            act["gcal_event_id"] = new_id
            if old_id:
                updated += 1
            else:
                created += 1

    console.print(f"[green]✓  {created} events created, {updated} updated.[/green]")
    return week_data


# ── Pull ──────────────────────────────────────────────────────────────────────

def pull_gcal_events(dates: List[date], config: dict) -> List[Dict]:
    """
    Fetch all Google Calendar events for a list of dates across all configured calendars.
    Returns a list of normalised dicts ready for display.
    """
    from googleapiclient.errors import HttpError

    service = get_service()
    if service is None:
        return []

    cal_ids  = config.get("gcal_pull_calendar_ids", [config.get("gcal_calendar_id", "primary")])
    time_min = f"{dates[0].isoformat()}T00:00:00Z"
    time_max = f"{dates[-1].isoformat()}T23:59:59Z"

    normalised = []
    seen_ids   = set()  # deduplicate across calendars

    for cal_id in cal_ids:
        try:
            result = service.events().list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
        except HttpError as e:
            console.print(f"[yellow]Could not fetch {cal_id}: {e}[/yellow]")
            continue

        for ev in result.get("items", []):
            if ev["id"] in seen_ids:
                continue
            seen_ids.add(ev["id"])

            start = ev.get("start", {})

            # All-day event
            if "date" in start:
                normalised.append({
                    "gcal_id":  ev["id"],
                    "calendar": cal_id,
                    "date":     start["date"],
                    "time":     None,
                    "title":    ev.get("summary", "(no title)"),
                    "notes":    ev.get("description", ""),
                    "location": ev.get("location", ""),
                    "all_day":  True,
                })
                continue

            # Timed event — convert to configured timezone
            start_str = start.get("dateTime", "")
            try:
                import pytz
                dt = datetime.fromisoformat(start_str)
                if dt.tzinfo is not None:
                    tz_local = pytz.timezone(config.get("timezone", "Pacific/Honolulu"))
                    dt = dt.astimezone(tz_local)
                event_date = dt.date().isoformat()
                event_time = dt.strftime("%H:%M")
            except (ValueError, Exception):
                continue

            normalised.append({
                "gcal_id":  ev["id"],
                "calendar": cal_id,
                "date":     event_date,
                "time":     event_time,
                "title":    ev.get("summary", "(no title)"),
                "notes":    ev.get("description", ""),
                "location": ev.get("location", ""),
                "all_day":  False,
            })

    return normalised


def whoami() -> Optional[str]:
    """Return the email address of the authenticated Google account."""
    service = get_service()
    if service is None:
        return None
    cal = service.calendars().get(calendarId="primary").execute()
    return cal.get("id")


def list_calendars() -> List[Dict]:
    """Return all calendars visible to the authenticated account."""
    from googleapiclient.errors import HttpError
    service = get_service()
    if service is None:
        return []
    try:
        result = service.calendarList().list().execute()
        return result.get("items", [])
    except HttpError as e:
        console.print(f"[red]Error listing calendars: {e}[/red]")
        return []


def pushed_event_ids(week_data: dict) -> set:
    """Return all gcal event IDs already pushed from this week (to avoid duplicates in pull view)."""
    ids = set()
    for day_data in week_data.get("days", {}).values():
        for act in day_data.get("activities", []):
            if act.get("gcal_event_id"):
                ids.add(act["gcal_event_id"])
    return ids
