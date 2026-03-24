# Library Recommender

A command-line tool that helps you pick the best books to check out from the library for your toddler. You feed it a CSV export of your library's catalog (with checkout counts, descriptions, and other metadata), and it learns your child's taste from engagement ratings you give after each visit. Over time it gets smarter about what to suggest.

Built for a 2-year-old whose parent rates books 1–5 based on how engaged the child is during read-aloud sessions.

---

## Plain Language Summary

You import your library's book catalog as a CSV file. The tool stores everything in a local database file (`library.db`). When you get recommendations, it shows you 10 books split into three groups: the best overall matches, a couple of "wild card" picks that are similar to what your child loved but that most people overlook, and three books that almost nobody checks out (pure discovery). After each library trip, you rate the books you returned, and the system uses those ratings to get better at predicting what your child will engage with next time.

---

## Project Structure

```
library_recommender/
├── cli.py            CLI entry point — all commands live here
├── db.py             Database layer — reads and writes to library.db
├── importer.py       CSV parser — flexible field detection and import
├── recommender.py    Recommendation engine — scoring and ranking logic
├── library           Shell wrapper so you can run ./library <command>
├── library.db        SQLite database (created on first run)
├── requirements.txt  Python dependencies
├── INSTRUCTIONS.md   Quick reference for daily use
└── README.md         This file
```

---

## CLI Commands

### `./library import-csv <path>`

Imports a library catalog CSV into the database. Existing books are updated (checkout counts refreshed); your ratings and checkout history are never overwritten.

**Options:**
- `--dry-run` — shows the detected column mapping without writing anything to the database. Use this first when trying a new CSV format.

**What it does:**
1. Reads the CSV and scans column headers.
2. Maps headers to known fields using a flexible name-matching list (e.g., `circs`, `circ count`, and `total checkouts` all map to the checkout count field).
3. Any columns it doesn't recognize are stored as supplemental subject text, which still gets used in content-based recommendations.
4. Inserts new books or updates existing ones by matching on title + author.

---

### `./library recommend`

Displays 10 book recommendations in three categories.

**The three categories:**

| Category | Count | How it's chosen |
|----------|-------|-----------------|
| Top matches | 5 | Highest combined score: content similarity to your liked books (60%) + library popularity (40%) |
| Experimental | 2 | High content similarity to liked books but low library checkout count — books that *should* interest your child based on past ratings, but that most people skip |
| Hidden gems | 3 | Lowest library checkout counts in the entire catalog |

**How the content score works:**

The engine converts each book's title, description, subject, and genre into a numerical fingerprint using TF-IDF (a standard text analysis technique). It then finds the "average fingerprint" of all books your child rated 4 or 5 stars, and measures how similar each unread book is to that average. Books that haven't been rated yet default to popularity-only scoring.

**What's shown per book:**
- Title, author, age range, genre
- Library checkout count
- Your average rating (if previously read)
- Description excerpt
- Match score (for top/experimental picks)

---

### `./library checkout <id>`

Marks a book as currently checked out. The `<id>` is the number shown next to book titles in `recommend`, `list`, and `search` output.

**What it does:**
- Creates a checkout record with today's date.
- Increments the book's personal checkout counter.
- The book will now appear in the `rate` prompt when you return it.

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

Decimal values are accepted (e.g., `3.5`). Press `s` to skip a book without rating it — it will appear again next time you run `rate`.

**What it does behind the scenes:**
- Records the rating and sets the return date to today.
- Recalculates the book's average rating across all sessions.
- The updated average is immediately used in the next `recommend` call.

---

### `./library search <query>`

Searches the catalog by title, author, description, or subject. Returns a table showing each match with its ID, author, library checkout count, your average rating, and how many times you've personally checked it out.

```bash
./library search "bedtime"
./library search "Eric Carle"
./library search "animals"
```

---

### `./library list`

Lists all books in the database as a table.

**Options:**
- `--rated` — filter to only books you've given a rating.
- `--limit <n>` — how many rows to show (default: 20).

```bash
./library list --limit 100
./library list --rated
```

---

## Module Reference

### `cli.py`

