#!/usr/bin/env python3
"""
catalog_scraper.py — Sno-Isle catalog scraper (parallel, change-only writes)

Probes all 36 query prefixes simultaneously, then fetches every page in one
shared thread pool. A single writer thread drains results from a queue so
fetch threads never block on the DB. Only writes rows that have changed.

Usage:
    python catalog_scraper.py                  # full run
    python catalog_scraper.py --max-pages 5    # quick test (~18k books)
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

BASE_URL  = "https://gateway.bibliocommons.com/v2/libraries/sno-isle/bibs/search"
PER_PAGE  = 100   # BiblioCommons max
WORKERS   = 30    # parallel fetch threads
QUERIES   = list("abcdefghijklmnopqrstuvwxyz0123456789")

# Fields we compare to decide whether a row needs updating
COMPARE_FIELDS = (
    "description", "isbn", "genre", "subject",
    "age_range", "library_checkout_count",
)

_seen: set       = set()
_seen_lock       = threading.Lock()
_SENTINEL        = object()   # signals writer to stop


# ── Network ──────────────────────────────────────────────────────────────────

def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
        "Origin":     "https://sno-isle.bibliocommons.com",
        "Referer":    "https://sno-isle.bibliocommons.com/",
    })
    return s


def _fetch(session, query, page):
    r = session.get(BASE_URL, params={
        "query":      query,
        "searchType": "keyword",
        "limit":      PER_PAGE,
        "page":       page,
        "f_FORMAT":   "BK",          # physical books only
    }, timeout=20)
    r.raise_for_status()
    return r.json()


# ── Extraction ────────────────────────────────────────────────────────────────

def _extract(data):
    """Pull books out of a raw API response, deduplicating by bib id."""
    books = []
    for bib_id, bib in data.get("entities", {}).get("bibs", {}).items():
        with _seen_lock:
            if bib_id in _seen:
                continue
            _seen.add(bib_id)

        info  = bib.get("briefInfo",   {})
        avail = bib.get("availability", {})

        def s(v): return (v or "").strip()

        authors  = info.get("authors")  or []
        isbns    = info.get("isbns")    or []
        subjects = (
            (info.get("subjectHeadings")          or []) +
            (info.get("compositeSubjectHeadings") or [])
        )

        copies = avail.get("totalCopies")
        try:
            checkout_count = int(copies) if copies is not None else 0
            if checkout_count >= 999999:   # BiblioCommons sentinel — not a real count
                checkout_count = 0
        except (TypeError, ValueError):
            checkout_count = 0

        title = s(info.get("title"))
        if not title:
            continue

        books.append({
            "title":                  title,
            "author":                 s(authors[0]) if authors else "",
            "description":            s(info.get("description")),
            "isbn":                   s(isbns[0]) if isbns else "",
            "genre":                  "; ".join(info.get("genreForm") or []),
            "subject":                "; ".join(dict.fromkeys(subjects)),
            "age_range":              "; ".join(info.get("audiences") or []),
            "library_checkout_count": checkout_count,
            "metadata_id":            s(info.get("metadataId")),
        })
    return books


# ── Database writer (single thread) ──────────────────────────────────────────

def _writer(q, pbar, bbar):
    """
    Drains the result queue and writes to SQLite on one thread —
    no lock contention, one connection for the whole run.
    """
    inserted = updated = skipped = errors = 0
    failed_pages = []
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row

    while True:
        item = q.get()
        if item is _SENTINEL:
            break

        query, page, books, err = item
        if err:
            errors += 1
            failed_pages.append((query, page, err))
            pbar.update(1)
            continue

        if not books:
            pbar.update(1)
            continue

        # Batch-fetch existing rows for all metadata_ids on this page
        meta_ids = [b["metadata_id"] for b in books if b.get("metadata_id")]
        if meta_ids:
            ph = ",".join("?" * len(meta_ids))
            rows = conn.execute(
                f"SELECT metadata_id, {', '.join(COMPARE_FIELDS)} "
                f"FROM books WHERE metadata_id IN ({ph})",
                meta_ids,
            ).fetchall()
            existing = {r["metadata_id"]: r for r in rows}
        else:
            existing = {}

        for book in books:
            mid = book.get("metadata_id")
            if not mid:
                continue

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
                f"{c} = excluded.{c}" for c in cols
                if c not in ("title", "author")
            )
            conn.execute(
                f"INSERT INTO books ({', '.join(cols)}) VALUES ({ph2}) "
                f"ON CONFLICT(title, author) DO UPDATE SET {update}",
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

def _fetch_page(query, page):
    sess = _session()
    for attempt in range(5):
        try:
            data  = _fetch(sess, query, page)
            books = _extract(data)
            return query, page, books, None
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            if status in (429, 503) or (isinstance(status, int) and status >= 500):
                wait = 2 ** attempt          # 1s, 2s, 4s, 8s, 16s
                tqdm.write(f"  [{query} p{page}] HTTP {status} — retrying in {wait}s")
                time.sleep(wait)
            else:
                tqdm.write(f"  [{query} p{page}] HTTP {status} — skipping")
                return query, page, [], str(e)
        except Exception as e:
            tqdm.write(f"  [{query} p{page}] {type(e).__name__}: {e} — skipping")
            return query, page, [], str(e)
    tqdm.write(f"  [{query} p{page}] gave up after 5 attempts")
    return query, page, [], "max retries"


def _probe(query, max_pages):
    """Fetch page 1; return (query, total_pages, page1_books)."""
    sess = _session()
    try:
        data       = _fetch(sess, query, 1)
        pagination = data.get("catalogSearch", {}).get("pagination", {})
        total      = pagination.get("pages", 1)
        if max_pages:
            total = min(total, max_pages)
        return query, total, _extract(data), None
    except Exception as e:
        tqdm.write(f"  [{query} probe] {type(e).__name__}: {e}")
        return query, 0, [], str(e)


# ── Orchestration ─────────────────────────────────────────────────────────────

def scrape_all(max_pages=None):
    db.init_db()

    # ── Phase 1: probe all query letters simultaneously ────────────────
    work = []           # (query, page) pairs for pages 2..N
    page1_results = []  # (query, page, books, err) from page-1 probes

    with tqdm(total=len(QUERIES), desc="Probing ", unit="prefix") as probe_bar:
        with ThreadPoolExecutor(max_workers=len(QUERIES)) as ex:
            futs = {ex.submit(_probe, q, max_pages): q for q in QUERIES}
            for fut in as_completed(futs):
                q, total, books, err = fut.result()
                page1_results.append((q, 1, books, err))
                for p in range(2, total + 1):
                    work.append((q, p))
                probe_bar.set_postfix(pages=f"{len(QUERIES) + len(work):,}")
                probe_bar.update(1)

    total_pages = len(QUERIES) + len(work)
    tqdm.write(f"  {total_pages:,} total pages — fetching {len(work):,} more\n")

    # ── Phase 2: fetch pool + writer thread ────────────────────────────
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
            futs = {ex.submit(_fetch_page, q, p): (q, p) for q, p in work}
            for fut in as_completed(futs):
                result_q.put(fut.result())

        result_q.put(_SENTINEL)
        writer_thread.join()

    r = writer_result
    failed = r.get('failed', [])
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
            w.writerow(["query", "page", "error"])
            w.writerows(failed)
        print(f"\nFailed pages written to: {log_path}")
        print(f"{'query':>6}  {'page':>6}  error")
        print(f"{'─'*6}  {'─'*6}  {'─'*40}")
        for q, p, e in sorted(failed):
            print(f"{q:>6}  {p:>6}  {e[:60]}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Sno-Isle physical-book catalog into library.db"
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Max pages per query letter — omit for full catalog",
    )
    args = parser.parse_args()
    print(f"Target: {db.DB_PATH}\n")
    scrape_all(max_pages=args.max_pages)


if __name__ == "__main__":
    main()
