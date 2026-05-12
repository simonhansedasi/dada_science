#!/usr/bin/env python3
"""
catalog_scraper.py — Sno-Isle children's catalog scraper

Discovery strategy: subject-based enumeration of juvenile books (much smaller
and more targeted than the old a-z keyword sweep over the full 190k catalog).
Unique key is metadata_id — BiblioCommons' authoritative bib identifier — so
series volumes with identical titles but different subtitles are stored separately.

Usage:
    python catalog_scraper.py                  # full run
    python catalog_scraper.py --max-pages 5    # quick test
"""

import argparse
import queue
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from tqdm import tqdm

import db

BASE_URL = "https://gateway.bibliocommons.com/v2/libraries/sno-isle/bibs/search"
PER_PAGE = 100
WORKERS  = 20

# Subject queries that together cover the juvenile catalog.
# Deduplicated by metadata_id so overlaps are free.
SUBJECTS = [
    "picture books",
    "juvenile fiction",
    "board books",
    "easy readers",
    "beginning readers",
    "fairy tales",
    "folklore",
    "nursery rhymes",
    "alphabet books",
    "counting books",
    "concept books",
    "toy and movable books",
]

COMPARE_FIELDS = (
    "title", "subtitle", "author", "series_name",
    "description", "isbn", "genre", "subject",
    "age_range", "library_checkout_count",
)

_seen: set    = set()
_seen_lock    = threading.Lock()
_SENTINEL     = object()


# ── Network ───────────────────────────────────────────────────────────────────

def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
        "Origin":     "https://sno-isle.bibliocommons.com",
        "Referer":    "https://sno-isle.bibliocommons.com/",
    })
    return s


def _fetch(session, subject, page):
    r = session.get(BASE_URL, params={
        "query":      subject,
        "searchType": "subject",
        "limit":      PER_PAGE,
        "page":       page,
        "f_FORMAT":   "BK",
        "f_AUDIENCE": "juvenile",
    }, timeout=20)
    r.raise_for_status()
    return r.json()


# ── Extraction ────────────────────────────────────────────────────────────────

def _extract(data):
    books = []
    for bib_id, bib in data.get("entities", {}).get("bibs", {}).items():
        with _seen_lock:
            if bib_id in _seen:
                continue
            _seen.add(bib_id)

        info  = bib.get("briefInfo",   {})
        avail = bib.get("availability", {})

        def s(v): return (v or "").strip()

        authors  = info.get("authors") or []
        isbns    = info.get("isbns")   or []
        subjects = (
            (info.get("subjectHeadings")          or []) +
            (info.get("compositeSubjectHeadings") or [])
        )
        series_list = info.get("series") or []
        series_name = series_list[0].get("name", "") if series_list else ""

        copies = avail.get("totalCopies")
        try:
            checkout_count = int(copies) if copies is not None else 0
            if checkout_count >= 999999:
                checkout_count = 0
        except (TypeError, ValueError):
            checkout_count = 0

        title = s(info.get("title"))
        if not title:
            continue

        books.append({
            "metadata_id":            bib_id,
            "title":                  title,
            "subtitle":               s(info.get("subtitle")),
            "author":                 s(authors[0]) if authors else "",
            "series_name":            s(series_name),
            "description":            s(info.get("description")),
            "isbn":                   s(isbns[0]) if isbns else "",
            "genre":                  "; ".join(info.get("genreForm") or []),
            "subject":                "; ".join(dict.fromkeys(subjects)),
            "age_range":              "; ".join(info.get("audiences") or []),
            "library_checkout_count": checkout_count,
        })
    return books


# ── Database writer (single thread) ──────────────────────────────────────────

