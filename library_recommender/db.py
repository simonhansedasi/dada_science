import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "library.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            description TEXT,
            isbn TEXT,
            age_range TEXT,
            genre TEXT,
            subject TEXT,
            -- library data
            metadata_id TEXT,
            library_checkout_count INTEGER DEFAULT 0,
            last_library_checkout TEXT,
            -- legacy columns (superseded by user_ratings table)
            times_checked_out INTEGER DEFAULT 0,
            avg_rating REAL,
            date_added TEXT DEFAULT (date('now')),
            UNIQUE(title, author)
        );

        CREATE TABLE IF NOT EXISTS checkouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            user TEXT NOT NULL DEFAULT 'default',
            checkout_date TEXT DEFAULT (date('now')),
            return_date TEXT,
            rating REAL,
            notes TEXT,
            FOREIGN KEY (book_id) REFERENCES books(id)
        );

        CREATE TABLE IF NOT EXISTS user_ratings (
            user TEXT NOT NULL,
            book_id INTEGER NOT NULL,
            avg_rating REAL,
            times_checked_out INTEGER DEFAULT 0,
            PRIMARY KEY (user, book_id),
            FOREIGN KEY (book_id) REFERENCES books(id)
        );
    """)
    conn.commit()

    # Migrations — safe to re-run
    for migration in [
        "ALTER TABLE books ADD COLUMN metadata_id TEXT",
        "ALTER TABLE checkouts ADD COLUMN user TEXT NOT NULL DEFAULT 'default'",
    ]:
        try:
            conn.execute(migration)
            conn.commit()
        except Exception:
            pass  # column already exists

    conn.close()


def upsert_book(data: dict) -> int:
    """Insert or update a book. Returns the book id."""
    conn = get_conn()
    cols = list(data.keys())
    placeholders = ", ".join(["?" for _ in cols])
    update_clause = ", ".join([f"{c} = excluded.{c}" for c in cols if c not in ("title", "author")])
    sql = f"""
        INSERT INTO books ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(title, author) DO UPDATE SET {update_clause}
    """
    cur = conn.execute(sql, list(data.values()))
    conn.commit()
    book_id = cur.lastrowid
    if book_id == 0 or cur.rowcount == 0:
        row = conn.execute(
            "SELECT id FROM books WHERE title = ? AND author = ?",
            (data.get("title"), data.get("author"))
        ).fetchone()
        book_id = row["id"] if row else book_id
    conn.close()
    return book_id


def get_all_books(user: str = "default"):
    """Return all books with personal fields scoped to the given user."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT b.*,
               COALESCE(ur.avg_rating,        NULL) AS avg_rating,
               COALESCE(ur.times_checked_out, 0)    AS times_checked_out
        FROM books b
        LEFT JOIN user_ratings ur ON ur.book_id = b.id AND ur.user = ?
        ORDER BY b.title
    """, (user,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_book(book_id: int, user: str = "default"):
    """Return a single book with personal fields scoped to the given user."""
    conn = get_conn()
    row = conn.execute("""
        SELECT b.*,
               COALESCE(ur.avg_rating,        NULL) AS avg_rating,
               COALESCE(ur.times_checked_out, 0)    AS times_checked_out
        FROM books b
        LEFT JOIN user_ratings ur ON ur.book_id = b.id AND ur.user = ?
        WHERE b.id = ?
    """, (user, book_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_checked_out_unrated(user: str = "default"):
    """Books currently checked out by this user with no rating yet."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT b.id, b.title, b.author, c.id as checkout_id
        FROM checkouts c
        JOIN books b ON b.id = c.book_id
        WHERE c.user = ? AND c.return_date IS NULL AND c.rating IS NULL
        ORDER BY c.checkout_date
    """, (user,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_checkout(book_id: int, user: str = "default"):
    conn = get_conn()
    conn.execute(
        "INSERT INTO checkouts (book_id, user) VALUES (?, ?)", (book_id, user)
    )
    conn.execute("""
        INSERT INTO user_ratings (user, book_id, times_checked_out)
        VALUES (?, ?, 1)
        ON CONFLICT(user, book_id) DO UPDATE SET
            times_checked_out = times_checked_out + 1
    """, (user, book_id))
    conn.commit()
    conn.close()


def record_rating(checkout_id: int, rating: float):
    """Save a rating for a checkout. User is inferred from the checkout record."""
    conn = get_conn()
    checkout = conn.execute(
        "SELECT book_id, user FROM checkouts WHERE id = ?", (checkout_id,)
    ).fetchone()
    book_id, user = checkout["book_id"], checkout["user"]

    conn.execute(
        "UPDATE checkouts SET rating = ?, return_date = date('now') WHERE id = ?",
        (rating, checkout_id)
    )
    avg = conn.execute(
        "SELECT AVG(rating) FROM checkouts WHERE book_id = ? AND user = ? AND rating IS NOT NULL",
        (book_id, user)
    ).fetchone()[0]
    conn.execute("""
        INSERT INTO user_ratings (user, book_id, avg_rating)
        VALUES (?, ?, ?)
        ON CONFLICT(user, book_id) DO UPDATE SET avg_rating = excluded.avg_rating
    """, (user, book_id, avg))
    conn.commit()
    conn.close()


def rate_book_direct(book_id: int, rating: float, user: str = "default"):
    """Create a completed checkout with a rating in one step (seed ratings)."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO checkouts (book_id, user, checkout_date, return_date, rating) "
        "VALUES (?, ?, date('now'), date('now'), ?)",
        (book_id, user, rating)
    )
    avg = conn.execute(
        "SELECT AVG(rating) FROM checkouts WHERE book_id = ? AND user = ? AND rating IS NOT NULL",
        (book_id, user)
    ).fetchone()[0]
    conn.execute("""
        INSERT INTO user_ratings (user, book_id, avg_rating, times_checked_out)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user, book_id) DO UPDATE SET
            avg_rating = excluded.avg_rating,
            times_checked_out = times_checked_out + 1
    """, (user, book_id, avg))
    conn.commit()
    conn.close()


