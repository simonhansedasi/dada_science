#!/usr/bin/env python3
"""
Library Recommender CLI
A recommendation system for toddler library books.
"""

import json
import os
import sys
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.status import Status

import db
import hold as holds_mod
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

    bid = book['id']
    lines.append(
        f"\n[dim]availability {bid}  •  hold {bid}  •  checkout {bid}[/dim]"
    )

    title_text = f"[bold cyan]{book['title']}[/bold cyan]  [bold yellow]id:{book['id']}[/bold yellow]"
    if label:
        title_text = f"{label}  {title_text}"

    return Panel(
        "\n".join(lines) if lines else "[dim]No details available.[/dim]",
        title=title_text,
        border_style="blue",
        padding=(0, 1),
    )


def _get_credentials(user: str, card_override=None, pin_override=None):
    """
    Look up credentials for a user. Checks in order:
      1. Explicit --card / --pin flags
      2. SNOISLE_CARD_<USER> / SNOISLE_PIN_<USER> env vars
      3. SNOISLE_CARD / SNOISLE_PIN env vars (default)
    Returns (card, pin).
    """
    holds_mod._load_credentials()  # populate os.environ from .env
    ukey = user.upper().replace("-", "_")
    card = (card_override
            or os.environ.get(f"SNOISLE_CARD_{ukey}")
            or os.environ.get("SNOISLE_CARD"))
    pin  = (pin_override
            or os.environ.get(f"SNOISLE_PIN_{ukey}")
            or os.environ.get("SNOISLE_PIN"))
    return card, pin


@click.group()
@click.option("--user", default=None, envvar="LIBRARY_USER",
              help="User profile (default: 'default'). Set LIBRARY_USER in .env to avoid typing it each time.")
@click.pass_context
def cli(ctx, user):
    """📚 Library Recommender — find great books for your little one."""
    db.init_db()
    ctx.ensure_object(dict)
    ctx.obj["user"] = user or "default"


@cli.command()
@click.option("--age", default=None, metavar="AUDIENCE",
              help="Filter by audience, e.g. juvenile, adult, teen.")
@click.option("--hold-all", is_flag=True,
              help="Place holds on all recommendations after displaying them.")
@click.option("--branch", default=None, envvar="SNOISLE_BRANCH",
              help="Pickup branch for holds. Falls back to SNOISLE_BRANCH in .env.")
@click.option("--card", default=None, help="Library card number (overrides .env).")
@click.option("--pin",  default=None, help="Library PIN (overrides .env).")
@click.pass_obj
def recommend(obj, age, hold_all, branch, card, pin):
    """Get 10 book recommendations (5 top, 2 experimental, 3 hidden gems)."""
    user = obj["user"]
    with Status("", console=console, spinner="dots") as status:
        def step(msg):
            console.print(f"  [dim]✓[/dim] {msg}")
            status.update(f"[dim]{msg}[/dim]")

        result, err = rec.recommend(user=user, age=age, step_fn=step)

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
        "\n[dim]availability [bold]<id>[/bold]   check which branches have it and if it's on the shelf[/dim]"
        "\n[dim]hold [bold]<id>[/bold]           place a hold for library pickup (uses .env credentials)[/dim]"
        "\n[dim]checkout [bold]<id>[/bold]       record a local checkout so you can rate it later[/dim]"
        "\n[dim]rate                rate returned books to improve future recommendations[/dim]\n"
    )

    if not hold_all:
        return

    # ── Place holds on all recommendations ────────────────────────────────────
    all_books = (
        [b for b, _ in result["top"]]
        + [b for b, _ in result["experimental"]]
        + result["bottom"]
    )
    holdable   = [b for b in all_books if b.get("metadata_id") and b["metadata_id"].startswith("S121")]
    no_meta    = [b for b in all_books if not b.get("metadata_id")]
    non_snoisle = [b for b in all_books if b.get("metadata_id") and not b["metadata_id"].startswith("S121")]

    if no_meta:
        console.print(
            f"[yellow]Skipping {len(no_meta)} book(s) with no catalog ID "
            f"(re-run the scraper to fix):[/yellow]"
        )
        for b in no_meta:
            console.print(f"  [dim]• {b['title']}[/dim]")

    if non_snoisle:
        console.print(
            f"[yellow]Skipping {len(non_snoisle)} book(s) not in Sno-Isle's catalog "
            f"(can't be held via API):[/yellow]"
        )
        for b in non_snoisle:
            console.print(f"  [dim]• {b['title']}[/dim]")

    if not holdable:
        console.print("[red]No holdable books found.[/red]")
        return

    resolved_card, resolved_pin = _get_credentials(user, card, pin)
    if not resolved_card or not resolved_pin:
        console.print(
            f"[red]No credentials found for user '{user}'.[/red]\n"
            f"[dim]Add SNOISLE_CARD_{user.upper()} and SNOISLE_PIN_{user.upper()} to .env[/dim]"
        )
        sys.exit(1)

    if not branch:
        console.print("\n[bold]Select a pickup branch:[/bold]\n")
        try:
            branches = holds_mod.get_branches()
        except Exception as e:
            console.print(f"[red]Could not fetch branches: {e}[/red]")
            sys.exit(1)
        for code, name in branches:
            console.print(f"  [cyan]{code:3s}[/cyan]  {name}")
        branch = click.prompt("\nBranch ID")

    console.print(f"\n[dim]Logging in as {user}...[/dim]")
    try:
        session = holds_mod.login(resolved_card, resolved_pin)
        account_id, _ = holds_mod.get_account_id(session)
    except Exception as e:
        console.print(f"[red]Login failed: {e}[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Placing {len(holdable)} hold(s) at branch {branch}...[/bold]\n")
    placed = failed = 0
    for book in holdable:
        try:
            holds_mod.place_hold(session, account_id, book["metadata_id"], branch)
            console.print(f"  [green]✓[/green] {book['title']}")
            placed += 1
        except RuntimeError as e:
            console.print(f"  [red]✗[/red] {book['title']}  [dim]{e}[/dim]")
            failed += 1

    console.print(
        f"\n[green]{placed} hold(s) placed.[/green]"
        + (f"  [yellow]{failed} failed.[/yellow]" if failed else "")
        + "\n[dim]Check your holds at https://sno-isle.bibliocommons.com/holds[/dim]\n"
    )


