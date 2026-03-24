# Library Recommender — Quick Reference

## Setup (first time only)

```bash
cd ~/coding/dada_science/library_recommender
pip install -r requirements.txt
```

---

## Credentials (first time only)

Edit `.env` in this directory:

```
SNOISLE_CARD=your_card_number
SNOISLE_PIN=your_pin
SNOISLE_BRANCH=your_default_branch_id   # optional — skips the branch prompt every time
```

These are never committed to git. Required for `hold` and `my-account`. If you don't know your branch ID, run `./library hold <any_id>` once without `--branch` to see the full list.

---

## Getting a catalog (first time only)

```bash
# Full run — ~165,000 physical books, all ages (~45 min)
python catalog_scraper.py

# Quick test first (~3,600 books)
python catalog_scraper.py --max-pages 2
```

Re-run anytime to refresh the catalog — ratings and checkout history are never overwritten. Any pages that fail are written to `failed_pages.csv` for inspection.

---

## Cold start — seed your first ratings

Before the recommender can personalize suggestions it needs a few ratings. Use `rate-book` to rate books you've already read without going through the checkout flow.

**Interactive loop** — search for books and rate them one by one:
```bash
./library rate-book
```
Type a title or author, pick from the results, give a score 1–5, repeat. Leave the search blank to finish.

**One-liner** — if you know the ID already:
```bash
./library rate-book <id> <score>
./library rate-book 42 5
```

Find IDs with `./library search "title"`. Five or more ratings is enough for the recommender to start personalizing.

---

## Daily use

### Get recommendations
```bash
./library recommend
./library recommend --age juvenile   # children's books only
./library recommend --age adult      # adult books only
./library recommend --age teen
```
Shows animated progress while thinking, then returns 10 books with bold IDs and quick-action hints on each card:
- **5 Top matches** — best fit based on past ratings + popularity
- **2 Experimental** — similar to liked books but rarely checked out
- **3 Hidden gems** — lowest checkout count in the catalog

### Check copy availability (no login needed)
```bash
./library availability <id>
```
Shows which branches have the book and whether each copy is on the shelf or checked out. Fast — no login required.

### See your account
```bash
./library my-account
```
Logs into Sno-Isle and shows your current holds (status + queue position) and all books currently checked out (due date + renewable status). Uses credentials from `.env`.

### Place a hold at the library
```bash
./library hold <id>
```
Shows live copy availability, then logs into your Sno-Isle account and places a hold. The `--branch` (or `SNOISLE_BRANCH` in `.env`) is the **pickup** branch — the library moves a copy to you regardless of where it currently is.

```bash
./library hold 42              # uses SNOISLE_BRANCH from .env, or prompts
./library hold 42 --branch 18  # override pickup branch for this hold
```

### Record a local checkout
```bash
./library checkout <id>
```
**This does not contact the library.** It only marks the book in your local database so it shows up in `./library rate` after you return it. Use `hold` to actually interact with Sno-Isle.

### Rate books (after returning them)
```bash
./library rate
```
Prompts you to rate each checked-out book 1–5 based on engagement. Press `s` to skip.

| Stars | Meaning |
|-------|---------|
| 1 | No interest / pushed it away |
| 2 | Tolerated it |
| 3 | Liked it |
| 4 | Asked for it again |
| 5 | Totally engaged, must re-read |

### Rate a book directly (no checkout step)
```bash
./library rate-book              # interactive search → rate loop
./library rate-book <id> <score> # one-liner
```

### Search the catalog
```bash
./library search "caterpillar"
./library search "Eric Carle"
./library search "bedtime"
```

### List all books
```bash
./library list
./library list --limit 100
./library list --rated        # only books you've rated
```

---

## File Locations

| File | Purpose |
|------|---------|
| `library.db` | SQLite database — all books, checkouts, and ratings |
| `.env` | Credentials — card, PIN, default branch (never committed) |
| `catalog_scraper.py` | Populates and refreshes the catalog |
| `failed_pages.csv` | Pages that errored during last scrape (created if any failures) |
| `explore_catalog.py` | Shows available filter fields before scraping |
| `hold.py` | Availability lookup, login, and hold placement |
| `cli.py` | CLI entry point |
| `db.py` | Database operations |
| `recommender.py` | Recommendation engine |

> **Backup tip:** Copy `library.db` to keep your rating history safe.

---

## Tips

- Re-run `catalog_scraper.py` periodically to pick up new books and updated copy counts.
- The recommendation engine improves significantly after 5+ rated books.
- Use `./library search` to find a book's ID, then `./library availability` to check the shelf before placing a hold.
- You can rate books in 0.5 increments (e.g., `3.5`).
- `my-account` is the fastest way to see what's due back and what holds are ready.
