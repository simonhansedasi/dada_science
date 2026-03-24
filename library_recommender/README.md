# Library Recommender

A command-line tool that helps you pick the best books to check out from the library for your toddler. It scrapes the Sno-Isle library catalog directly into a local database, learns your child's taste from engagement ratings you give after each visit, and can place holds on recommended books from the command line.

Built for a 2-year-old whose parent rates books 1–5 based on how engaged the child is during read-aloud sessions.

---

## Plain Language Summary

Run the scraper to pull the Sno-Isle catalog into a local database (`library.db`). When you get recommendations, it shows you 10 books split into three groups: the best overall matches, a couple of "wild card" picks that are similar to what your child loved but that most people overlook, and three books that almost nobody checks out (pure discovery). When you find something you want, place a hold directly from the command line. After each library trip, rate the books you returned, and the system uses those ratings to get better at predicting what your child will engage with next time.

---

## Project Structure

```
library_recommender/
├── cli.py               CLI entry point — all commands live here
├── db.py                Database layer — reads and writes to library.db
├── recommender.py       Recommendation engine — scoring and ranking logic
├── catalog_scraper.py   Scraper — pulls Sno-Isle catalog directly into library.db
├── hold.py              Hold placement — login, account resolution, hold submission
├── explore_catalog.py   Catalog explorer — shows available filter fields and counts
├── Untitled.ipynb       Scraper notebook — exploration / raw API inspection
├── library              Shell wrapper so you can run ./library <command>
├── library.db           SQLite database (created on first run)
├── requirements.txt     Python dependencies
├── INSTRUCTIONS.md      Quick reference for daily use
└── README.md            This file
```

---

## Credentials

Edit `.env` in the project directory:

```
SNOISLE_CARD=your_card_number
SNOISLE_PIN=your_pin
SNOISLE_BRANCH=your_default_branch_id   # optional — skips the branch prompt
```

This file is already in `.gitignore` and will never be committed. The `hold` command reads all three automatically — no `export` needed. Run `./library hold <id>` without `--branch` once to see the full branch list with IDs if you don't know yours.

---

## Getting a Catalog

The recommender needs books in the database before it can recommend anything.

### 1. Explore what's available (optional)

```bash
python explore_catalog.py                                   # full overview of all filter fields
python explore_catalog.py --audience JUVENILE --format BK  # scope to children's physical books
```

Shows every available filter value and how many books match, so you can decide what to scrape.

### 2. Scrape into the database

```bash
python catalog_scraper.py                  # full run — ~165k physical books, all ages (~45 min)
python catalog_scraper.py --max-pages 2    # quick test (~3,600 books)
```

Re-run anytime to refresh checkout counts and pick up new titles. Ratings and personal checkout history are never overwritten. Any pages that fail are written to `failed_pages.csv` for inspection.

| Flag | Default | Description |
|------|---------|-------------|
| `--max-pages N` | all | Stop after N pages per query prefix |

---

## CLI Commands

### `./library recommend [--age AUDIENCE]`

Displays 10 book recommendations in three categories.

```bash
./library recommend              # all ages
./library recommend --age juvenile
./library recommend --age adult
./library recommend --age teen
```

`--age` is a case-insensitive substring match against the BiblioCommons audience field. When set, the TF-IDF profile and all scoring are scoped to that audience only.

**The three categories:**

| Category | Count | How it's chosen |
|----------|-------|-----------------|
| Top matches | 5 | Highest combined score: content similarity to your liked books (60%) + library popularity (40%) |
| Experimental | 2 | High content similarity to liked books but low library checkout count |
| Hidden gems | 3 | Lowest library checkout counts in the entire catalog |

**How the content score works:**

The engine converts each book's title, description, subject, and genre into a numerical fingerprint using TF-IDF. It then finds the "average fingerprint" of all books your child rated 4 or 5 stars, and measures how similar each unread book is to that average. Books that haven't been rated yet default to popularity-only scoring.

---

### `./library hold <id>`

Places a hold on a book at Sno-Isle for library pickup.

```bash
./library hold 42              # prompts for pickup branch interactively
./library hold 42 --branch 18  # Lynnwood Library directly
```