@cli.command(name="rate-book")
@click.argument("book_id", type=int, required=False)
@click.argument("score",   type=float, required=False)
@click.pass_obj
def rate_book(obj, book_id, score):
    """Directly rate a book — no checkout step needed. Great for seeding.

    \b
    Usage:
      ./library rate-book              # interactive: search → rate in a loop
      ./library rate-book <id> <score> # one-liner: rate book #id with score
    """
    user = obj["user"]

    # ── One-liner mode ───────────────────────────────────────────────────────
    if book_id is not None:
        book = db.get_book(book_id, user)
        if not book:
            console.print(f"[red]Book #{book_id} not found.[/red]")
            sys.exit(1)
        if score is None:
            score = click.prompt(
                f"  Rating for '{book['title']}' (1–5)",
                type=click.FloatRange(1, 5)
            )
        if not (1.0 <= score <= 5.0):
            console.print("[red]Score must be between 1 and 5.[/red]")
            sys.exit(1)
        db.rate_book_direct(book_id, score, user)
        stars = "★" * int(score) + "☆" * (5 - int(score))
        console.print(f"[yellow]{stars}[/yellow] [bold]{book['title']}[/bold] rated {score}\n")
        return

    # ── Interactive loop mode ─────────────────────────────────────────────────
    console.print(
        "\n[bold]Seed ratings[/bold]  [dim](search for a book, rate it, repeat)[/dim]\n"
        "[dim]Leave search blank to finish.[/dim]\n"
    )
    rated = 0
    while True:
        query = click.prompt("Search", default="", show_default=False).strip()
        if not query:
            break

        results = db.search_books(query, user)
        if not results:
            console.print(f"  [dim]No results for '{query}'[/dim]\n")
            continue

        matches = results[:8]
        console.print()
        for i, b in enumerate(matches, 1):
            existing = f"  [dim](already rated {b['avg_rating']:.1f})[/dim]" if b.get("avg_rating") else ""
            console.print(f"  [cyan]{i}.[/cyan] [bold]{b['title']}[/bold]"
                          + (f"  [dim]— {b['author']}[/dim]" if b.get("author") else "")
                          + existing)
        console.print()

        if len(matches) == 1:
            book = matches[0]
        else:
            pick = click.prompt(
                "  Pick a number (or Enter to skip)",
                default="", show_default=False
            ).strip()
            if not pick:
                continue
            try:
                idx = int(pick) - 1
                if not (0 <= idx < len(matches)):
                    raise ValueError
            except ValueError:
                console.print("  [red]Invalid choice.[/red]\n")
                continue
            book = matches[idx]
        raw = click.prompt(
            f"  Rating for '{book['title']}' (1–5, or s to skip)",
            default="s", show_default=False
        ).strip()
        if raw.lower() == "s":
            continue
        try:
            score = float(raw)
            if not (1.0 <= score <= 5.0):
                raise ValueError
        except ValueError:
            console.print("  [red]Enter a number 1–5.[/red]\n")
            continue

        db.rate_book_direct(book["id"], score, user)
        stars = "★" * int(score) + "☆" * (5 - int(score))
        console.print(f"  [yellow]{stars}[/yellow] saved!\n")
        rated += 1

    if rated:
        console.print(f"[green]{rated} book(s) rated.[/green] "
                      f"Run [bold]./library recommend[/bold] to see your picks.\n")


