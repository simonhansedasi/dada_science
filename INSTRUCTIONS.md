# Library Recommender — Quick Reference

## Setup (first time only)

```bash
cd ~/coding/library_recommender
pip install -r requirements.txt
```

---

## Daily Use

### Import your library CSV
```bash
./library import-csv /path/to/library_inventory.csv
```
Run with `--dry-run` first to preview column detection without importing:
```bash
./library import-csv /path/to/library_inventory.csv --dry-run
```

### Get recommendations
```bash
./library recommend
```
Returns 10 books:
- **5 Top matches** — best fit for your child based on past ratings + popularity
- **2 Experimental** — similar to liked books but rarely checked out
- **3 Hidden gems** — lowest checkout count in the library

### Check out a book
```bash
./library checkout <id>
```
The `<id>` is the number shown next to each book in `recommend` or `list`.

### Rate books (after returning them)
```bash
./library rate
```
Prompts you to give each checked-out book a score 1–5 based on your child's engagement. Press `s` to skip any book.

**Rating scale:**
| Stars | Meaning |
|-------|---------|
| 1 | No interest / pushed it away |
| 2 | Tolerated it |
| 3 | Liked it |
| 4 | Asked for it again |
| 5 | Totally engaged, must re-read |

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
| `cli.py` | Main CLI entry point |
| `db.py` | Database operations |
| `importer.py` | CSV parsing and field detection |
| `recommender.py` | Recommendation engine |

> **Backup tip:** Copy `library.db` to keep your rating history safe.

---

## CSV Format

The importer is flexible and auto-detects columns. At minimum, your CSV needs a **Title** column. The more data you have, the better the recommendations.

Recognized column names (case-insensitive):

| Field | Accepted column names |
|-------|-----------------------|
| Title | `title`, `book title`, `item title` |
| Author | `author`, `creator`, `by` |
| Description | `description`, `summary`, `synopsis`, `annotation` |
| ISBN | `isbn`, `isbn13`, `isbn-13` |
| Age Range | `age range`, `age`, `reading level`, `audience` |
| Genre | `genre`, `category`, `format` |
| Subject/Tags | `subject`, `topics`, `tags`, `keywords` |
| Checkout Count | `checkout count`, `checkouts`, `circ count`, `circs`, `total checkouts` |
| Last Checkout | `last checkout`, `last circ`, `last activity` |

Any unrecognized columns are stored as supplemental subject data and used in recommendations.

---

## Tips

- Re-import the same CSV anytime to update checkout counts — existing ratings are preserved.
- The recommendation engine improves significantly after 5+ rated books.
- Use `search` to find a book's ID before checking it out.
- You can rate books 0.5 increments (e.g., `3.5`).
