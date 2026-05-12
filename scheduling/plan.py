#!/usr/bin/env python3
"""Weekly Planner CLI — plan your week before it hits the paper."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import questionary
from questionary import Style as QStyle
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

import gcal

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "config.json"
WEEKS_DIR = ROOT / "weeks"
WEEKS_DIR.mkdir(exist_ok=True)

console = Console()

STYLE = QStyle([
    ("qmark",       "fg:#f5a623 bold"),
    ("question",    "bold"),
    ("answer",      "fg:#5bc0eb bold"),
    ("pointer",     "fg:#f5a623 bold"),
    ("highlighted", "fg:#f5a623"),
    ("selected",    "fg:#5bc0eb"),
    ("separator",   "fg:#444444"),
    ("instruction", "fg:#888888 italic"),
])

WEEKDAYS   = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_NAMES  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

TAG_CHOICES = [
    questionary.Choice("🧒  Whole family",      value="🧒"),
    questionary.Choice("👫  Adults only",        value="👫"),
    questionary.Choice("🌋  Science/geology",    value="🌋"),
    questionary.Choice("🏛️   Cultural heritage", value="🏛️"),
    questionary.Choice("⚠️   Needs booking",     value="⚠️"),
]


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_config(config: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ── Week helpers ──────────────────────────────────────────────────────────────

def week_id(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"

def week_start(wid: str) -> date:
    """ISO week id → Monday date."""
    year_s, w_s = wid.split("-W")
    year, w = int(year_s), int(w_s)
    jan4 = date(year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    return week1_monday + timedelta(weeks=w - 1)

def week_dates(wid: str) -> List[date]:
    start = week_start(wid)
    return [start + timedelta(days=i) for i in range(7)]

def load_week(wid: str) -> dict:
    f = WEEKS_DIR / f"{wid}.json"
    if f.exists():
        with open(f) as fp:
            return json.load(fp)
    start = week_start(wid)
    return {
        "week":  wid,
        "start": start.isoformat(),
        "end":   (start + timedelta(days=6)).isoformat(),
        "days":  {},
    }

def save_week(wid: str, data: dict):
    with open(WEEKS_DIR / f"{wid}.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_day(week_data: dict, d: date) -> dict:
    return week_data["days"].get(d.isoformat(), {"activities": []})

def set_day(week_data: dict, d: date, day_data: dict):
    week_data["days"][d.isoformat()] = day_data


# ── Time helpers ──────────────────────────────────────────────────────────────

def fmt_time(t: str) -> str:
    """'14:30' → '2:30pm'"""
    try:
        h, m = map(int, t.split(":"))
        suffix = "am" if h < 12 else "pm"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d}{suffix}"
    except Exception:
        return t

def fmt_range(start: str, end: str) -> str:
    return f"{fmt_time(start)}–{fmt_time(end)}"

def time_minutes(t: str) -> int:
    try:
        h, m = map(int, t.split(":"))
        return h * 60 + m
    except Exception:
        return 9999

def validate_time(t: str) -> bool:
    try:
        parts = t.strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59 and len(parts) == 2
    except Exception:
        return False

def _maps_url(location: str) -> str:
    return f"https://maps.google.com/?q={quote_plus(location)}"


def sorted_acts(activities: List[dict]) -> List[dict]:
    return sorted(activities, key=lambda a: time_minutes(a.get("time", "99:99")))

# ── Display ───────────────────────────────────────────────────────────────────

def print_act_row(act: dict, dim: bool = False):
    is_gcal = act.get("gcal_source", False)
    tags    = " ".join(act.get("tags", []))

    if is_gcal and act.get("all_day"):
        display_time = "all day"
    else:
        t_start = act.get("time", "")
        t_end   = act.get("end", "")
        if t_start and t_end:
            display_time = fmt_range(t_start, t_end)
        elif t_start:
            display_time = fmt_time(t_start)
        else:
            display_time = ""

    row  = Text()
    base = "dim" if dim else ""

    if is_gcal:
        cal_id    = act.get("calendar", "")
        cal_label = cal_id.split("@")[0] if "@" in cal_id else cal_id
        row.append(f"  {display_time:<14}", style=f"magenta {base}".strip())
        row.append(" 📅  ", style=base)
        row.append(act["title"], style=f"magenta {base}".strip())
        row.append(f"  [{cal_label}]", style=f"dim {base}".strip())
    else:
        row.append(f"  {display_time:<14}", style=f"cyan {base}".strip())
        row.append(f" {tags:<6}  ", style=base)
        row.append(act["title"], style=f"bold {base}".strip())
        if act.get("notes"):
            row.append(f"  {act['notes']}", style=f"dim {base}".strip())

    console.print(row)

    location = act.get("location", "").strip()
    if location:
        url      = _maps_url(location)
        loc_text = Text()
        loc_text.append("  " + " " * 22, style=base)
        loc_text.append(f"📍 ", style=base)
        loc_text.append(location, style=f"link {url} {'dim' if dim else 'blue'}".strip())
        console.print(loc_text)


def cmd_show_week(args: List[str]):
    config = load_config()

    if args:
        raw = args[0]
        if "-W" in raw:
            wid = raw
        else:
            try:
                wid = week_id(datetime.strptime(raw, "%Y-%m-%d").date())
            except ValueError:
                console.print(f"[red]Expected YYYY-WXX or YYYY-MM-DD, got: {raw}[/red]")
                sys.exit(1)
    else:
        wid = week_id(date.today())

    week_data = load_week(wid)
    today     = date.today()
    dates     = week_dates(wid)
    s, e      = dates[0].strftime("%b %d"), dates[6].strftime("%b %d, %Y")

    console.print()
    console.print(Panel(
        f"[bold]{wid}[/bold]   [dim]{s} – {e}[/dim]",
        title="[bold yellow]📅 Weekly Planner[/bold yellow]",
        border_style="yellow",
    ))

    for d in dates:
        is_today = d == today
        is_past  = d < today
        day_name = WEEKDAYS[d.weekday()]
        theme    = config["themes"].get(day_name, "")

        label     = f"{DAY_NAMES[d.weekday()]} {d.strftime('%b %d')}"
        theme_str = f" — {theme}" if theme else ""
        marker    = " ◀ TODAY" if is_today else ""

        rule_style  = "yellow" if is_today else ("dim" if is_past else "blue")
        label_style = "bold yellow" if is_today else ("dim" if is_past else "bold white")

        console.print()
        console.print(Rule(
            title=f"[{label_style}]{label}{theme_str}{marker}[/{label_style}]",
            style=rule_style,
        ))

        day_data   = get_day(week_data, d)
        activities = sorted_acts(day_data.get("activities", []))

        if not activities and not is_past:
            console.print("  [dim italic]No activities — run [cyan]plan add[/cyan][/dim italic]")
        else:
            for act in activities:
                print_act_row(act, dim=is_past)

    console.print()


def cmd_show_day(target: str):
    config = load_config()

    if target.lower() == "today":
        d = date.today()
    else:
        try:
            d = datetime.strptime(target, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Invalid date: {target}. Use YYYY-MM-DD or 'today'.[/red]")
            sys.exit(1)

    wid      = week_id(d)
    week_data = load_week(wid)
    day_data  = get_day(week_data, d)
    day_name  = WEEKDAYS[d.weekday()]
    theme     = config["themes"].get(day_name, "")

    console.print()
    console.print(Panel(
        f"[bold]{theme}[/bold]" if theme else "",
        title=f"[bold yellow]{DAY_NAMES[d.weekday()]} {d.strftime('%b %d, %Y')}[/bold yellow]",
        border_style="yellow",
    ))

    activities = sorted_acts(day_data.get("activities", []))

    for act in activities:
        tags = " ".join(act.get("tags", []))
        t_start, t_end = act.get("time", ""), act.get("end", "")
        display_time = fmt_range(t_start, t_end) if t_end else fmt_time(t_start)

        body = Text()
        if act.get("notes"):
            body.append(act["notes"], style="dim")
        else:
            body.append("no notes", style="dim italic")
        location = act.get("location", "").strip()
        if location:
            url = _maps_url(location)
            body.append("\n📍 ", style="")
            body.append(location, style=f"link {url} blue")

        console.print()
        console.print(Panel(
            body,
            title=f"[cyan]{display_time}[/cyan]  {tags}  [bold white]{act['title']}[/bold white]",
            border_style="blue",
            padding=(0, 1),
        ))

    console.print()


# ── Interactive helpers ───────────────────────────────────────────────────────

def pick_day(wid: str, config: dict, prompt: str = "Which day?") -> Optional[date]:
    choices = []
    for d in week_dates(wid):
        day_name = WEEKDAYS[d.weekday()]
        theme    = config["themes"].get(day_name, "")
        label    = f"{DAY_NAMES[d.weekday()]} {d.strftime('%b %d')}  {theme}"
        choices.append(questionary.Choice(label, value=d))
    choices.append(questionary.Choice("↩  Cancel", value=None))
    return questionary.select(prompt, choices=choices, style=STYLE).ask()

def ask_time(prompt: str, default: str = "") -> Optional[str]:
    kwargs = {"default": default} if default else {}
    return questionary.text(
        prompt,
        validate=lambda t: validate_time(t) or "Enter time as HH:MM (24h), e.g. 09:30",
        style=STYLE,
        **kwargs,
    ).ask()

def ask_tags(current: Optional[List[str]] = None) -> Optional[List[str]]:
    current = current or []
    choices = [
        questionary.Choice("🧒  Whole family",      value="🧒",  checked="🧒"  in current),
        questionary.Choice("👫  Adults only",        value="👫",  checked="👫"  in current),
        questionary.Choice("🌋  Science/geology",    value="🌋",  checked="🌋"  in current),
        questionary.Choice("🏛️   Cultural heritage", value="🏛️", checked="🏛️" in current),
        questionary.Choice("⚠️   Needs booking",     value="⚠️", checked="⚠️" in current),
    ]
    return questionary.checkbox("Tags (space to toggle):", choices=choices, style=STYLE).ask()


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_add(args: List[str]):
    config = load_config()

    if args and "-W" in args[0]:
        wid = args[0]
    else:
        wid = week_id(date.today())

    console.print()
    console.print(f"[bold yellow]➕  Add activity[/bold yellow]  [dim]{wid}[/dim]\n")

    d = pick_day(wid, config)
    if d is None:
        return

    time_str = ask_time("Time (HH:MM, 24h):")
    if time_str is None:
        return

    title = questionary.text("Title:", style=STYLE).ask()
    if not title or not title.strip():
        return

    notes    = questionary.text("Notes (optional — press Enter to skip):", style=STYLE).ask()
    location = questionary.text("Location (optional — press Enter to skip):", style=STYLE).ask()

    tags = ask_tags()
    if tags is None:
        return

    activity = {
        "id":       str(uuid.uuid4())[:8],
        "time":     time_str.strip(),
        "title":    title.strip(),
        "notes":    (notes or "").strip(),
        "location": (location or "").strip(),
        "tags":     tags,
    }

    console.print()
    console.print(Panel(
        f"[dim]{activity['notes'] or 'no notes'}[/dim]",
        title=(
            f"[cyan]{fmt_time(activity['time'])}[/cyan]  "
            f"{' '.join(tags)}  [bold]{activity['title']}[/bold]"
        ),
        title_align="left",
        border_style="blue",
        padding=(0, 1),
    ))

    if not questionary.confirm("Add this activity?", default=True, style=STYLE).ask():
        console.print("[dim]Cancelled.[/dim]")
        return

    week_data = load_week(wid)
    day_data  = get_day(week_data, d)
    day_data.setdefault("activities", []).append(activity)
    set_day(week_data, d, day_data)
    save_week(wid, week_data)

    console.print(f"[green]✓  Added to {DAY_NAMES[d.weekday()]} {d.strftime('%b %d')}.[/green]")


def cmd_edit(args: List[str]):
    config = load_config()

    if args and "-W" in args[0]:
        wid = args[0]
    else:
        wid = week_id(date.today())

    console.print()
    console.print(f"[bold yellow]✏️   Edit / delete[/bold yellow]  [dim]{wid}[/dim]\n")

    d = pick_day(wid, config)
    if d is None:
        return

    week_data  = load_week(wid)
    day_data   = get_day(week_data, d)
    activities = day_data.get("activities", [])

    act_choices = []
    for act in sorted_acts(activities):
        t_str = fmt_time(act["time"])
        label = f"{t_str:<10} {' '.join(act.get('tags', [])):<8} {act['title']}"
        act_choices.append(questionary.Choice(label, value=act["id"]))
    act_choices.append(questionary.Choice("↩  Cancel", value=None))

    act_id = questionary.select(
        f"Which activity on {DAY_NAMES[d.weekday()]} {d.strftime('%b %d')}?",
        choices=act_choices,
        style=STYLE,
    ).ask()

    if act_id is None:
        return

    act = next((a for a in activities if a["id"] == act_id), None)
    if act is None:
        return

    action = questionary.select(
        f"'{act['title']}':",
        choices=["Edit fields", "Delete", "↩  Cancel"],
        style=STYLE,
    ).ask()

    if action == "Delete":
        if questionary.confirm(f"Delete '{act['title']}'?", default=False, style=STYLE).ask():
            day_data["activities"] = [a for a in activities if a["id"] != act_id]
            set_day(week_data, d, day_data)
            save_week(wid, week_data)
            console.print(f"[green]✓  Deleted '{act['title']}'.[/green]")
        return

    if action != "Edit fields":
        return

    new_time = ask_time("Time (HH:MM):", default=act["time"])
    if new_time is None:
        return

    new_title = questionary.text("Title:", default=act["title"], style=STYLE).ask()
    if new_title is None:
        return

    new_notes = questionary.text(
        "Notes:", default=act.get("notes", ""), style=STYLE
    ).ask()

    new_location = questionary.text(
        "Location:", default=act.get("location", ""), style=STYLE
    ).ask()

    new_tags = ask_tags(current=act.get("tags", []))
    if new_tags is None:
        return

    act["time"]     = new_time.strip()
    act["title"]    = new_title.strip()
    act["notes"]    = (new_notes or "").strip()
    act["location"] = (new_location or "").strip()
    act["tags"]     = new_tags

    set_day(week_data, d, day_data)
    save_week(wid, week_data)
    console.print(f"[green]✓  Updated '{act['title']}'.[/green]")


def cmd_check():
    console.print()
    console.print("[bold yellow]🔍  Outstanding — needs booking[/bold yellow]\n")

    today    = date.today()
    found    = []
    week_files = sorted(WEEKS_DIR.glob("*.json"))

    for wf in week_files:
        with open(wf) as f:
            data = json.load(f)
        for date_str, day_data in data.get("days", {}).items():
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            for act in day_data.get("activities", []):
                if "⚠️" in act.get("tags", []):
                    found.append((d, act))

    if not found:
        console.print("[green]Nothing outstanding.[/green]\n")
        return

    found.sort(key=lambda x: x[0])
    for d, act in found:
        days_away = (d - today).days
        if days_away < 0:
            when = f"[dim]{abs(days_away)}d ago[/dim]"
        elif days_away == 0:
            when = "[red bold]TODAY[/red bold]"
        else:
            when = f"in {days_away}d"

        label = f"{DAY_NAMES[d.weekday()]} {d.strftime('%b %d')}"
        other_tags = " ".join(t for t in act.get("tags", []) if t != "⚠️")
        console.print(
            f"  [red]⚠️[/red]  [bold]{act['title']}[/bold]"
            f"  {other_tags}  [dim]{label}[/dim]  ({when})"
        )
        if act.get("notes"):
            console.print(f"      [dim]{act['notes']}[/dim]")

    console.print()


# ── Google Calendar commands ──────────────────────────────────────────────────

def cmd_whoami():
    account = gcal.whoami()
    if account:
        console.print(f"\n[bold]Authenticated as:[/bold] [cyan]{account}[/cyan]\n")
    else:
        console.print("\n[yellow]Not authenticated. Run [cyan]plan auth[/cyan].[/yellow]\n")


def cmd_calendars():
    calendars = gcal.list_calendars()
    if not calendars:
        console.print("\n[yellow]No calendars found or not authenticated.[/yellow]\n")
        return

    account = gcal.whoami()
    console.print()
    console.print(Panel(
        f"[dim]Authenticated as [cyan]{account}[/cyan][/dim]",
        title="[bold yellow]📅 Available Calendars[/bold yellow]",
        border_style="yellow",
    ))
    console.print()

    for cal in sorted(calendars, key=lambda c: (c.get("primary") is None, c.get("summaryOverride", c.get("summary", "")))):
        cal_id      = cal.get("id", "")
        summary     = cal.get("summaryOverride") or cal.get("summary", "")
        primary     = cal.get("primary", False)
        access      = cal.get("accessRole", "")
        color       = cal.get("backgroundColor", "")
        primary_tag = " [green][primary][/green]" if primary else ""
        owner_tag   = " [dim][read-only][/dim]" if access == "reader" else ""

        console.print(f"  [bold]{summary}[/bold]{primary_tag}{owner_tag}")
        console.print(f"  [dim]{cal_id}[/dim]\n")

    console.print(
        "[dim]To pull from a calendar, add its ID to [cyan]config.json[/cyan] "
        "under [cyan]gcal_calendar_ids[/cyan].[/dim]\n"
    )


def cmd_auth():
    console.print()
    console.print(Panel(
        "[bold]Google Calendar Setup[/bold]\n\n"
        "1. Go to [cyan]https://console.cloud.google.com[/cyan]\n"
        "2. Create a project (or select an existing one)\n"
        "3. Enable the [bold]Google Calendar API[/bold]\n"
        "   APIs & Services → Enable APIs → search 'Google Calendar API'\n"
        "4. Create OAuth credentials\n"
        "   APIs & Services → Credentials → Create → OAuth client ID → Desktop app\n"
        "5. Download the JSON file and save it as:\n"
        "   [cyan]credentials/client_secret.json[/cyan]\n"
        "6. Re-run [cyan]plan auth[/cyan] to complete sign-in\n",
        title="[bold yellow]🔑 Google Calendar Auth[/bold yellow]",
        border_style="yellow",
    ))

    secret = gcal.SECRET_FILE
    if not secret.exists():
        console.print("[dim]Waiting for credentials/client_secret.json ...[/dim]")
        return

    console.print("[dim]Opening browser for Google sign-in...[/dim]\n")
    creds = gcal.get_credentials()
    if creds:
        console.print("[green]✓  Authenticated. token.json saved.[/green]")


def cmd_push(args: List[str]):
    config = load_config()

    if args and "-W" in args[0]:
        wid = args[0]
    elif args and args[0] == "next":
        wid = week_id(date.today() + timedelta(weeks=1))
    elif args and args[0] in ("prev", "last"):
        wid = week_id(date.today() - timedelta(weeks=1))
    else:
        wid = week_id(date.today())

    console.print(f"\n[bold yellow]⬆  Pushing {wid} to Google Calendar[/bold yellow]\n")

    week_data = load_week(wid)
    if not week_data.get("days"):
        console.print("[dim]No activities to push.[/dim]")
        return

    week_data = gcal.push_week(week_data, config)
    save_week(wid, week_data)


def _imported_gcal_ids(week_data: dict) -> set:
    """Return gcal_ids of events already imported into the week JSON."""
    ids = set()
    for day_data in week_data.get("days", {}).values():
        for act in day_data.get("activities", []):
            if act.get("gcal_source") and act.get("gcal_id"):
                ids.add(act["gcal_id"])
    return ids


def cmd_pull(args: List[str]):
    config = load_config()

    if args and "-W" in args[0]:
        wid = args[0]
    elif args and args[0] == "next":
        wid = week_id(date.today() + timedelta(weeks=1))
    elif args and args[0] in ("prev", "last"):
        wid = week_id(date.today() - timedelta(weeks=1))
    else:
        wid = week_id(date.today())

    dates     = week_dates(wid)
    week_data = load_week(wid)

    # Fetch GCal events, skipping ones already in the JSON
    gcal_events  = gcal.pull_gcal_events(dates, config)
    skip_ids     = gcal.pushed_event_ids(week_data) | _imported_gcal_ids(week_data)

    new_count = 0
    for ev in gcal_events:
        if ev["gcal_id"] in skip_ids:
            continue
        d_str = ev["date"]
        if d_str not in week_data["days"]:
            week_data["days"][d_str] = {"activities": []}
        week_data["days"][d_str]["activities"].append({
            "id":          str(uuid.uuid4())[:8],
            "time":        ev["time"] or "00:00",
            "title":       ev["title"],
            "notes":       ev.get("notes", ""),
            "location":    ev.get("location", ""),
            "tags":        [],
            "gcal_source": True,
            "gcal_id":     ev["gcal_id"],
            "calendar":    ev.get("calendar", ""),
            "all_day":     ev.get("all_day", False),
        })
        new_count += 1

    if new_count:
        save_week(wid, week_data)
        console.print(f"\n[green]✓  {new_count} event(s) pulled from Google Calendar.[/green]")
    else:
        console.print("\n[dim]No new events to pull.[/dim]")

    cmd_show_week([wid])


# ── Entry point ───────────────────────────────────────────────────────────────

def usage():
    console.print(Panel(
        "[bold]Commands:[/bold]\n\n"
        "  [cyan]plan show week[/cyan]              Current week at a glance\n"
        "  [cyan]plan show next[/cyan]              Next week\n"
        "  [cyan]plan show prev[/cyan]              Previous week\n"
        "  [cyan]plan show week YYYY-WXX[/cyan]     A specific week, e.g. 2026-W14\n"
        "  [cyan]plan show today[/cyan]             Today's schedule\n"
        "  [cyan]plan show YYYY-MM-DD[/cyan]        A specific day\n"
        "  [cyan]plan add[/cyan]                    Add an activity (interactive)\n"
        "  [cyan]plan edit[/cyan]                   Edit or delete an activity (interactive)\n"
        "  [cyan]plan check[/cyan]                  All ⚠️ items needing a booking\n\n"
        "  [bold]Google Calendar[/bold]\n"
        "  [cyan]plan auth[/cyan]                   Set up Google Calendar integration\n"
        "  [cyan]plan whoami[/cyan]                 Show which Google account is authenticated\n"
        "  [cyan]plan calendars[/cyan]              List all calendars visible to that account\n"
        "  [cyan]plan push [YYYY-WXX][/cyan]        Push week activities to Google Calendar\n"
        "  [cyan]plan pull [YYYY-WXX][/cyan]        Pull Google Calendar events into the week JSON and show\n",
        title="[bold yellow]📅 Weekly Planner[/bold yellow]",
        border_style="yellow",
    ))


def main():
    args = sys.argv[1:]

    if not args:
        usage()
        return

    cmd = args[0].lower()

    if cmd == "show":
        if len(args) < 2:
            usage()
            return
        sub = args[1].lower()
        if sub == "week":
            cmd_show_week(args[2:])
        elif sub in ("next", "next week"):
            cmd_show_week([week_id(date.today() + timedelta(weeks=1))])
        elif sub in ("prev", "last", "prev week", "last week"):
            cmd_show_week([week_id(date.today() - timedelta(weeks=1))])
        elif sub == "today":
            cmd_show_day("today")
        else:
            cmd_show_day(args[1])

    elif cmd == "add":
        cmd_add(args[1:])

    elif cmd == "edit":
        cmd_edit(args[1:])

    elif cmd == "check":
        cmd_check()

    elif cmd == "auth":
        cmd_auth()

    elif cmd == "whoami":
        cmd_whoami()

    elif cmd == "calendars":
        cmd_calendars()

    elif cmd == "push":
        cmd_push(args[1:])

    elif cmd == "pull":
        cmd_pull(args[1:])

    else:
        console.print(f"[red]Unknown command:[/red] {cmd}")
        usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
