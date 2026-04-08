"""
Recommendation engine.

Produces:
  - 5 top matches  : high content similarity to liked books + popularity weighted
  - 2 experimental : similar to liked books but low library checkout count
  - 3 bottom match : lowest library checkout count (pure discovery)

Scoring:
  - Content score: TF-IDF cosine similarity on (title + description + subject + genre)
    against the centroid of books rated >= 4.
  - Popularity score: normalized library_checkout_count (0-1).
  - Final score = 0.6 * content_score + 0.4 * popularity_score
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

    # Split into already-checked-out and candidates
    checked_ids = {b["id"] for b in books if b["times_checked_out"] > 0}
    candidates = [b for b in books if b["id"] not in checked_ids]

    if not candidates:
        return None, "No un-read books to recommend. Import a larger catalog."

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

    # Build preference profile: mean vector of books rated >= 4
    liked = [b for b in books if b.get("avg_rating") and b["avg_rating"] >= 4.0]
    if liked:
        step(f"Building taste profile from {len(liked)} loved book(s)...")
        liked_indices = [id_to_idx[b["id"]] for b in liked]
        weights = np.array([b["avg_rating"] for b in liked])
        profile = np.average(
            tfidf_matrix[liked_indices].toarray(), axis=0, weights=weights
        ).reshape(1, -1)
    else:
        # Fall back to all checked-out books if no ratings yet
        checked_list = [b for b in books if b["id"] in checked_ids]
        if checked_list:
            step(f"No ratings yet — profiling from {len(checked_list)} checked-out book(s)...")
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

    step("Ranking results...")
    final_scores = 0.6 * content_scores + 0.4 * pop_scores

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
