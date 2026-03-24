#!/usr/bin/env python3
"""
Library Recommender CLI
A recommendation system for toddler library books.
"""

import sys
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

import db
import importer as imp
import recommender as rec

console = Console()


def _book_panel(book: dict, score: float = None, label: str = "") -> Panel:
    lines = []
    if book.get("author"):
        lines.append(f"[dim]by[/dim] {book['author']}")
    if book.get("age_range"):
        lines.append(f"[dim]Age:[/dim] {book['age_range']}")
    if book.get("genre"):
        lines.append(f"[dim]Genre:[/dim] {book['genre']}")
    if book.get("library_checkout_count") is not None:
        lines.append(f"[dim]Library checkouts:[/dim] {book['library_checkout_count']}")
    if book.get("avg_rating"):
        stars = "★" * int(round(book["avg_rating"])) + "☆" * (5 - int(round(book["avg_rating"])))
        lines.append(f"[dim]Your rating:[/dim] [yellow]{stars}[/yellow] ({book['avg_rating']:.1f})")
    if book.get("description"):
        desc = book["description"]
        if len(desc) > 200:
            desc = desc[:197] + "..."
        lines.append(f"\n[italic]{desc}[/italic]")
    if score is not None:
        lines.append(f"\n[dim]Match score: {score:.2f}[/dim]")

    title_text = f"[bold cyan]{book['title']}[/bold cyan]  [dim]#{book['id']}[/dim]"
    if label:
        title_text = f"{label}  {title_text}"

    return Panel(
        "\n".join(lines) if lines else "[dim]No details available.[/dim]",
        title=title_text,
        border_style="blue",
        padding=(0, 1),
    )


@click.group()
def cli():
    """📚 Library Recommender — find great books for your little one."""
    db.init_db()


@cli.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview column mapping without importing.")
def import_csv(csv_path, dry_run):
    """Import library inventory from a CSV file."""
    console.print(f"\n[bold]Importing:[/bold] {csv_path}\n")
    imp.import_csv(csv_path, dry_run=dry_run)


@cli.command()
def recommend():
    """Get 10 book recommendations (5 top, 2 experimental, 3 hidden gems)."""
    result, err = rec.recommend()
    if err:
        console.print(f"[red]{err}[/red]")
        sys.exit(1)

    if result["has_profile"]:
        console.print(
            f"\n[dim]Profile built from {result['liked_count']} highly-rated book(s).[/dim]\n"
        )
    else:
        console.print(
            "\n[dim]No ratings yet — recommendations based on library popularity.[/dim]\n"
            "[dim]Check out some books and rate them to personalize results![/dim]\n"
        )

    console.print(Panel(
        "[bold green]★ TOP 5 MATCHES[/bold green]\n"
        "Best fit based on what you've loved + library popularity.",
        border_style="green", box=box.ROUNDED
    ))
    for i, (book, score) in enumerate(result["top"], 1):
        console.print(_book_panel(book, score, label=f"[green]{i}.[/green]"))

    console.print("\n")
    console.print(Panel(
        "[bold magenta]🔬 2 EXPERIMENTAL[/bold magenta]\n"
        "Similar to your favorites but rarely checked out — hidden potential.",
        border_style="magenta", box=box.ROUNDED
    ))
    for i, (book, score) in enumerate(result["experimental"], 1):
        console.print(_book_panel(book, score, label=f"[magenta]{i}.[/magenta]"))

    console.print("\n")
    console.print(Panel(
        "[bold yellow]🌱 3 HIDDEN GEMS[/bold yellow]\n"
        "Least checked-out books in the library — pure discovery.",
        border_style="yellow", box=box.ROUNDED
    ))
    for i, book in enumerate(result["bottom"], 1):
        console.print(_book_panel(book, label=f"[yellow]{i}.[/yellow]"))

    console.print(
        "\n[dim]To check out a book: [bold]library checkout <id>[/bold][/dim]"
        "\n[dim]To rate books:        [bold]library rate[/bold][/dim]\n"
    )


