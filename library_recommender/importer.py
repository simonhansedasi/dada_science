"""
Flexible CSV importer.
Detects known fields from common library export column names and maps them
to the internal schema. Unknown columns are stored as JSON in 'subject'.
"""

import pandas as pd
import json
from db import upsert_book
from rich.console import Console
from rich.table import Table

console = Console()

# Map of internal field -> list of possible CSV column names (case-insensitive)
FIELD_MAP = {
    "title": ["title", "book title", "name", "item title", "bib title"],
    "author": ["author", "author name", "creator", "by", "writer"],
    "description": ["description", "summary", "synopsis", "abstract", "notes", "annotation"],
    "isbn": ["isbn", "isbn13", "isbn10", "isbn-13", "isbn-10"],
    "age_range": ["age range", "age", "reading level", "level", "grade", "audience"],
    "genre": ["genre", "category", "type", "format"],
    "subject": ["subject", "subjects", "topic", "topics", "tags", "keywords"],
    "library_checkout_count": [
        "checkout count", "checkouts", "total checkouts", "circ count",
        "circulation count", "holds", "total holds", "times checked out",
        "checkout_count", "circs"
    ],
    "last_library_checkout": [
        "last checkout", "last checked out", "last circ", "last circulation date",
        "most recent checkout", "last activity"
    ],
}


def detect_columns(df: pd.DataFrame) -> dict:
    """Return mapping of internal_field -> actual_csv_column."""
    col_lower = {c.lower().strip(): c for c in df.columns}
    mapping = {}
    unmapped = list(df.columns)

    for field, candidates in FIELD_MAP.items():
        for candidate in candidates:
            if candidate in col_lower:
                mapping[field] = col_lower[candidate]
                if col_lower[candidate] in unmapped:
                    unmapped.remove(col_lower[candidate])
                break

    return mapping, unmapped


def import_csv(path: str, dry_run: bool = False) -> int:
    df = pd.read_csv(path, dtype=str).fillna("")

    mapping, extra_cols = detect_columns(df)

    if "title" not in mapping:
        console.print("[red]Error:[/red] Could not find a 'title' column. "
                      "Please check your CSV headers.")
        console.print(f"Detected columns: {list(df.columns)}")
        return 0

    # Show detected mapping
    table = Table(title="Detected Column Mapping", show_header=True)
    table.add_column("Internal Field", style="cyan")
    table.add_column("CSV Column", style="green")
    for field, col in mapping.items():
        table.add_row(field, col)
    if extra_cols:
        table.add_row("[yellow]extra (ignored)[/yellow]", ", ".join(extra_cols))
    console.print(table)

    if dry_run:
        console.print(f"\n[yellow]Dry run:[/yellow] Would import {len(df)} rows.")
        return 0

    imported = 0
    errors = 0
    for _, row in df.iterrows():
        book = {}
        for field, col in mapping.items():
            val = row.get(col, "").strip()
            if val:
                book[field] = val

        if not book.get("title"):
            continue

        # Normalize checkout count to int
        if "library_checkout_count" in book:
            try:
                book["library_checkout_count"] = int(
                    str(book["library_checkout_count"]).replace(",", "").split(".")[0]
                )
            except ValueError:
                del book["library_checkout_count"]

        # Store extra columns as supplemental subject info
        if extra_cols:
            extras = {c: row.get(c, "") for c in extra_cols if row.get(c, "").strip()}
            if extras:
                existing = book.get("subject", "")
                extra_str = "; ".join(f"{k}: {v}" for k, v in extras.items())
                book["subject"] = f"{existing}; {extra_str}".strip("; ") if existing else extra_str

        try:
            upsert_book(book)
            imported += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                console.print(f"[red]Error on row {imported + errors}:[/red] {e}")

    console.print(f"\n[green]Imported {imported} books.[/green]"
                  + (f" [red]{errors} errors.[/red]" if errors else ""))
    return imported
