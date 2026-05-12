"""
Recommendation engine.

Produces:
  - 5 top matches  : high content similarity to liked books + popularity weighted
  - 2 experimental : similar to liked books but low library checkout count
  - 3 bottom match : lowest library checkout count (pure discovery)

Preference profile (per-user, mixed signals):
  - avg_rating     (1–5 stars, adult subjective quality)    weight 0.30
  - reread_demands (child asked "again!" count)             weight 0.40
  - times_read     (completed reading sessions)             weight 0.20
  - false_starts   (started but not finished — negative)   weight -0.10
  Each component is normalized 0–1 across the catalog before weighting.
  Books with a composite preference score > 0 seed the taste profile.

Scoring (candidates):
  - Content score: TF-IDF cosine similarity against the preference-weighted centroid.
  - Popularity score: normalized library_checkout_count (0–1).
  - Familiarity penalty: normalized times_checked_out (our own checkouts), weight -0.25.
  - Final score = 0.6 * content_score + 0.4 * popularity_score - 0.25 * familiarity
  Books we've checked out before are penalized but not excluded — revisits remain possible.
"""

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from db import get_all_books


def _build_text(book: dict) -> str:
    parts = [
        book.get("title") or "",
        book.get("author") or "",
        book.get("description") or "",
        book.get("subject") or "",
        book.get("genre") or "",
        book.get("age_range") or "",
    ]
    return " ".join(p for p in parts if p).lower()


def recommend(user: str = "default", age: str = None, step_fn=None):
    def step(msg):
        if step_fn:
            step_fn(msg)

    step("Loading catalog...")
    books = get_all_books(user)
    if not books:
        return None, "No books in database. Run `import` first."

    # Age filter — case-insensitive substring match against age_range field
    if age:
        age_lower = age.lower()
        books = [b for b in books if age_lower in (b.get("age_range") or "").lower()]
        if not books:
            return None, f"No books found for age filter '{age}'."

    # Hard-exclude books currently on our shelf — no point recommending them
    checked_ids = {b["id"] for b in books if b["times_checked_out"] > 0}
    candidates = [b for b in books if not b.get("currently_checked_out")]

    if not candidates:
        return None, "No books to recommend. Import a catalog first."

    step(f"Building vocabulary across {len(books):,} books...")
    all_texts = [_build_text(b) for b in books]
    id_to_idx = {b["id"]: i for i, b in enumerate(books)}

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=5000,
        min_df=1,
        stop_words="english",
    )
    try:
        tfidf_matrix = vectorizer.fit_transform(all_texts)
    except ValueError:
        return None, "Not enough text data to build recommendations yet."

    # Build preference profile from a composite of all engagement signals.
    # Each signal is normalized 0–1 across the catalog before weighting.
    def _norm(arr):
        hi = arr.max()
        return arr / hi if hi > 0 else arr

    ratings       = np.array([b.get("avg_rating")     or 0.0 for b in books])
    reread        = np.array([b.get("reread_demands")  or 0   for b in books], dtype=float)
    reads         = np.array([b.get("times_read")      or 0   for b in books], dtype=float)
    false_starts  = np.array([b.get("false_starts")    or 0   for b in books], dtype=float)

    # Normalize rating to 0–1 (scale is 1–5, so subtract floor then normalize)
    ratings_norm = _norm(np.where(ratings > 0, (ratings - 1) / 4, 0.0))
    reread_norm  = _norm(reread)
    reads_norm   = _norm(reads)
    fs_norm      = _norm(false_starts)

    pref_scores = (
        0.30 * ratings_norm
        + 0.40 * reread_norm
        + 0.20 * reads_norm
        - 0.10 * fs_norm
    )

    liked_mask = pref_scores > 0
    liked = [b for b, has_pref in zip(books, liked_mask) if has_pref]

    if liked:
        step(f"Building taste profile from {len(liked)} book(s) with engagement history...")
        liked_indices = [id_to_idx[b["id"]] for b in liked]
        weights = np.array([pref_scores[id_to_idx[b["id"]]] for b in liked])
        profile = np.average(
            tfidf_matrix[liked_indices].toarray(), axis=0, weights=weights
        ).reshape(1, -1)
    else:
        # Fall back to all checked-out books if no signals yet
        checked_list = [b for b in books if b["id"] in checked_ids]
        if checked_list:
            step(f"No engagement data yet — profiling from {len(checked_list)} checked-out book(s)...")
            indices = [id_to_idx[b["id"]] for b in checked_list]
            profile = np.asarray(tfidf_matrix[indices].mean(axis=0))
        else:
            step("No history yet — ranking by library popularity...")
            profile = None

    step(f"Scoring {len(candidates):,} candidates...")
    checkout_counts = np.array([b.get("library_checkout_count") or 0 for b in candidates], dtype=float)
    max_count = checkout_counts.max() if checkout_counts.max() > 0 else 1
    pop_scores = checkout_counts / max_count

    cand_indices = [id_to_idx[b["id"]] for b in candidates]
    cand_matrix = tfidf_matrix[cand_indices]

    if profile is not None:
        content_scores = cosine_similarity(cand_matrix, profile).flatten()
    else:
        content_scores = np.zeros(len(candidates))

    # Familiarity penalty: discount books we've already checked out
    own_checkouts = np.array([b.get("times_checked_out") or 0 for b in candidates], dtype=float)
    max_own = own_checkouts.max() if own_checkouts.max() > 0 else 1.0
    familiarity = own_checkouts / max_own

    step("Ranking results...")
    final_scores = 0.6 * content_scores + 0.4 * pop_scores - 0.25 * familiarity

    scored = list(zip(candidates, final_scores, content_scores, pop_scores))
    scored.sort(key=lambda x: x[1], reverse=True)

    # --- 5 Top matches ---
    top = scored[:5]

    # --- 2 Experimental: high content similarity but low popularity ---
    exp_pool = sorted(scored, key=lambda x: x[2] - x[3], reverse=True)
    top_ids = {b["id"] for b, *_ in top}
    experimental = [s for s in exp_pool if s[0]["id"] not in top_ids][:2]

    # --- 3 Bottom matches: lowest library checkout count ---
    bottom_pool = sorted(candidates, key=lambda b: b.get("library_checkout_count") or 0)
    used_ids = top_ids | {b["id"] for b, *_ in experimental}
    bottom = [b for b in bottom_pool if b["id"] not in used_ids][:3]

    return {
        "top": [(b, score) for b, score, _, _ in top],
        "experimental": [(b, score) for b, score, _, _ in experimental],
        "bottom": bottom,
        "has_profile": profile is not None,
        "liked_count": len(liked),
    }, None
