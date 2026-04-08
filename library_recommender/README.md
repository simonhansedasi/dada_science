# Library Recommender

A command-line tool that helps you pick the best books to check out from the library for your toddler. It scrapes the Sno-Isle library catalog directly into a local database, learns each user's taste from engagement ratings after each visit, and can place holds on recommended books from the command line.

Built for a 2-year-old whose parents rate books 1–5 based on how engaged the child is during read-aloud sessions. Supports multiple users with separate rating profiles.

---

## Plain Language Summary

Run the scraper to pull the Sno-Isle catalog into a local database (`library.db`). When you get recommendations, it shows you 10 books split into three groups: the best overall matches, a couple of "wild card" picks that are similar to what your child loved but that most people overlook, and three books that almost nobody checks out (pure discovery). When you find something you want, place a hold directly from the command line. After each library trip, rate the books you returned, and the system uses those ratings to get better at predicting what your child will engage with next time.

Each parent has their own user profile and rating history. Recommendations are fully independent — different users can have different taste profiles against the same catalog.

---

## Project Structure

```
library_recommender/
├── cli.py                  CLI entry point — all commands live here
├── db.py                   Database layer — reads and writes to library.db
├── recommender.py          Recommendation engine — scoring and ranking logic
├── catalog_scraper.py      Scraper — pulls Sno-Isle catalog directly into library.db
├── hold.py                 Hold placement — login, account resolution, hold submission
├── explore_catalog.py      Catalog explorer — shows available filter fields and counts
├── Untitled.ipynb          Scraper notebook — exploration / raw API inspection
├── library                 Shell wrapper so you can run ./library <command>
├── library.db              SQLite database (created on first run, not committed — too large)
├── ratings_heiki.json      Heiki's exported ratings — commit to git
├── ratings_madeleine.json  Madeleine's exported ratings — commit to git
├── requirements.txt        Python dependencies
├── INSTRUCTIONS.md         Quick reference for daily use
└── README.md               This file
```

---

## Multi-User Setup

Each user gets an independent rating profile. The catalog is shared; only ratings and checkouts are per-user.

### Credentials in `.env`

```
# Active user when --user is not specified
LIBRARY_USER=heiki

# Per-user library cards
SNOISLE_CARD_HEIKI=your_card_number
SNOISLE_PIN_HEIKI=your_pin

SNOISLE_CARD_MADELEINE=her_card_number
SNOISLE_PIN_MADELEINE=her_pin

# Default pickup branch
SNOISLE_BRANCH=18
```

`.env` is in `.gitignore` and is never committed.

### Selecting a user

```bash
./library --user heiki recommend
./library --user madeleine recommend
```

Set `LIBRARY_USER` in `.env` to avoid typing `--user` every time. All commands support `--user`.

---

## Getting a Catalog

The recommender needs books in the database before it can recommend anything.

### 1. Explore what's available (optional)

```bash
python explore_catalog.py                                   # full overview of all filter fields
python explore_catalog.py --audience JUVENILE --format BK  # scope to children's physical books
```

### 2. Scrape into the database

```bash
python catalog_scraper.py                  # full run — ~165k physical books, all ages (~45 min)
python catalog_scraper.py --max-pages 2    # quick test (~3,600 books)
```

Re-run anytime to refresh checkout counts and pick up new titles. Ratings and personal checkout history are never overwritten. Any pages that fail are written to `failed_pages.csv` for inspection. Monthly re-runs are sufficient for a current catalog.

The scraper skips books that haven't changed (matched by `metadata_id`, compared against description, isbn, genre, subject, age_range, and checkout count). Only new or changed books are written. Read timeouts are retried up to 5 times with exponential backoff before a page is abandoned.

| Flag | Default | Description |
|------|---------|-------------|
| `--max-pages N` | all | Stop after N pages per query prefix |

---

## CLI Commands

### `./library [--user NAME] <command>`