@cli.command()
@click.argument("book_id", type=int)
@click.pass_obj
def checkout(obj, book_id):
    """Mark a book as checked out by its ID."""
    user = obj["user"]
    book = db.get_book(book_id, user)
    if not book:
        console.print(f"[red]Book #{book_id} not found.[/red]")
        sys.exit(1)
    db.add_checkout(book_id, user)
    console.print(f"\n[green]Checked out:[/green] [bold]{book['title']}[/bold]\n"
                  f"Rate it when you return it with [bold]library rate[/bold].\n")


@cli.command()
@click.pass_obj
def rate(obj):
    """Prompt to rate all currently checked-out unrated books."""
    user = obj["user"]
    pending = db.get_checked_out_unrated(user)
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
@click.argument("query", required=False, default=None)
@click.option("--title",  "-t", default=None, help="Filter by title.")
@click.option("--author", "-a", default=None, help="Filter by author.")
@click.pass_obj
def search(obj, query, title, author):
    """Search books by title, author, description, or subject.

    \b
    Examples:
      ./library search "caterpillar"
      ./library search --author "Eric Carle"
      ./library search --title "hungry" --author "carle"
      ./library search "bedtime" --author "sendak"
    """
    user = obj["user"]
    if not any([query, title, author]):
        console.print("[red]Provide a search term or use --title / --author.[/red]")
        return
    results = db.search_books(query=query, user=user, title=title, author=author)
    label = " + ".join(filter(None, [query, title and f"title:{title}", author and f"author:{author}"]))
    if not results:
        console.print(f"\n[dim]No results for '{label}'.[/dim]\n")
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
@click.pass_obj
def list_books(obj, rated, limit):
    """List books in the database."""
    user = obj["user"]
    books = db.get_all_books(user)
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


@cli.command()
@click.argument("book_id", type=int)
@click.pass_obj
def availability(obj, book_id):
    """Show which branches have a book and whether it's on the shelf."""
    user = obj["user"]
    book = db.get_book(book_id, user)
    if not book:
        console.print(f"[red]Book #{book_id} not found.[/red]")
        sys.exit(1)

    if not book.get("metadata_id"):
        console.print(
            f"[red]No BiblioCommons ID for '{book['title']}'.[/red]\n"
            "[dim]Re-run the scraper: python catalog_scraper.py[/dim]"
        )
        sys.exit(1)

    with console.status("[dim]Checking availability...[/dim]"):
        try:
            copies = holds_mod.get_availability(book["metadata_id"])
        except Exception as e:
            console.print(f"[red]Could not fetch availability: {e}[/red]")
            sys.exit(1)

    console.print(f"\n[bold cyan]{book['title']}[/bold cyan]"
                  + (f"  [dim]by {book['author']}[/dim]" if book.get("author") else ""))

    if not copies:
        console.print("[dim]No copies found.[/dim]\n")
        return

    t = Table(box=box.SIMPLE, show_header=True)
    t.add_column("Branch", style="cyan")
    t.add_column("Collection")
    t.add_column("Status", justify="center")
    t.add_column("Call number", style="dim")

    for c in copies:
        status = c["library_status"] or c["status"]
        status_str = f"[green]{status}[/green]" if c["status"] == "AVAILABLE" else f"[dim]{status}[/dim]"
        t.add_row(c["branch_name"], c["collection"], status_str, c["call_number"])

    console.print(t)
    console.print(f"[dim]To place a hold: [bold]./library hold {book_id}[/bold][/dim]\n")


@cli.command()
@click.argument("book_id", type=int)
@click.option("--branch", default=None, envvar="SNOISLE_BRANCH",
              help="Pickup branch ID. Falls back to SNOISLE_BRANCH in .env, then interactive.")
