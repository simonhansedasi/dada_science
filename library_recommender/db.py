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
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            metadata_id TEXT    NOT NULL UNIQUE,
            title       TEXT    NOT NULL,
            subtitle    TEXT,
            author      TEXT,
            series_name TEXT,
            description TEXT,
            isbn        TEXT,
            age_range   TEXT,
            genre       TEXT,
            subject     TEXT,
            library_checkout_count INTEGER DEFAULT 0,
            last_library_checkout  TEXT,
            date_added             TEXT DEFAULT (date('now'))
        );

        CREATE TABLE IF NOT EXISTS checkouts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id       INTEGER NOT NULL,
            user          TEXT    NOT NULL DEFAULT 'default',
            checkout_date TEXT    DEFAULT (date('now')),
            return_date   TEXT,
            rating        REAL,
            notes         TEXT,
            FOREIGN KEY (book_id) REFERENCES books(id)
        );

        CREATE TABLE IF NOT EXISTS user_ratings (
            user                TEXT    NOT NULL,
            book_id             INTEGER NOT NULL,
            avg_rating          REAL,
            times_checked_out   INTEGER DEFAULT 0,
            times_read          INTEGER DEFAULT 0,
            reread_demands      INTEGER DEFAULT 0,
            false_starts        INTEGER DEFAULT 0,
            currently_checked_out INTEGER DEFAULT 0,
            PRIMARY KEY (user, book_id),
            FOREIGN KEY (book_id) REFERENCES books(id)
        );
    """)
    conn.commit()
    conn.close()


def upsert_book(data: dict) -> int:
    """Insert or update a book by metadata_id. Returns the book id."""
    conn = get_conn()
    cols = list(data.keys())
    placeholders = ", ".join(["?"] * len(cols))
    update_clause = ", ".join(
        f"{c} = excluded.{c}" for c in cols if c != "metadata_id"
    )
    sql = f"""
        INSERT INTO books ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(metadata_id) DO UPDATE SET {update_clause}
    """
    cur = conn.execute(sql, list(data.values()))
    conn.commit()
    book_id = cur.lastrowid
    if not book_id:
        row = conn.execute(
            "SELECT id FROM books WHERE metadata_id = ?", (data.get("metadata_id"),)
        ).fetchone()
        book_id = row["id"] if row else book_id
    conn.close()
    return book_id


def get_all_books(user: str = "default"):
    conn = get_conn()
    rows = conn.execute("""
        SELECT b.*,
               COALESCE(ur.avg_rating,            NULL) AS avg_rating,
               COALESCE(ur.times_checked_out,     0)    AS times_checked_out,
               COALESCE(ur.times_read,            0)    AS times_read,
               COALESCE(ur.reread_demands,        0)    AS reread_demands,
               COALESCE(ur.false_starts,          0)    AS false_starts,
               COALESCE(ur.currently_checked_out, 0)    AS currently_checked_out
        FROM books b
        LEFT JOIN user_ratings ur ON ur.book_id = b.id AND ur.user = ?
        ORDER BY b.title
    """, (user,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_book(book_id: int, user: str = "default"):
    conn = get_conn()
    row = conn.execute("""
        SELECT b.*,
               COALESCE(ur.avg_rating,        NULL) AS avg_rating,
               COALESCE(ur.times_checked_out, 0)    AS times_checked_out,
               COALESCE(ur.times_read,        0)    AS times_read,
               COALESCE(ur.reread_demands,    0)    AS reread_demands,
               COALESCE(ur.false_starts,      0)    AS false_starts
        FROM books b
        LEFT JOIN user_ratings ur ON ur.book_id = b.id AND ur.user = ?
        WHERE b.id = ?
    """, (user, book_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_checked_out_unrated(user: str = "default"):
    conn = get_conn()
    rows = conn.execute("""
        SELECT b.id, b.title, b.subtitle, b.author, c.id as checkout_id
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


def log_read(book_id: int, user: str = "default", count: int = 1):
    conn = get_conn()
    conn.execute("""
        INSERT INTO user_ratings (user, book_id, times_read)
        VALUES (?, ?, ?)
        ON CONFLICT(user, book_id) DO UPDATE SET times_read = times_read + ?
    """, (user, book_id, count, count))
    conn.commit()
    conn.close()


def log_reread_demand(book_id: int, user: str = "default", count: int = 1):
    conn = get_conn()
    conn.execute("""
        INSERT INTO user_ratings (user, book_id, reread_demands)
        VALUES (?, ?, ?)
        ON CONFLICT(user, book_id) DO UPDATE SET reread_demands = reread_demands + ?
    """, (user, book_id, count, count))
    conn.commit()
    conn.close()


def log_false_start(book_id: int, user: str = "default", count: int = 1):
    conn = get_conn()
    conn.execute("""
        INSERT INTO user_ratings (user, book_id, false_starts)
        VALUES (?, ?, ?)
        ON CONFLICT(user, book_id) DO UPDATE SET false_starts = false_starts + ?
    """, (user, book_id, count, count))
    conn.commit()
    conn.close()