All commands accept `--user` as a global flag before the command name. Defaults to `LIBRARY_USER` in `.env`.

---

### `./library recommend [--age AUDIENCE] [--hold-all]`

Displays 10 book recommendations in three categories, scoped to the active user's ratings.

```bash
./library recommend
./library --user heiki recommend --age juvenile
./library --user heiki recommend --age juvenile --hold-all
```

`--age` is a case-insensitive substring match against the BiblioCommons audience field.

`--hold-all` places holds on all 10 recommendations immediately after displaying them. Logs in once and places all holds in sequence. Uses `SNOISLE_BRANCH` from `.env` for pickup branch (or prompts if not set). Two categories of books are skipped with a warning:
- Books with no `metadata_id` — re-run the scraper to fix
- Books whose `metadata_id` doesn't start with `S121` — these are shared catalog records from partner libraries; Sno-Isle's hold API only accepts its own records. Place these holds on the website instead.

```bash
# Additional --hold-all options (all fall back to .env)
./library --user heiki recommend --hold-all --branch 18
./library --user heiki recommend --hold-all --card 12345 --pin 9999
```

**The three categories:**

| Category | Count | How it's chosen |
|----------|-------|-----------------|
| Top matches | 5 | Highest combined score: content similarity to your liked books (60%) + library popularity (40%) |
| Experimental | 2 | High content similarity to liked books but low library checkout count |
| Hidden gems | 3 | Lowest library checkout counts in the entire catalog |

**How the content score works:**

The engine converts each book's title, author, description, subject, genre, and age range into a numerical fingerprint using TF-IDF. It then finds the "average fingerprint" of books rated 4 or 5 stars by the active user, **weighted by rating** (a 5-star book pulls the profile harder than a 4-star one), and measures how similar each unread book is to that profile.

If there are no ratings yet, it falls back to the mean vector of all checked-out books. If there are no checkouts either, it falls back to popularity-only scoring.

---

### `./library search`

Searches the catalog by title, author, description, or subject. Filters are ANDed together.

```bash
./library search "caterpillar"                      # all fields
./library search --author "Eric Carle"              # author only
./library search --title "hungry" --author "carle"  # both
./library search "bedtime" --author "sendak"        # general + author filter
```

---

### `./library hold <id>`

Places a hold on a book at Sno-Isle for library pickup using the active user's card.

```bash
./library hold 42                          # uses SNOISLE_BRANCH from .env, or prompts
./library hold 42 --branch 18             # Lynnwood Library directly
./library --user madeleine hold 42        # places hold on Madeleine's card
```

**What it does:**
1. Fetches live copy availability (unauthenticated) — shows which branches have the book and whether each copy is on the shelf or checked out
2. Logs into `sno-isle.bibliocommons.com` using the active user's card and PIN from `.env`
3. Resolves the `accountId` from the BiblioCommons API
4. POSTs a hold to `gateway.bibliocommons.com/v2/libraries/sno-isle/holds`

**Note:** Only books with a `metadata_id` starting with `S121` can be held via the API — these are records owned by Sno-Isle. Books with other prefixes (e.g. `S980`) are shared records from partner libraries; the CLI will refuse them with a clear message. Place those holds on the website instead.

**Branch IDs** (common Sno-Isle locations):

| ID | Branch | ID | Branch |
|----|--------|----|--------|
| 7  | Arlington | 18 | Lynnwood |
| 9  | Camano Island | 19 | Marysville |
| 13 | Edmonds | 20 | Mill Creek |
| 15 | Granite Falls | 21 | Monroe |
| 16 | Lake Stevens | 22 | Mountlake Terrace |
| 30 | Lakewood Smokey Point | 23 | Mukilteo |
| 17 | Langley | 25 | Snohomish |

Run `./library hold <id>` without `--branch` for the full interactive list.

---

### `./library availability <id>`

Shows live copy availability for a book — no login required.

```bash
./library availability 42
```