def _writer(q, pbar, bbar):
    inserted = updated = skipped = errors = 0
    failed_pages = []
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row

    while True:
        item = q.get()
        if item is _SENTINEL:
            break

        subject, page, books, err = item
        if err:
            errors += 1
            failed_pages.append((subject, page, err))
            pbar.update(1)
            continue

        if not books:
            pbar.update(1)
            continue

        meta_ids = [b["metadata_id"] for b in books]
        ph = ",".join("?" * len(meta_ids))
        rows = conn.execute(
            f"SELECT metadata_id, {', '.join(COMPARE_FIELDS)} "
            f"FROM books WHERE metadata_id IN ({ph})",
            meta_ids,
        ).fetchall()
        existing = {r["metadata_id"]: r for r in rows}

        for book in books:
            mid = book["metadata_id"]

            if mid in existing:
                row = existing[mid]
                changed = any(
                    str(book.get(f) or "") != str(row[f] or "")
                    for f in COMPARE_FIELDS
                )
                if not changed:
                    skipped += 1
                    continue
                updated += 1
            else:
                inserted += 1

            cols   = list(book.keys())
            ph2    = ", ".join(["?"] * len(cols))
            update = ", ".join(
                f"{c} = excluded.{c}" for c in cols if c != "metadata_id"
            )
            conn.execute(
                f"INSERT INTO books ({', '.join(cols)}) VALUES ({ph2}) "
                f"ON CONFLICT(metadata_id) DO UPDATE SET {update}",
                list(book.values()),
            )

        conn.commit()
        bbar.update(inserted + updated + skipped)
        pbar.set_postfix(
            new=f"{inserted:,}", upd=f"{updated:,}", skip=f"{skipped:,}"
        )
        pbar.update(1)

    conn.close()
    return inserted, updated, skipped, errors, failed_pages


# ── Fetch workers ─────────────────────────────────────────────────────────────

def _fetch_page(subject, page):
    sess = _session()
    for attempt in range(5):
        try:
            data  = _fetch(sess, subject, page)
            books = _extract(data)
            return subject, page, books, None
        except requests.exceptions.Timeout:
            wait = 2 ** attempt
            tqdm.write(f"  [{subject!r} p{page}] Timeout — retrying in {wait}s")
            time.sleep(wait)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            if status in (429, 503) or (isinstance(status, int) and status >= 500):
                wait = 2 ** attempt
                tqdm.write(f"  [{subject!r} p{page}] HTTP {status} — retrying in {wait}s")
                time.sleep(wait)
            else:
                tqdm.write(f"  [{subject!r} p{page}] HTTP {status} — skipping")
                return subject, page, [], str(e)
        except Exception as e:
            tqdm.write(f"  [{subject!r} p{page}] {type(e).__name__}: {e} — skipping")
            return subject, page, [], str(e)
    tqdm.write(f"  [{subject!r} p{page}] gave up after 5 attempts")
    return subject, page, [], "max retries"


def _probe(subject, max_pages):
    sess = _session()
    try:
        data       = _fetch(sess, subject, 1)
        pagination = data.get("catalogSearch", {}).get("pagination", {})
        total      = pagination.get("pages", 1)
        count      = pagination.get("count", 0)
        if max_pages:
            total = min(total, max_pages)
        return subject, total, count, _extract(data), None
    except Exception as e:
        tqdm.write(f"  [{subject!r} probe] {type(e).__name__}: {e}")
        return subject, 0, 0, [], str(e)


# ── Orchestration ─────────────────────────────────────────────────────────────