**What it does:**
1. Fetches live copy availability (unauthenticated) — shows which branches have the book and whether each copy is on the shelf or checked out
2. Logs into `sno-isle.bibliocommons.com` using your card and PIN from `.env`
3. Resolves your `accountId` from the BiblioCommons API
4. POSTs a hold to `gateway.bibliocommons.com/v2/libraries/sno-isle/holds`

Credentials are read from `.env` automatically — see the Credentials section above.

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

### `./library checkout <id>`

Records a book as currently checked out locally. The `<id>` is the number shown in `recommend`, `list`, or `search`.

- Creates a checkout record with today's date.
- Increments the book's personal checkout counter.
- The book will appear in the `rate` prompt when you return it.

```bash
./library checkout 7
```

---

### `./library rate`

Interactively prompts you to rate every book that is currently checked out and hasn't been rated yet.

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

### `./library search <query>`

Searches the catalog by title, author, description, or subject.

```bash
./library search "bedtime"
./library search "Eric Carle"
./library search "animals"
```

---

### `./library availability <id>`

Shows live copy availability for a book — no login required.

```bash
./library availability 42
```

Lists every copy in the Sno-Isle system with branch name, collection, call number, and shelf status (On Shelf / Checked Out / etc).

---

### `./library my-account`

Logs into your Sno-Isle account and displays your current holds and checkouts.

```bash
./library my-account
```

Shows:
- **Holds** — title, status, queue position, pickup branch, pickup-by / expiry dates
- **Checkouts** — title, due date, overdue status, renewable flag

Reads credentials from `.env` automatically.

---

### `./library rate-book`

Rate a book directly without going through the checkout flow. Useful for seeding ratings on books you've already read.

```bash
./library rate-book              # interactive: search → pick → rate, repeat
./library rate-book <id> <score> # one-liner
```

---

### `./library list`

Lists all books in the database as a table.

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

Queries the BiblioCommons API and prints all available filter fields with counts. Use before scraping to understand what's available. Accepts `--format`, `--audience`, `--genre`, `--topic`, `--language`, `--fiction`, `--circ` flags.

### `Untitled.ipynb`

Scraper notebook for exploration and raw API inspection. Saves to CSV — useful for one-off queries or examining raw API responses, but `catalog_scraper.py` is the right tool for populating the database.

### `cli.py`

Entry point. Uses [Click](https://click.palletsprojects.com/) for commands and [Rich](https://rich.readthedocs.io/) for display. Calls into `db.py`, `hold.py`, and `recommender.py`.

### `db.py`

All database reads and writes. Uses Python's built-in `sqlite3`. No ORM.

| Function | Description |
|----------|-------------|
| `init_db()` | Creates tables and runs migrations. Called on every CLI invocation. |
| `upsert_book(data)` | Inserts or updates a book matched by title + author. |
| `get_all_books()` | Returns every book as a list of dicts. |
| `get_book(book_id)` | Returns a single book by ID. |
| `get_checked_out_unrated()` | Returns books with open checkout records and no rating. |
| `add_checkout(book_id)` | Creates a checkout record and increments personal checkout count. |
| `record_rating(checkout_id, rating)` | Saves a rating and recalculates the book's average. |
| `search_books(query)` | Full-text search across title, author, description, and subject. |

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
    times_checked_out      INTEGER,           -- your personal checkout count
    avg_rating             REAL,              -- your average engagement rating
    date_added             TEXT,
    UNIQUE(title, author)
)

checkouts (
    id             INTEGER PRIMARY KEY,
    book_id        INTEGER,
    checkout_date  TEXT,
    return_date    TEXT,
    rating         REAL,
    notes          TEXT
)
```

### `recommender.py`

Core recommendation engine using TF-IDF and cosine similarity from scikit-learn.

**Scoring:**
1. TF-IDF matrix built from all books (unigrams + bigrams, 5,000 features max)
2. Preference profile = mean TF-IDF vector of books rated ≥ 4 stars
3. Content score = cosine similarity to preference profile
4. Popularity score = library checkout count normalized to 0–1
5. Final score = `0.6 × content + 0.4 × popularity`

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
