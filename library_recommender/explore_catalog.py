"""
explore_catalog.py — Sno-Isle BiblioCommons catalog explorer

Shows every available filter field, its values, and book counts.
Run with no arguments for a full overview, or pass a filter to drill down.

Usage:
    python explore_catalog.py
    python explore_catalog.py --audience JUVENILE
    python explore_catalog.py --audience JUVENILE --format BK
    python explore_catalog.py --audience JUVENILE --format BK --genre "Juvenile Fiction"
"""

import argparse
import requests
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

BASE_URL = "https://gateway.bibliocommons.com/v2/libraries/sno-isle/bibs/search"

# Human-readable labels for field IDs
FIELD_LABELS = {
    "FORMAT":               "Format",
    "AUDIENCE":             "Audience",
    "FICTION_TYPE":         "Fiction / Nonfiction",
    "GENRE_HEADINGS":       "Genre",
    "TOPIC_HEADINGS":       "Topic (subject headings)",
    "GEO_HEADINGS":         "Geographic focus",
    "TAG_GENRE":            "Community tag: genre",
    "TAG_ABOUT":            "Community tag: about",
    "TAG_TONE":             "Community tag: tone",
    "LANGUAGE":             "Language",
    "PRIMARY_LANGUAGE":     "Primary language",
    "PUBLISHED_DATE":       "Publication year",
    "AUTHOR":               "Author",
    "CIRC":                 "Circulation type",
    "STATUS":               "Availability / branch",
    "UGC_RATING":           "Community rating",
    "TECHNICAL_DIFFICULTY": "Reading level",
    "NEWLY_ACQUIRED":       "Newly acquired",
}

# CLI filter flags -> API param key  (format: f_FIELDID)
FILTER_PARAMS = {
    "format":   "f_FORMAT",
    "audience": "f_AUDIENCE",
    "genre":    "f_GENRE_HEADINGS",
    "topic":    "f_TOPIC_HEADINGS",
    "language": "f_LANGUAGE",
    "fiction":  "f_FICTION_TYPE",
    "circ":     "f_CIRC",
}

SEARCH_TYPES = ["keyword", "title", "author", "subject", "series", "tag"]


def fetch_facets(filters: dict):
    params = {"query": "a", "searchType": "keyword", "limit": 1, "page": 1}
    params.update(filters)
    r = requests.get(BASE_URL, params=params, timeout=15,
                     headers={"User-Agent": "Mozilla/5.0 Chrome/120.0"})
    r.raise_for_status()
    data = r.json()
    cs = data["catalogSearch"]
    total = cs["pagination"]["count"]
    return total, cs["fields"]


def print_overview(filters: dict):
    console.print()
    total, fields = fetch_facets(filters)

    # Header
    if filters:
        active = "  ".join(f"[cyan]{k}[/cyan]=[yellow]{v}[/yellow]"
                           for k, v in filters.items())
        console.print(f"Active filters: {active}")
    console.print(f"Total matching items: [bold green]{total:,}[/bold green]\n")

    for field in fields:
        fid = field["id"]
        label = FIELD_LABELS.get(fid, fid)
        has_more = field["hasMore"]
        values = field["fieldFilters"]

        t = Table(title=f"{label}  [dim](field: {fid})[/dim]",
                  box=box.SIMPLE_HEAVY, show_header=True, min_width=50)
        t.add_column("Value", style="cyan")
        t.add_column("Count", justify="right", style="green")

        for v in values:
            t.add_row(v["value"], f"{v['count']:,}")

        if has_more:
            t.add_row("[dim]… (top 15 shown)[/dim]", "")

        console.print(t)

    # Remind user of available search types and filter flags
    console.rule("How to search")
    st_table = Table(box=box.SIMPLE, show_header=True)
    st_table.add_column("searchType", style="cyan")
    st_table.add_column("Matches on")
    for st in SEARCH_TYPES:
        desc = {
            "keyword": "title, author, subject, description (default)",
            "title":   "title only",
            "author":  "author name",
            "subject": "subject headings",
            "series":  "series name",
            "tag":     "community tags",
        }.get(st, "")
        st_table.add_row(st, desc)
    console.print(st_table)

    console.rule("Filter flags (combine freely)")
    flag_table = Table(box=box.SIMPLE, show_header=True)
    flag_table.add_column("Flag", style="cyan")
    flag_table.add_column("API param")
    flag_table.add_column("Example values")
    examples = {
        "--format":   ("f_FORMAT",           "BK  EBOOK  EAUDIOBOOK  DVD  GRAPHIC_NOVEL"),
        "--audience": ("f_AUDIENCE",         "JUVENILE  adult  teen"),
        "--genre":    ("f_GENRE_HEADINGS",   "\"Juvenile Fiction\"  \"Picture Books\""),
        "--topic":    ("f_TOPIC_HEADINGS",   "Animals  \"Bedtime\"  Dinosaurs"),
        "--language": ("f_LANGUAGE",         "eng  spa  fre"),
        "--fiction":  ("f_FICTION_TYPE",     "FICTION  NONFICTION"),
        "--circ":     ("f_CIRC",             "CIRC  ONLINE  NON_CIRC"),
    }
    for flag, (param, ex) in examples.items():
        flag_table.add_row(flag, param, ex)
    console.print(flag_table)

    console.print("\n[bold]Tip:[/bold] combine filters to scope your scraper:\n"
                  "  python explore_catalog.py --audience JUVENILE --format BK\n"
                  "  python explore_catalog.py --audience JUVENILE --format BK "
                  "--genre \"Picture Books\"\n")


def main():
    parser = argparse.ArgumentParser(description="Explore the Sno-Isle catalog facets")
    parser.add_argument("--format",   help="filter by format (e.g. BK)")
    parser.add_argument("--audience", help="filter by audience (e.g. JUVENILE)")
    parser.add_argument("--genre",    help="filter by genre heading")
    parser.add_argument("--topic",    help="filter by topic heading")
    parser.add_argument("--language", help="filter by language code (e.g. eng)")
    parser.add_argument("--fiction",  help="filter by fiction type (FICTION / NONFICTION)")
    parser.add_argument("--circ",     help="filter by circulation type (CIRC / ONLINE)")
    args = parser.parse_args()

    filters = {}
    for flag, param in FILTER_PARAMS.items():
        val = getattr(args, flag)
        if val:
            filters[param] = val

    print_overview(filters)


if __name__ == "__main__":
    main()
