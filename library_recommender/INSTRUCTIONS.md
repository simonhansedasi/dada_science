# Library Recommender — Quick Reference

## Setup (first time only)

```bash
cd ~/coding/dada_science/library_recommender
pip install -r requirements.txt
```

---

## Credentials (first time only)

Edit `.env` in this directory. Each user gets their own card and PIN:

```
# Which user profile is active when --user is not specified
LIBRARY_USER=heiki

# Per-user library credentials
SNOISLE_CARD_HEIKI=your_card_number
SNOISLE_PIN_HEIKI=your_pin

SNOISLE_CARD_MADELEINE=her_card_number
SNOISLE_PIN_MADELEINE=her_pin

# Default pickup branch (optional — skips the branch prompt)
SNOISLE_BRANCH=18
```

`.env` is never committed to git. If you don't know your branch ID, run `./library hold <any_id>` without `--branch` to see the full list.

---

## Users

Every command that touches ratings, checkouts, or recommendations is scoped to a user. Set `LIBRARY_USER` in `.env` to avoid typing `--user` each time.

```bash
./library --user heiki recommend
./library --user madeleine recommend
```

All commands support `--user`. The default is whatever `LIBRARY_USER` is set to in `.env`.

---

## Getting a catalog (first time only)

```bash
# Full run — ~165,000 physical books, all ages (~45 min)
python catalog_scraper.py

# Quick test first (~3,600 books)
python catalog_scraper.py --max-pages 2
```

Re-run anytime to refresh the catalog — ratings and checkout history are never overwritten. Books that haven't changed are skipped, so re-runs are fast. Read timeouts are retried up to 5 times before a page is abandoned; any abandoned pages are written to `failed_pages.csv`. Run again after a failed scrape to pick up any missed pages (already-scraped books will be skipped instantly).

The catalog is shared between all users. Only ratings and checkouts are per-user.

---

## Cold start — seed your first ratings

Before the recommender can personalize suggestions it needs a few ratings. Use `rate-book` to rate books you've already read without going through the checkout flow.

**Interactive loop** — search for books and rate them one by one:
```bash
./library rate-book
./library --user madeleine rate-book
```
Type a title or author, pick from the results, give a score 1–5, repeat. Leave the search blank to finish.

**One-liner** — if you know the ID already:
```bash
./library rate-book <id> <score>
./library rate-book 42 5
```

Find IDs with `./library search`. Five or more ratings is enough for the recommender to start personalizing.

---

## Daily use

### Get recommendations
```bash
./library recommend
./library --user heiki recommend --age juvenile   # children's books only
./library recommend --age adult
./library recommend --age teen
```
Shows animated progress while thinking, then returns 10 books with bold IDs and quick-action hints on each card:
- **5 Top matches** — best fit based on past ratings + popularity
- **2 Experimental** — similar to liked books but rarely checked out
- **3 Hidden gems** — lowest checkout count in the catalog

### Recommend and hold all in one step
```bash
./library --user heiki recommend --age juvenile --hold-all
```
Displays recommendations then immediately places holds on all of them. Uses `SNOISLE_BRANCH` from `.env` for pickup (Lynnwood = 18). Logs in once and places all holds in sequence.

Skips two kinds of books with a warning:
- No catalog ID → re-run the scraper
- Non-`S121` metadata ID (e.g. `S980...`) → shared record from a partner library; Sno-Isle's API won't hold it. Place these on the website.

### Place a single hold
```bash
./library --user heiki hold <id>
```
Same `S121` restriction applies — the CLI will tell you clearly if a book can't be held via API.

### Search the catalog
```bash
./library search "caterpillar"
./library search --author "Eric Carle"
./library search --title "hungry" --author "carle"
./library search "bedtime" --author "sendak"
```
`--title` and `--author` filters are ANDed together. The positional query searches all fields (title, author, description, subject).

### Check copy availability (no login needed)
```bash
./library availability <id>
```
Shows which branches have the book and whether each copy is on the shelf or checked out. Fast — no login required.

### See your account
```bash
./library my-account
./library --user madeleine my-account
```
Logs into Sno-Isle and shows:
- **Holds** — status, queue position, pickup branch, pickup-by date
- **Checkouts** — local DB id, due date, renewable flag, your rating so far

Use the id column to rate directly without searching:
```bash
./library --user heiki rate-book <id> <score>
```
Books that show `?` for id aren't in the local catalog yet — re-run the scraper. Uses the credentials for the active user from `.env`.

### Place a hold at the library
```bash
./library hold <id>
./library --user madeleine hold <id>
```
Shows live copy availability, then logs into Sno-Isle using the active user's credentials and places a hold. The `--branch` (or `SNOISLE_BRANCH` in `.env`) is the **pickup** branch.

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
./library --user madeleine rate
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

### Save and restore ratings

Ratings are saved to a per-user JSON file. Commit these files to git so your history persists across machines.

```bash
# Export
./library export-ratings                    # writes ratings_heiki.json
./library --user madeleine export-ratings   # writes ratings_madeleine.json

# Import (after cloning on a new machine and re-scraping the catalog)
./library import-ratings                    # reads ratings_heiki.json
./library --user madeleine import-ratings   # reads ratings_madeleine.json
```

Books are matched by title + author, so import works after a full re-scrape even when numeric IDs have changed. Any books not found in the current catalog are reported as skipped — re-run the scraper and import again.

**New machine setup:**
```bash
git clone <repo>
pip install -r requirements.txt
python catalog_scraper.py
./library import-ratings
./library --user madeleine import-ratings
./library recommend
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
| `library.db` | SQLite database — catalog, checkouts, and ratings (not committed — too large) |
| `ratings_heiki.json` | Heiki's exported ratings — commit this to git |
| `ratings_madeleine.json` | Madeleine's exported ratings — commit this to git |
| `.env` | Credentials and user config — never committed |
| `catalog_scraper.py` | Populates and refreshes the catalog |
| `failed_pages.csv` | Pages that errored during last scrape (created if any failures) |
| `explore_catalog.py` | Shows available filter fields before scraping |
| `hold.py` | Availability lookup, login, and hold placement |
| `cli.py` | CLI entry point |
| `db.py` | Database operations |
| `recommender.py` | Recommendation engine |

---

## Tips

- **`--user` goes before the subcommand**, not after: `./library --user heiki rate-book 42 5` ✓ — putting it after stores the rating under the wrong user.
- Re-run `catalog_scraper.py` monthly to pick up new books and updated copy counts. It skips anything unchanged so it's safe to run anytime.
- The recommendation engine improves significantly after 5+ rated books.
- Use `./library my-account` to see your pile with IDs and existing ratings, then rate in one pass with `./library --user <name> rate-book <id> <score>`. If a book shows `?` for id but you've rated it before, it's a metadata mismatch — the title+author fallback should catch it automatically; if not, re-run the scraper.
- Ratings are weighted by score — a 5-star book pulls the taste profile harder than a 4-star one.
- Use `./library search` to find a book's ID, then `./library availability <id>` to check the shelf before placing a hold.
- You can rate books in 0.5 increments (e.g., `3.5`).
- Export and commit ratings after every library trip so they're never lost.
