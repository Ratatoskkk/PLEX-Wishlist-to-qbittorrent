"""Title normalisation, formatting and fuzzy comparison helpers."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_ARTICLES = {"the", "a", "an"}
_WORD_RE = re.compile(r"[a-z0-9]+")
_ROMAN = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
    "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
}
_AMPERSAND_RE = re.compile(r"\s*&\s*")
_YEAR_RE = re.compile(r"\((19|20)\d{2}\)")

GIB = 1024**3


def strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)
    )


def tokenize(title: str) -> list[str]:
    """Lowercase alphanumeric tokens, accents folded, ``&`` expanded to ``and``."""
    value = _AMPERSAND_RE.sub(" and ", strip_accents(title).lower())
    value = value.replace("'", "").replace("’", "")
    return _WORD_RE.findall(value)


def normalize_title(title: str) -> str:
    """Canonical comparison key: no articles, roman numerals folded to digits.

    ``"The Lord of the Rings: Part II"`` and ``"Lord of the Rings Part 2"``
    both collapse to ``"lord of rings part 2"``.
    """
    tokens = [t for t in tokenize(_YEAR_RE.sub("", title)) if t not in _ARTICLES]
    tokens = [str(_ROMAN[t]) if t in _ROMAN else t for t in tokens]
    return " ".join(tokens)


def title_similarity(left: str, right: str) -> float:
    """0..1 similarity between two titles after normalisation."""
    a, b = normalize_title(left), normalize_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    a_tokens, b_tokens = set(a.split()), set(b.split())
    jaccard = len(a_tokens & b_tokens) / len(a_tokens | b_tokens)
    ratio = SequenceMatcher(None, a, b).ratio()
    return max(jaccard, ratio)


# ---------------------------------------------------------------------------
# Presentation helpers (shared by API responses and log messages)
# ---------------------------------------------------------------------------
def human_size(num_bytes: float) -> str:
    if num_bytes <= 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    index = 0
    size = float(num_bytes)
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    precision = 0 if index < 2 else (1 if size >= 10 else 2)
    return f"{size:.{precision}f} {units[index]}"


def human_duration(seconds: float | int | None) -> str:
    if seconds is None or seconds < 0:
        return "∞"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours:02d}h"


def episode_code(season: int | None, episode: int | None) -> str:
    if season is None:
        return ""
    if episode is None:
        return f"S{season:02d}"
    return f"S{season:02d}E{episode:02d}"