@cli.command()
@click.argument("book_id", type=int)
def checkout(book_id):
    """Mark a book as checked out by its ID."""
    book = db.get_book(book_id)
    if not book:
        console.print(f"[red]Book #{book_id} not found.[/red]")
        sys.exit(1)
    db.add_checkout(book_id)
    console.print(f"\n[green]Checked out:[/green] [bold]{book['title']}[/bold]\n"
                  f"Rate it when you return it with [bold]library rate[/bold].\n")


@cli.command()
def rate():
    """Prompt to rate all currently checked-out unrated books."""
    pending = db.get_checked_out_unrated()
    if not pending:
        console.print("\n[dim]No books pending rating. Check some out first![/dim]\n")
        return

    console.print(f"\n[bold]Rate {len(pending)} checked-out book(s)[/bold] "
                  f"[dim](1=no interest, 5=totally engaged)[/dim]\n")

    for item in pending:
        console.print(f"  [bold cyan]{item['title']}[/bold cyan]"
                      + (f"  [dim]by {item['author']}[/dim]" if item.get("author") else ""))
        while True:
            raw = click.prompt(
                "  Rating (1-5, or s to skip)",
                default="s",
                show_default=True,
            )
            if raw.strip().lower() == "s":
                break
            try:
                rating = float(raw)
                if 1.0 <= rating <= 5.0:
                    db.record_rating(item["checkout_id"], rating)
                    stars = "★" * int(rating) + "☆" * (5 - int(rating))
                    console.print(f"  [yellow]{stars}[/yellow] saved!\n")
                    break
                else:
                    console.print("  [red]Enter a number between 1 and 5.[/red]")
            except ValueError:
                console.print("  [red]Enter a number between 1 and 5, or 's' to skip.[/red]")


@cli.command()
@click.argument("query")
def search(query):
    """Search books by title, author, description, or subject."""
    results = db.search_books(query)
    if not results:
        console.print(f"\n[dim]No results for '{query}'.[/dim]\n")
        return

    table = Table(title=f"Search: '{query}'", show_header=True, box=box.SIMPLE)
    table.add_column("ID", style="dim", width=5)
    table.add_column("Title", style="cyan")
    table.add_column("Author")
    table.add_column("Checkouts", justify="right")
    table.add_column("Rating", justify="center")
    table.add_column("Your #", justify="right")

    for b in results:
        rating = f"{b['avg_rating']:.1f}" if b.get("avg_rating") else "—"
        table.add_row(
            str(b["id"]),
            b["title"],
            b.get("author") or "—",
            str(b.get("library_checkout_count") or "—"),
            rating,
            str(b["times_checked_out"]),
        )
    console.print(table)


@cli.command(name="list")
@click.option("--rated", is_flag=True, help="Show only rated books.")
@click.option("--limit", default=20, show_default=True, help="Max rows to show.")
def list_books(rated, limit):
    """List books in the database."""
    books = db.get_all_books()
    if rated:
        books = [b for b in books if b.get("avg_rating")]

    table = Table(title="Library Catalog", show_header=True, box=box.SIMPLE)
    table.add_column("ID", style="dim", width=5)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Author", max_width=25)
    table.add_column("Lib. Checkouts", justify="right")
    table.add_column("Your Rating", justify="center")
    table.add_column("You Checked Out", justify="right")

    for b in books[:limit]:
        rating = f"{b['avg_rating']:.1f}" if b.get("avg_rating") else "—"
        table.add_row(
            str(b["id"]),
            b["title"],
            b.get("author") or "—",
            str(b.get("library_checkout_count") or "—"),
            rating,
            str(b["times_checked_out"]),
        )

    console.print(table)
    if len(books) > limit:
        console.print(f"[dim]Showing {limit} of {len(books)} books. Use --limit to see more.[/dim]")


if __name__ == "__main__":
    cli()