def scrape_all(max_pages=None):
    db.init_db()

    work = []
    page1_results = []

    tqdm.write(f"Probing {len(SUBJECTS)} subject queries...\n")
    with tqdm(total=len(SUBJECTS), desc="Probing ", unit="subject") as probe_bar:
        with ThreadPoolExecutor(max_workers=len(SUBJECTS)) as ex:
            futs = {ex.submit(_probe, s, max_pages): s for s in SUBJECTS}
            for fut in as_completed(futs):
                subj, total, count, books, err = fut.result()
                page1_results.append((subj, 1, books, err))
                for p in range(2, total + 1):
                    work.append((subj, p))
                probe_bar.set_postfix(subject=f"{subj!r}", books=f"{count:,}")
                probe_bar.update(1)

    total_pages = len(SUBJECTS) + len(work)
    tqdm.write(f"\n  {total_pages:,} total pages — fetching {len(work):,} more\n")

    result_q = queue.Queue(maxsize=WORKERS * 2)

    with tqdm(total=total_pages, desc="Pages   ", unit="pg") as pbar, \
         tqdm(total=0,           desc="Books   ", unit="bk",
              bar_format="{desc}: {n_fmt} [{elapsed}, {rate_fmt}]") as bbar:

        writer_result = {}

        def run_writer():
            ins, upd, skip, err, failed = _writer(result_q, pbar, bbar)
            writer_result.update(inserted=ins, updated=upd,
                                 skipped=skip, errors=err, failed=failed)

        writer_thread = threading.Thread(target=run_writer, daemon=True)
        writer_thread.start()

        for item in page1_results:
            result_q.put(item)

        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(_fetch_page, s, p): (s, p) for s, p in work}
            for fut in as_completed(futs):
                result_q.put(fut.result())

        result_q.put(_SENTINEL)
        writer_thread.join()

    r = writer_result
    failed = r.get("failed", [])
    print("\n" + "─" * 40)
    print(f"Inserted:    {r.get('inserted', 0):,}")
    print(f"Updated:     {r.get('updated',  0):,}")
    print(f"Skipped:     {r.get('skipped',  0):,}")
    print(f"Errors:      {r.get('errors',   0):,}")
    print(f"Unique seen: {len(_seen):,}")
    print("─" * 40)

    if failed:
        import pathlib, csv
        log_path = pathlib.Path(db.DB_PATH).with_name("failed_pages.csv")
        with log_path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["subject", "page", "error"])
            w.writerows(failed)
        print(f"\nFailed pages: {log_path}")


# ── Live lookup (used by add-book command) ────────────────────────────────────

def search_bibliocommons(query: str, search_type: str = "title", limit: int = 20) -> list:
    """Search BiblioCommons live. search_type: 'title' | 'author' | 'series' | 'keyword'"""
    sess = _session()
    r = sess.get(BASE_URL, params={
        "query":      query,
        "searchType": search_type,
        "limit":      limit,
        "page":       1,
        "f_FORMAT":   "BK",
    }, timeout=20)
    r.raise_for_status()
    data = r.json()

    books = []
    for bib_id, bib in data.get("entities", {}).get("bibs", {}).items():
        info        = bib.get("briefInfo",   {})
        avail       = bib.get("availability", {})
        authors     = info.get("authors") or []
        isbns       = info.get("isbns")   or []
        subjects    = (
            (info.get("subjectHeadings")          or []) +
            (info.get("compositeSubjectHeadings") or [])
        )
        series_list = info.get("series") or []
        series_name = series_list[0].get("name", "") if series_list else ""

        copies = avail.get("totalCopies")
        try:
            checkout_count = int(copies) if copies is not None else 0
            if checkout_count >= 999999:
                checkout_count = 0
        except (TypeError, ValueError):
            checkout_count = 0

        def s(v): return (v or "").strip()

        title = s(info.get("title"))
        if not title:
            continue

        books.append({
            "metadata_id":            bib_id,
            "title":                  title,
            "subtitle":               s(info.get("subtitle")),
            "author":                 s(authors[0]) if authors else "",
            "series_name":            s(series_name),
            "description":            s(info.get("description")),
            "isbn":                   s(isbns[0]) if isbns else "",
            "genre":                  "; ".join(info.get("genreForm") or []),
            "subject":                "; ".join(dict.fromkeys(subjects)),
            "age_range":              "; ".join(info.get("audiences") or []),
            "library_checkout_count": checkout_count,
        })

    books.sort(key=lambda b: b["library_checkout_count"], reverse=True)
    return books


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Sno-Isle juvenile catalog into library.db"
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Max pages per subject query — omit for full run",
    )
    args = parser.parse_args()
    print(f"Target: {db.DB_PATH}\n")
    scrape_all(max_pages=args.max_pages)


if __name__ == "__main__":
    main()