def export_ratings(user: str = "default"):
    conn = get_conn()
    checkouts = [dict(r) for r in conn.execute(
        "SELECT c.*, b.title, b.author FROM checkouts c "
        "JOIN books b ON b.id = c.book_id WHERE c.user = ?",
        (user,)
    ).fetchall()]
    book_ratings = [dict(r) for r in conn.execute(
        "SELECT b.title, b.subtitle, b.author, b.metadata_id, "
        "ur.avg_rating, ur.times_checked_out, "
        "ur.times_read, ur.reread_demands, ur.false_starts "
        "FROM user_ratings ur JOIN books b ON b.id = ur.book_id WHERE ur.user = ?",
        (user,)
    ).fetchall()]
    conn.close()
    return {"user": user, "checkouts": checkouts, "book_ratings": book_ratings}


def import_ratings(data: dict, user: str = "default"):
    """Restore ratings from export_ratings(). Matches by metadata_id first, then title+author."""
    conn = get_conn()
    restored = skipped = 0

    for br in data.get("book_ratings", []):
        row = None
        if br.get("metadata_id"):
            row = conn.execute(
                "SELECT id FROM books WHERE metadata_id = ?", (br["metadata_id"],)
            ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT id FROM books WHERE title = ? AND author = ?",
                (br["title"], br["author"])
            ).fetchone()
        if not row:
            skipped += 1
            continue
        conn.execute("""
            INSERT INTO user_ratings (user, book_id, avg_rating, times_checked_out,
                                      times_read, reread_demands, false_starts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user, book_id) DO UPDATE SET
                avg_rating        = excluded.avg_rating,
                times_checked_out = excluded.times_checked_out,
                times_read        = excluded.times_read,
                reread_demands    = excluded.reread_demands,
                false_starts      = excluded.false_starts
        """, (user, row["id"], br["avg_rating"], br["times_checked_out"],
              br.get("times_read", 0), br.get("reread_demands", 0), br.get("false_starts", 0)))
        restored += 1

    conn.commit()
    conn.close()
    return restored, skipped


def upsert_ratings_partial(user: str, book_id: int, **fields):
    """SET-semantics upsert into user_ratings; only updates columns explicitly provided."""
    if not fields:
        return
    col_names = list(fields.keys())
    placeholders = ", ".join("?" * len(col_names))
    all_cols = ", ".join(["user", "book_id"] + col_names)
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in col_names)
    conn = get_conn()
    conn.execute(f"""
        INSERT INTO user_ratings ({all_cols})
        VALUES (?, ?, {placeholders})
        ON CONFLICT(user, book_id) DO UPDATE SET {update_clause}
    """, [user, book_id] + list(fields.values()))
    conn.commit()
    conn.close()


def sync_currently_checked_out(book_ids: list, user: str = "default"):
    conn = get_conn()
    conn.execute(
        "UPDATE user_ratings SET currently_checked_out = 0 WHERE user = ?", (user,)
    )
    for book_id in book_ids:
        conn.execute("""
            INSERT INTO user_ratings (user, book_id, currently_checked_out)
            VALUES (?, ?, 1)
            ON CONFLICT(user, book_id) DO UPDATE SET currently_checked_out = 1
        """, (user, book_id))
    conn.commit()
    conn.close()


def get_ratings_by_book_ids(book_ids: list, user: str = "default") -> dict:
    if not book_ids:
        return {}
    conn = get_conn()
    placeholders = ",".join("?" * len(book_ids))
    rows = conn.execute(
        f"SELECT book_id, avg_rating, times_read, reread_demands, false_starts "
        f"FROM user_ratings "
        f"WHERE user = ? AND book_id IN ({placeholders})",
        [user] + list(book_ids)
    ).fetchall()
    conn.close()
    return {r["book_id"]: dict(r) for r in rows}


def get_book_ids_by_metadata(metadata_ids: list) -> dict:
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


def get_book_ids_by_title_author(books: list) -> dict:
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


def search_books(query: str = None, user: str = "default",
                 title: str = None, author: str = None):
    conn = get_conn()
    conditions = []
    params = [user]

    if query:
        conditions.append(
            "(b.title LIKE ? OR b.subtitle LIKE ? OR b.author LIKE ? "
            "OR b.series_name LIKE ? OR b.description LIKE ? OR b.subject LIKE ?)"
        )
        like = f"%{query}%"
        params += [like, like, like, like, like, like]

    if title:
        conditions.append("(b.title LIKE ? OR b.subtitle LIKE ?)")
        params += [f"%{title}%", f"%{title}%"]

    if author:
        conditions.append("b.author LIKE ?")
        params.append(f"%{author}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = conn.execute(f"""
        SELECT b.*,
               COALESCE(ur.avg_rating,        NULL) AS avg_rating,
               COALESCE(ur.times_checked_out, 0)    AS times_checked_out,
               COALESCE(ur.times_read,        0)    AS times_read,
               COALESCE(ur.reread_demands,    0)    AS reread_demands,
               COALESCE(ur.false_starts,      0)    AS false_starts
        FROM books b
        LEFT JOIN user_ratings ur ON ur.book_id = b.id AND ur.user = ?
        {where}
        ORDER BY b.title
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
