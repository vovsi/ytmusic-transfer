"""Fuzzy-matches a YouTube Music track against SoundCloud search results."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

_NOISE = re.compile(
    r"[\(\[][^\)\]]*(official|video|audio|lyrics?|remaster\w*|hd|hq|explicit|clean)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    text = _NOISE.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip().lower()


def best_match(yt_title: str, yt_artist: str, candidates, threshold: float):
    """Returns (best SCTrack, score) if it clears `threshold`, else (None, score).

    Scores with both token_sort_ratio (penalizes extra/missing words) and
    token_set_ratio (ignores them) and takes the max - SoundCloud titles
    often carry extra remix/mashup wording that token_sort_ratio alone
    would over-penalize.
    """
    query = normalize(f"{yt_artist} {yt_title}")
    best = None
    best_score = 0.0
    for candidate in candidates:
        target = normalize(f"{candidate.artist} {candidate.title}")
        score = max(
            fuzz.token_sort_ratio(query, target),
            fuzz.token_set_ratio(query, target),
        )
        if score > best_score:
            best_score = score
            best = candidate
    if best and best_score >= threshold:
        return best, best_score
    return None, best_score