Lists every copy in the Sno-Isle system with branch name, collection, call number, and shelf status.

---

### `./library my-account`

Logs into Sno-Isle and shows current holds and checked-out books for the active user.

```bash
./library my-account
./library --user madeleine my-account
```

Shows:
- **Holds** — title, status, queue position, pickup branch, pickup-by / expiry dates
- **Checkouts** — local DB id, title, due date, overdue status, renewable flag, your rating

The local DB id is looked up first by matching the BiblioCommons `metadata_id`, then by title + author as a fallback (handles cases where the checkout API returns a different metadata_id format than the scraper stored). Books genuinely absent from the local catalog show `?` — re-run the scraper to pick them up. Use the id to rate directly from this view:

```bash
./library --user heiki rate-book <id> <score>
```

---

### `./library checkout <id>`

Records a book as currently checked out in the local database for the active user.

```bash
./library checkout 42
```

**This does not contact the library.** It marks the book so it appears in `./library rate` when you return it. Use `hold` to interact with Sno-Isle.

---

### `./library rate`

Prompts you to rate all checked-out unrated books for the active user.

```bash
./library rate
./library --user madeleine rate
```

**Rating scale:**

| Score | Meaning |
|-------|---------|
| 1 | No interest |
| 2 | Tolerated |
| 3 | Liked it |
| 4 | Asked for it again |
| 5 | Totally engaged |

Decimal values are accepted (e.g., `3.5`). Press `s` to skip a book.

---

### `./library rate-book`

Rate a book directly without going through the checkout flow. Useful for seeding ratings on books you've already read.

```bash
./library rate-book              # interactive: search → pick → rate, repeat
./library rate-book <id> <score> # one-liner
```

---

### `./library export-ratings` / `./library import-ratings`

Export and restore per-user ratings. Commit the exported files to git so ratings persist across machines.

```bash
# Export (run after each library trip, then commit)
./library export-ratings                    # writes ratings_heiki.json
./library --user madeleine export-ratings   # writes ratings_madeleine.json

# Import (after cloning or pulling on a new machine)
./library import-ratings                    # reads ratings_heiki.json
./library --user madeleine import-ratings   # reads ratings_madeleine.json

# Custom file path
./library export-ratings mybackup.json
./library import-ratings mybackup.json
```

Books are matched by title + author, so import works correctly after a full re-scrape where numeric IDs differ. Books not found in the current catalog are reported as skipped — re-run the scraper and import again.

**New machine workflow:**
```bash
git clone <repo>
pip install -r requirements.txt
# Edit .env with your credentials
python catalog_scraper.py
./library import-ratings
./library --user madeleine import-ratings
./library recommend
```

---

### `./library list`

Lists all books in the database with personal fields scoped to the active user.

```bash
./library list
./library list --limit 100
./library list --rated        # only books you've rated
```

---

## Module Reference

### `catalog_scraper.py`

Queries `gateway.bibliocommons.com/v2/libraries/sno-isle/bibs/search` page by page and upserts books directly into `library.db`. Uses `tqdm` for progress bars. Stores `metadata_id` (the BiblioCommons bib ID) on each book, which is required for hold placement.

### `hold.py`

Handles availability lookup, authentication, and hold submission against the BiblioCommons API. Functions: `get_availability()`, `login()`, `get_account_id()`, `get_branches()`, `place_hold()`, `hold_book()`, `get_holds()`, `get_checkouts()`.

`get_availability(metadata_id)` is unauthenticated — it returns per-copy branch name, collection, call number, and shelf status. `get_holds()` and `get_checkouts()` return live account data using `_gateway_get()`, which retries across NERF load-balancer backends to handle session replication lag. All authenticated functions require credentials from `.env`.

### `explore_catalog.py`

Queries the BiblioCommons API and prints all available filter fields with counts. Use before scraping to understand what's available.

### `cli.py`