The entry point. Uses [Click](https://click.palletsprojects.com/) to define all commands. Handles display formatting with [Rich](https://rich.readthedocs.io/). Calls into `db.py`, `importer.py`, and `recommender.py` — contains no business logic itself.

---

### `db.py`

All database reads and writes. Uses Python's built-in `sqlite3` module. No ORM.

| Function | Description |
|----------|-------------|
| `init_db()` | Creates the `books` and `checkouts` tables if they don't exist. Called automatically on every CLI invocation. |
| `upsert_book(data)` | Inserts a new book or updates an existing one matched by title + author. Returns the book's ID. |
| `get_all_books()` | Returns every book in the database as a list of dicts. |
| `get_book(book_id)` | Returns a single book by ID, or `None` if not found. |
| `get_checked_out_unrated()` | Returns all books that have an open checkout record with no rating yet. Used by the `rate` command. |
| `add_checkout(book_id)` | Creates a checkout record and increments the book's personal checkout counter. |
| `record_rating(checkout_id, rating)` | Saves a rating to a checkout record, sets the return date to today, and recalculates the book's average rating. |
| `search_books(query)` | Full-text search across title, author, description, and subject using SQL `LIKE`. |

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
    library_checkout_count INTEGER,   -- from library CSV
    last_library_checkout  TEXT,      -- from library CSV
    times_checked_out      INTEGER,   -- your personal checkout count
    avg_rating             REAL,      -- your average engagement rating
    date_added             TEXT
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

---

### `importer.py`

Reads a CSV and maps its columns to the internal schema using a fuzzy name-matching dictionary. Handles messy real-world library exports where column names vary between systems.

| Function | Description |
|----------|-------------|
| `detect_columns(df)` | Scans DataFrame column names against a dictionary of known aliases for each internal field. Returns a mapping of `internal_field → csv_column` and a list of unrecognized columns. |
| `import_csv(path, dry_run)` | Orchestrates the full import: loads CSV, detects columns, shows a mapping table, then iterates rows calling `upsert_book()`. Unrecognized columns are appended to the subject field so their text is still used in recommendations. |

**Recognized field aliases** (partial list):

- Checkout count: `checkout count`, `checkouts`, `circ count`, `circs`, `circulation count`, `total checkouts`, `total holds`
- Description: `description`, `summary`, `synopsis`, `abstract`, `annotation`
- Age range: `age range`, `age`, `reading level`, `audience`, `grade`

---

### `recommender.py`

The core recommendation engine. Uses TF-IDF vectorization and cosine similarity from [scikit-learn](https://scikit-learn.org/).

| Function | Description |
|----------|-------------|
| `_build_text(book)` | Concatenates a book's title, author, description, subject, genre, and age range into a single lowercase string for vectorization. |
| `recommend()` | Main function. Builds the TF-IDF matrix, constructs a preference profile, scores all unread candidates, and returns the three recommendation buckets. Returns `(result_dict, error_string)` — error is `None` on success. |

**Scoring breakdown:**

1. **TF-IDF matrix** — built from all books in the database using unigrams and bigrams, capped at 5,000 features.
2. **Preference profile** — the mean TF-IDF vector of all books rated ≥ 4 stars. Falls back to all checked-out books if no 4+ ratings exist yet. If no books have been checked out at all, content scoring is skipped and ranking is purely by popularity.
3. **Content score** — cosine similarity between each candidate book and the preference profile (0 to 1).
4. **Popularity score** — library checkout count normalized to 0–1 relative to the most-checked-out book in the candidate pool.
5. **Final score** — `0.6 × content_score + 0.4 × popularity_score`
6. **Experimental picks** — re-sorted by `content_score − popularity_score` to find books that match your taste profile but are underexposed in the library.
7. **Hidden gems** — simply the three candidates with the lowest `library_checkout_count`, regardless of content score.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `click` | CLI framework — argument parsing, commands, prompts |
| `rich` | Terminal formatting — tables, panels, colored output |
| `pandas` | CSV reading and data handling |
| `scikit-learn` | TF-IDF vectorization and cosine similarity |
| `numpy` | Matrix math used by the recommendation engine |
| `sqlite3` | Built-in Python — database storage (no install needed) |
