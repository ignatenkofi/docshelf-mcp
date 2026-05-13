"""Filename slug normalizer.

Maps an arbitrary heading or title like "Chapter 4: I²C Timing & Drift"
into a safe, lowercase, hyphen-joined slug usable as a filename.

Algorithm:

1. Unicode NFKD normalization (decomposes accents, fullwidths, sub/superscripts).
2. Strip trailing dots/whitespace.
3. Drop characters that aren't word chars, whitespace, or hyphens (keeps
   unicode letters thanks to `re.UNICODE` — works for Cyrillic, CJK, etc.).
4. Collapse runs of whitespace to single hyphens.
5. Lowercase, then truncate to ``max_len`` (without leaving a trailing hyphen).
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["slugify"]


def slugify(text: str, max_len: int = 60) -> str:
    """Normalize ``text`` into a filename-safe slug.

    Args:
        text: Arbitrary text — heading, title, anything.
        max_len: Maximum slug length in characters. Default 60.

    Returns:
        A non-empty slug. If the input slugifies to nothing (pure punctuation
        or whitespace), returns the literal ``"section"``.

    Example:
        >>> slugify("Chapter 4: Power Supplies")
        'chapter-4-power-supplies'
        >>> slugify("   ")
        'section'
    """
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"\.+$", "", text.strip())
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text).strip("-")
    text = text.lower()
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "section"