@click.option("--card", default=None, help="Library card number (overrides .env).")
@click.option("--pin",  default=None, help="Library PIN (overrides .env).")
@click.pass_obj
def hold(obj, book_id, branch, card, pin):
    """Place a hold on a book at Sno-Isle for library pickup."""
    user = obj["user"]
    book = db.get_book(book_id, user)
    if not book:
        console.print(f"[red]Book #{book_id} not found.[/red]")
        sys.exit(1)

    if not book.get("metadata_id"):
        console.print(
            f"[red]No BiblioCommons ID for '{book['title']}'.[/red]\n"
            "[dim]Re-run the scraper: python catalog_scraper.py[/dim]"
        )
        sys.exit(1)

    if not book["metadata_id"].startswith("S121"):
        console.print(
            f"[red]'{book['title']}' is not in Sno-Isle's own catalog (id: {book['metadata_id']}).[/red]\n"
            "[dim]This book can be found at the library but holds must be placed on the website.[/dim]"
        )
        sys.exit(1)

    # Live availability lookup
    with console.status("[dim]Checking availability...[/dim]"):
        try:
            copies = holds_mod.get_availability(book["metadata_id"])
        except Exception as e:
            console.print(f"[yellow]Could not fetch availability: {e}[/yellow]")
            copies = []

    if copies:
        avail_table = Table(title="Copy availability", box=box.SIMPLE, show_header=True)
        avail_table.add_column("Branch", style="cyan")
        avail_table.add_column("Collection")
        avail_table.add_column("Status", justify="center")
        avail_table.add_column("Call number", style="dim")

        for c in copies:
            status = c["library_status"] or c["status"]
            if c["status"] == "AVAILABLE":
                status_str = f"[green]{status}[/green]"
            else:
                status_str = f"[dim]{status}[/dim]"
            avail_table.add_row(c["branch_name"], c["collection"], status_str, c["call_number"])

        console.print()
        console.print(avail_table)

    # Branch selection
    if branch:
        console.print(f"\n[dim]Pickup branch: {branch}[/dim]")
    else:
        console.print("\n[bold]Select a pickup branch:[/bold]\n")
        try:
            branches = holds_mod.get_branches()
        except Exception as e:
            console.print(f"[red]Could not fetch branches: {e}[/red]")
            sys.exit(1)

        for code, name in branches:
            console.print(f"  [cyan]{code:3s}[/cyan]  {name}")

        branch = click.prompt("\nBranch ID")

    # Resolve credentials for this user
    resolved_card, resolved_pin = _get_credentials(user, card, pin)
    if not resolved_card or not resolved_pin:
        console.print(
            f"[red]No credentials found for user '{user}'.[/red]\n"
            f"[dim]Add SNOISLE_CARD_{user.upper()} and SNOISLE_PIN_{user.upper()} to .env[/dim]"
        )
        sys.exit(1)

    console.print(f"\nPlacing hold on [bold cyan]{book['title']}[/bold cyan]...")

    try:
        holds_mod.hold_book(
            metadata_id=book["metadata_id"],
            pickup_branch_id=branch,
            card=resolved_card,
            pin=resolved_pin,
        )
        console.print(
            f"[green]Hold placed![/green] Pick up at branch [bold]{branch}[/bold] "
            f"when it's ready.\n"
            f"[dim]Check your holds at https://sno-isle.bibliocommons.com/holds[/dim]\n"
        )
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


