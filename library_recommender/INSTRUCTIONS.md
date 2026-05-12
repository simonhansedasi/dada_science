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
# Full run — ~20-40k juvenile books, subject-targeted (~5-10 min)
python catalog_scraper.py

# Quick test first (~500 books)
python catalog_scraper.py --max-pages 2
```

The scraper queries 12 children's subject categories (`picture books`, `juvenile fiction`, `board books`, `fairy tales`, etc.) and deduplicates by BiblioCommons bib ID. Overlapping subjects are free — a book appearing in multiple subjects is only stored once.

Re-run anytime to refresh the catalog — ratings and checkout history are never overwritten. Books that haven't changed are skipped, so re-runs are fast. Any failed pages are written to `failed_pages.csv`; re-run to pick them up.

The catalog is shared between all users. Only ratings and checkouts are per-user.

### Adding a specific book not in the catalog

If a book you want isn't in the local catalog (e.g. a very old bib record the subject sweep missed), add it directly from BiblioCommons:

```bash
./library add-book "The Lorax"                         # title search (default)
./library add-book "Adam Raccoon" --type title         # find all volumes in a series
./library add-book "Eric Carle" --type author          # by author
```

Shows matching results with checkout counts and any already-in-catalog flags. Enter a number, comma-separated list, or `all` to add.

---

## Cold start — seed your first ratings

Before the recommender can personalize suggestions it needs a few ratings. Use `export-account-csv` if you have books currently checked out, or `rate-book` to rate books you've already read without going through the checkout flow.

**CSV workflow** (fastest for a batch):
```bash
./library export-account-csv          # export current checkouts
# fill in the CSV, then:
./library import-ratings-csv currently_out_YYYY-MM-DD.csv
```

**One-liner** — if you know the ID:
```bash
./library rate-book <id> <score>
./library rate-book 42 5
```

**Interactive loop** — search and rate one by one:
```bash
./library rate-book
```

Find IDs with `./library search`. Five or more ratings (or any combination of reads/reread demands) is enough for the recommender to start personalizing.

---

## Daily use

### Before every library trip — sync current checkouts

The recommender can't know what's already on your shelf unless you tell it. Run this once before recommending:

```bash
./library sync-checkouts
./library --user madeleine sync-checkouts   # if using multi-user
```

This logs into Sno-Isle, fetches your live checkout list, and marks those books so `recommend` skips them. Re-run after returning books to un-flag them.

---

### Get recommendations
```bash
./library recommend
./library --user heiki recommend
```
Shows animated progress while thinking, then returns 10 books with bold IDs and quick-action hints on each card:
- **5 Top matches** — best fit based on past ratings + popularity
- **2 Experimental** — similar to liked books but rarely checked out
- **3 Hidden gems** — lowest checkout count in the catalog

### Recommend and hold all in one step
```bash
./library --user heiki recommend --hold-all
```
Displays recommendations then immediately places holds on all of them. Uses `SNOISLE_BRANCH` from `.env` for pickup (Lynnwood = 18). Logs in once and places all holds in sequence.

Skips two kinds of books with a warning:
- No catalog ID → use `./library add-book "title"` to find and add it
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

Books that show `?` for id aren't in the local catalog yet — re-run the scraper. Uses the credentials for the active user from `.env`.

### Rate a whole batch via CSV (primary rating workflow)

```bash
# 1. Export currently checked-out books
./library export-account-csv          # writes currently_out_YYYY-MM-DD.csv

# 2. Open CSV in any spreadsheet, fill in: rating, times_read, reread_demands, false_starts
#    Leave cells blank to skip them — blank = don't change what's already stored

# 3. Apply the data
./library import-ratings-csv currently_out_2025-06-01.csv
```

Values are SET (not incremented). `times_read=5` stores 5 total — it doesn't add 5 to whatever was there.

Rate a single book one-off:
```bash
./library rate-book <id> <score>
./library rate-book              # interactive search loop
```

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

### Log engagement signals (during or after reading)

There are four signals you can tally for any book. Log them as they happen — you don't have to wait until return day.

#### `read` — finished the book
```bash
./library read <id>
./library --user heiki read 42
```
Call once per completed reading session. If Heiki gets the same book read three times across a checkout, run it three times.

#### `reread` — "again!"
```bash
./library reread <id>
./library --user heiki reread 42
```
Log every time Heiki asks for another pass before the book is even put down. This is the strongest positive signal in the recommender.

#### `false-start` — opened but not finished
```bash
./library false-start <id>
./library --user heiki false-start 42
```
Log when a book gets pushed away partway through. Soft negative — a few false starts will nudge it down in future recommendations without burying it.

#### `rate` / `rate-book` — star rating (optional but useful)
```bash
./library rate
./library --user madeleine rate
```
Prompts you to rate each checked-out unrated book 1–5. Press `s` to skip. The star rating is your subjective take — re-read demands and reads tell you what Heiki actually wanted.

| Stars | Meaning |
|-------|---------|
| 1 | No interest / pushed it away |
| 2 | Tolerated it |
| 3 | Liked it |
| 4 | Asked for it again |
| 5 | Totally engaged, must re-read |

Rate directly if you know the ID and don't want the interactive prompt:
```bash
./library rate-book              # interactive search → rate loop
./library rate-book <id> <score> # one-liner
```

#### How the signals combine

The recommender builds a preference score per book, normalized across the catalog:

| Signal | Weight |
|--------|--------|
| Star rating | 30% |
| Re-read demands | 40% |
| Times read | 20% |
| False starts | −10% |

Any book with a preference score above zero seeds the taste profile. All four signals improve recommendations — even a single re-read demand on an unrated book is enough to register.

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

Books are matched by BiblioCommons ID first, then by title + author as a fallback. Import works after a full re-scrape even when numeric IDs have changed. Any books not found in the current catalog are reported as skipped — re-run the scraper (or use `add-book`) and import again.

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

- **Run `sync-checkouts` before every trip.** Without it, `recommend` doesn't know what's on your shelf and will suggest books you already have.
- **`--user` goes before the subcommand**, not after: `./library --user heiki rate-book 42 5` ✓ — putting it after stores the data under the wrong user.
- Re-run `catalog_scraper.py` monthly to pick up new books and updated copy counts. It skips anything unchanged so it's safe to run anytime.
- The recommendation engine improves significantly after 5+ engagement events — a mix of reads, reread demands, and ratings all count.
- Re-read demands carry the most weight (40%). If Heiki smashes the "again" button on a book but you never formally rate it, the recommender still picks it up.
- Use `./library my-account` to see your pile with IDs and existing ratings, then log engagement in one pass. If a book shows `?` for id, use `add-book` to find and add it.
- Use `./library search` to find a book's ID — it searches title, subtitle, author, series name, description, and subject. Then use `./library availability <id>` to check the shelf before placing a hold.
- You can rate books in 0.5 increments (e.g., `3.5`).
- Export and commit ratings after every library trip so they're never lost.
- Series volumes are stored separately — searching "Adam Raccoon" shows each volume with its subtitle (e.g., "The Adventures of Adam Raccoon: Lost Woods").
