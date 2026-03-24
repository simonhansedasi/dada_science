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
            -- user data
            times_checked_out INTEGER DEFAULT 0,
            avg_rating REAL,
            date_added TEXT DEFAULT (date('now')),
            UNIQUE(title, author)
        );

        CREATE TABLE IF NOT EXISTS checkouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            checkout_date TEXT DEFAULT (date('now')),
            return_date TEXT,
            rating REAL,
            notes TEXT,
            FOREIGN KEY (book_id) REFERENCES books(id)
        );
    """)
    conn.commit()

    # Migrations — safe to re-run, silently skipped if column already exists
    for migration in [
        "ALTER TABLE books ADD COLUMN metadata_id TEXT",
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
    # If updated (not inserted), fetch the real id
    if book_id == 0 or cur.rowcount == 0:
        row = conn.execute(
            "SELECT id FROM books WHERE title = ? AND author = ?",
            (data.get("title"), data.get("author"))
        ).fetchone()
        book_id = row["id"] if row else book_id
    conn.close()
    return book_id


def get_all_books():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM books ORDER BY title").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_book(book_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_checked_out_unrated():
    """Books currently checked out with no rating yet."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT b.id, b.title, b.author, c.id as checkout_id
        FROM checkouts c
        JOIN books b ON b.id = c.book_id
        WHERE c.return_date IS NULL AND c.rating IS NULL
        ORDER BY c.checkout_date
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_checkout(book_id: int):
    conn = get_conn()
    conn.execute(
        "INSERT INTO checkouts (book_id) VALUES (?)", (book_id,)
    )
    conn.execute(
        "UPDATE books SET times_checked_out = times_checked_out + 1 WHERE id = ?",
        (book_id,)
    )
    conn.commit()
    conn.close()


def record_rating(checkout_id: int, rating: float):
    conn = get_conn()
    conn.execute(
        "UPDATE checkouts SET rating = ?, return_date = date('now') WHERE id = ?",
        (rating, checkout_id)
    )
    # Recalculate avg_rating for the book
    conn.execute("""
        UPDATE books SET avg_rating = (
            SELECT AVG(rating) FROM checkouts
            WHERE book_id = books.id AND rating IS NOT NULL
        )
        WHERE id = (SELECT book_id FROM checkouts WHERE id = ?)
    """, (checkout_id,))
    conn.commit()
    conn.close()


def rate_book_direct(book_id: int, rating: float):
    """Create a completed checkout record with a rating in one step.
    Used for seeding ratings without going through the checkout flow."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO checkouts (book_id, checkout_date, return_date, rating)
           VALUES (?, date('now'), date('now'), ?)""",
        (book_id, rating)
    )
    conn.execute(
        "UPDATE books SET times_checked_out = times_checked_out + 1 WHERE id = ?",
        (book_id,)
    )
    conn.execute("""
        UPDATE books SET avg_rating = (
            SELECT AVG(rating) FROM checkouts
            WHERE book_id = ? AND rating IS NOT NULL
        ) WHERE id = ?
    """, (book_id, book_id))
    conn.commit()
    conn.close()


def search_books(query: str):
    conn = get_conn()
    like = f"%{query}%"
    rows = conn.execute("""
        SELECT * FROM books
        WHERE title LIKE ? OR author LIKE ? OR description LIKE ? OR subject LIKE ?
        ORDER BY title
    """, (like, like, like, like)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