@cli.command(name="my-account")
@click.option("--card", default=None, help="Library card number (overrides .env).")
@click.option("--pin",  default=None, help="Library PIN (overrides .env).")
@click.pass_obj
def my_account(obj, card, pin):
    """Show your current holds and checked-out books from Sno-Isle."""
    user = obj["user"]
    resolved_card, resolved_pin = _get_credentials(user, card, pin)
    if not resolved_card or not resolved_pin:
        console.print(
            f"[red]No credentials found for user '{user}'.[/red]\n"
            f"[dim]Add SNOISLE_CARD_{user.upper()} and SNOISLE_PIN_{user.upper()} to .env[/dim]"
        )
        sys.exit(1)

    with console.status("[dim]Logging in...[/dim]"):
        try:
            session = holds_mod.login(resolved_card, resolved_pin)
            account_id, _ = holds_mod.get_account_id(session)
        except Exception as e:
            console.print(f"[red]Login failed: {e}[/red]")
            sys.exit(1)

    with console.status("[dim]Fetching your account...[/dim]"):
        try:
            holds     = holds_mod.get_holds(session, account_id)
            checkouts = holds_mod.get_checkouts(session, account_id)
        except Exception as e:
            console.print(f"[red]Could not fetch account data: {e}[/red]")
            sys.exit(1)

    # ── Holds ──────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        f"[bold cyan]HOLDS[/bold cyan]  [dim]({len(holds)} waiting)[/dim]",
        border_style="cyan", box=box.ROUNDED, padding=(0, 1)
    ))
    if not holds:
        console.print("  [dim]No holds.[/dim]\n")
    else:
        t = Table(box=box.SIMPLE, show_header=True)
        t.add_column("Title", style="cyan", max_width=40)
        t.add_column("Author", max_width=22)
        t.add_column("Status", justify="center")
        t.add_column("Position", justify="right")
        t.add_column("Pickup branch")
        t.add_column("Pickup by", style="dim")
        for h_ in holds:
            status = h_["status"] or "—"
            color  = "green" if status == "READY" else "yellow"
            t.add_row(
                h_["title"],
                h_["author"] or "—",
                f"[{color}]{status}[/{color}]",
                str(h_["position"]) if h_["position"] else "—",
                h_["pickup_branch"] or "—",
                h_["pickup_by"] or "—",
            )
        console.print(t)

    # ── Checkouts ──────────────────────────────────────────────────────────
    # Enrich each checkout with local DB id and rating
    meta_to_id = db.get_book_ids_by_metadata(
        [c["metadata_id"] for c in checkouts if c.get("metadata_id")]
    )
    # Fall back to title+author match for any checkouts not found by metadata_id
    unmatched = [c for c in checkouts if not meta_to_id.get(c.get("metadata_id"))]
    title_author_to_id = db.get_book_ids_by_title_author(unmatched)
    book_id_to_rating = db.get_ratings_by_book_ids(
        list(meta_to_id.values()) + list(title_author_to_id.values()), user
    )

    console.print(Panel(
        f"[bold green]CHECKED OUT[/bold green]  [dim]({len(checkouts)} books)[/dim]",
        border_style="green", box=box.ROUNDED, padding=(0, 1)
    ))
    if not checkouts:
        console.print("  [dim]No books currently checked out.[/dim]\n")
    else:
        t2 = Table(box=box.SIMPLE, show_header=True)
        t2.add_column("ID", style="yellow bold", justify="right")
        t2.add_column("Title", style="cyan", max_width=40)
        t2.add_column("Author", max_width=22)
        t2.add_column("Due date", justify="center")
        t2.add_column("Renewable", justify="center")
        t2.add_column("Your rating", justify="center")
        for c in checkouts:
            due      = c["due_date"][:10] if c["due_date"] else "—"
            color    = "red" if c["overdue"] else "white"
            renew    = "[green]Yes[/green]" if c["renewable"] else "[dim]No[/dim]"
            local_id = (meta_to_id.get(c.get("metadata_id"))
                        or title_author_to_id.get((c["title"], c["author"])))
            id_str   = str(local_id) if local_id else "[dim]?[/dim]"
            rating   = book_id_to_rating.get(local_id) if local_id else None
            if rating is not None:
                stars = "★" * int(round(rating)) + "☆" * (5 - int(round(rating)))
                rating_str = f"[yellow]{stars}[/yellow] [dim]{rating:.1f}[/dim]"
            else:
                rating_str = "[dim]—[/dim]"
            t2.add_row(id_str, f"[{color}]{c['title']}[/{color}]", c["author"] or "—", due, renew, rating_str)
        console.print(t2)
        console.print("[dim]Rate by id: [bold]./library --user heiki rate-book <id> <score>[/bold][/dim]\n")


@cli.command(name="export-ratings")
@click.argument("path", default=None, required=False)
@click.pass_obj
def export_ratings(obj, path):
    """Export your ratings and checkout history to a JSON file.

    \b
    Usage:
      ./library export-ratings             # writes ratings_<user>.json
      ./library export-ratings myfile.json # custom path
    """
    user = obj["user"]
    if path is None:
        path = f"ratings_{user}.json"
    data = db.export_ratings(user)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    console.print(
        f"[green]Exported[/green] {len(data['book_ratings'])} rated book(s) "
        f"and {len(data['checkouts'])} checkout record(s) to [bold]{path}[/bold]"
    )


@cli.command(name="import-ratings")
@click.argument("path", default=None, required=False)
@click.pass_obj
def import_ratings(obj, path):
    """Restore ratings from a JSON file produced by export-ratings.

    \b
    Usage:
      ./library import-ratings             # reads ratings_<user>.json
      ./library import-ratings myfile.json # custom path

    Books are matched by title + author, so this works after a full
    re-scrape even if numeric IDs have changed.
    """
    user = obj["user"]
    if path is None:
        path = f"ratings_{user}.json"
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]File not found: {path}[/red]")
        sys.exit(1)

    restored, skipped = db.import_ratings(data, user)
    console.print(f"[green]Restored[/green] {restored} book(s).")
    if skipped:
        console.print(
            f"[dim]{skipped} book(s) skipped — not found in current catalog. "
            f"Re-run the scraper then import again.[/dim]"
        )


if __name__ == "__main__":
    cli()
