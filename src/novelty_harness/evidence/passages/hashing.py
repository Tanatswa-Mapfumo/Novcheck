"""Deterministic content hashing for source text and passages.

Normalization is conservative: it makes equivalent carrier encodings of the
same text hash identically without rewriting the text itself. It never
summarizes, truncates or otherwise changes the information content.
"""

import hashlib
import unicodedata

_BOM = "\ufeff"


def normalize_text(text: str) -> str:
    """Return the canonical form of source-derived text used for hashing.

    Rules (stable, documented, order-sensitive):

    1. a leading byte-order mark is dropped;
    2. ``\\r\\n`` and lone ``\\r`` become ``\\n``;
    3. trailing spaces and tabs are removed from every line;
    4. the text is normalized to Unicode NFC;
    5. surrounding whitespace is stripped without touching the interior.
    """

    if text.startswith(_BOM):
        text = text[len(_BOM) :]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
    text = unicodedata.normalize("NFC", text)
    return text.strip()


def text_hash(text: str) -> str:
    """Hash raw source text after canonical normalization."""

    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