Entry point. Uses [Click](https://click.palletsprojects.com/) for commands and [Rich](https://rich.readthedocs.io/) for display. Calls into `db.py`, `hold.py`, and `recommender.py`. The `--user` global option is resolved here and passed to all database and recommender calls.

### `db.py`

All database reads and writes. Uses Python's built-in `sqlite3`. No ORM. All personal-data functions accept a `user` parameter to scope ratings and checkouts.

| Function | Description |
|----------|-------------|
| `init_db()` | Creates tables and runs migrations. Called on every CLI invocation. |
| `upsert_book(data)` | Inserts or updates a book matched by title + author. |
| `get_all_books(user)` | Returns every book with personal fields scoped to the user. |
| `get_book(book_id, user)` | Returns a single book by ID with user-scoped personal fields. |
| `get_checked_out_unrated(user)` | Returns books with open checkout records and no rating for this user. |
| `add_checkout(book_id, user)` | Creates a checkout record for this user. |
| `record_rating(checkout_id, rating)` | Saves a rating; user is inferred from the checkout record. |
| `rate_book_direct(book_id, rating, user)` | Creates a completed checkout + rating in one step. |
| `search_books(query, user, title, author)` | Search with optional field-specific filters. |
| `get_book_ids_by_metadata(metadata_ids)` | Returns `{metadata_id: book_id}` for a list of BiblioCommons bib IDs. |
| `get_book_ids_by_title_author(books)` | Fallback lookup returning `{(title, author): book_id}` for books not matched by metadata_id. |
| `get_ratings_by_book_ids(book_ids, user)` | Returns `{book_id: avg_rating}` for the given book ids and user. |
| `export_ratings(user)` | Returns all rating data for a user as a serialisable dict. |
| `import_ratings(data, user)` | Restores ratings from an export, matching books by title + author. |

**Database schema:**

```sql
books (
    id                     INTEGER PRIMARY KEY,
    title                  TEXT NOT NULL,
    author                 TEXT,
    description            TEXT,
    isbn                   TEXT,
    age_range              TEXT,
    genre                  TEXT,
    subject                TEXT,
    metadata_id            TEXT,              -- BiblioCommons bib ID (for holds)
    library_checkout_count INTEGER,           -- total copies held (popularity proxy)
    last_library_checkout  TEXT,
    date_added             TEXT,
    UNIQUE(title, author)
)

checkouts (
    id             INTEGER PRIMARY KEY,
    book_id        INTEGER,
    user           TEXT,                      -- which user checked this out
    checkout_date  TEXT,
    return_date    TEXT,
    rating         REAL,
    notes          TEXT
)

user_ratings (
    user                TEXT,                 -- user profile name
    book_id             INTEGER,
    avg_rating          REAL,                 -- average engagement rating for this user
    times_checked_out   INTEGER,              -- how many times this user checked it out
    PRIMARY KEY (user, book_id)
)
```

### `recommender.py`

Core recommendation engine using TF-IDF and cosine similarity from scikit-learn.

**Scoring:**
1. TF-IDF matrix built from all books (unigrams + bigrams, 5,000 features max) — text includes title, author, description, subject, genre, and age_range
2. Preference profile = mean TF-IDF vector of books rated ≥ 4 stars by the active user; falls back to mean of all checked-out books; falls back to zero vector (popularity-only) if no history
3. Content score = cosine similarity to preference profile
4. Popularity score = library checkout count normalized to 0–1
5. Final score = `0.6 × content + 0.4 × popularity`

Experimental picks are selected by highest `content − popularity` gap (similar to liked books but rarely checked out). Hidden gems are the three lowest absolute checkout counts across the whole catalog.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `click` | CLI framework |
| `rich` | Terminal formatting |
| `requests` | HTTP — scraper and hold placement |
| `tqdm` | Progress bars in the scraper |
| `scikit-learn` | TF-IDF and cosine similarity |
| `numpy` | Matrix math |
| `sqlite3` | Built-in — database storage |