def export_ratings(user: str = "default"):
    """Return rating data for a single user as a serialisable dict."""
    conn = get_conn()
    checkouts = [dict(r) for r in conn.execute(
        "SELECT c.*, b.title, b.author FROM checkouts c "
        "JOIN books b ON b.id = c.book_id WHERE c.user = ?",
        (user,)
    ).fetchall()]
    book_ratings = [dict(r) for r in conn.execute(
        "SELECT b.title, b.author, ur.avg_rating, ur.times_checked_out "
        "FROM user_ratings ur JOIN books b ON b.id = ur.book_id WHERE ur.user = ?",
        (user,)
    ).fetchall()]
    conn.close()
    return {"user": user, "checkouts": checkouts, "book_ratings": book_ratings}


def import_ratings(data: dict, user: str = "default"):
    """Restore ratings from export_ratings(). Matches books by title + author.
    Returns (restored, skipped) counts."""
    conn = get_conn()
    restored = skipped = 0

    for br in data.get("book_ratings", []):
        row = conn.execute(
            "SELECT id FROM books WHERE title = ? AND author = ?",
            (br["title"], br["author"])
        ).fetchone()
        if not row:
            skipped += 1
            continue
        conn.execute("""
            INSERT INTO user_ratings (user, book_id, avg_rating, times_checked_out)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user, book_id) DO UPDATE SET
                avg_rating = excluded.avg_rating,
                times_checked_out = excluded.times_checked_out
        """, (user, row["id"], br["avg_rating"], br["times_checked_out"]))
        restored += 1

    for c in data.get("checkouts", []):
        row = conn.execute(
            "SELECT id FROM books WHERE title = ? AND author = ?",
            (c["title"], c["author"])
        ).fetchone()
        if not row:
            continue
        book_id = row["id"]
        exists = conn.execute(
            "SELECT id FROM checkouts WHERE book_id = ? AND user = ? "
            "AND checkout_date = ? AND rating IS ?",
            (book_id, user, c["checkout_date"], c["rating"])
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO checkouts (book_id, user, checkout_date, return_date, rating, notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (book_id, user, c["checkout_date"], c["return_date"], c["rating"], c.get("notes"))
            )

    conn.commit()
    conn.close()
    return restored, skipped


def get_ratings_by_book_ids(book_ids: list, user: str = "default") -> dict:
    """Return {book_id: avg_rating} for the given book_ids and user."""
    if not book_ids:
        return {}
    conn = get_conn()
    placeholders = ",".join("?" * len(book_ids))
    rows = conn.execute(
        f"SELECT book_id, avg_rating FROM user_ratings "
        f"WHERE user = ? AND book_id IN ({placeholders})",
        [user] + list(book_ids)
    ).fetchall()
    conn.close()
    return {r["book_id"]: r["avg_rating"] for r in rows}


def get_book_ids_by_title_author(books: list) -> dict:
    """
    Fallback lookup: match by (title, author) for books missing a metadata_id match.
    `books` is a list of dicts with at least 'title' and 'author' keys.
    Returns {(title, author): book_id}.
    """
    if not books:
        return {}
    conn = get_conn()
    result = {}
    for b in books:
        row = conn.execute(
            "SELECT id FROM books WHERE title = ? AND author = ?",
            (b["title"], b["author"])
        ).fetchone()
        if row:
            result[(b["title"], b["author"])] = row["id"]
    conn.close()
    return result


def get_book_ids_by_metadata(metadata_ids: list) -> dict:
    """Return {metadata_id: book_id} for the given metadata_ids."""
    if not metadata_ids:
        return {}
    conn = get_conn()
    placeholders = ",".join("?" * len(metadata_ids))
    rows = conn.execute(
        f"SELECT id, metadata_id FROM books WHERE metadata_id IN ({placeholders})",
        metadata_ids
    ).fetchall()
    conn.close()
    return {r["metadata_id"]: r["id"] for r in rows}


def search_books(query: str = None, user: str = "default",
                 title: str = None, author: str = None):
    """Search books. Filters are ANDed together.

    - query:  matches title, author, description, or subject
    - title:  matches title only
    - author: matches author only
    """
    conn = get_conn()
    conditions = []
    params = [user]

    if query:
        conditions.append(
            "(b.title LIKE ? OR b.author LIKE ? OR b.description LIKE ? OR b.subject LIKE ?)"
        )
        like = f"%{query}%"
        params += [like, like, like, like]

    if title:
        conditions.append("b.title LIKE ?")
        params.append(f"%{title}%")

    if author:
        conditions.append("b.author LIKE ?")
        params.append(f"%{author}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = conn.execute(f"""
        SELECT b.*,
               COALESCE(ur.avg_rating,        NULL) AS avg_rating,
               COALESCE(ur.times_checked_out, 0)    AS times_checked_out
        FROM books b
        LEFT JOIN user_ratings ur ON ur.book_id = b.id AND ur.user = ?
        {where}
        ORDER BY b.title
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
