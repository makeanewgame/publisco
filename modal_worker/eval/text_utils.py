"""Metriklerin ortak kullandığı metin normalizasyon yardımcıları."""

from __future__ import annotations

import re
import unicodedata


def normalize_phrase(text: str) -> str:
    """Karşılaştırma için: unicode NFC + casefold + boşluk sadeleştirme.
    `must_include_phrases` / `must_exclude_phrases` kontrolünde kullanılır."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = re.sub(r"\s+", " ", normalized).strip().casefold()
    return normalized


def tokenize_words(text: str) -> list[str]:
    """Noktalamayı atıp kelimelere böler (unicode harf/rakam)."""
    normalized = unicodedata.normalize("NFC", text).casefold()
    return re.findall(r"[^\W\d_]+(?:[''][^\W\d_]+)*|\d+", normalized, re.UNICODE)


def word_ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    if len(tokens) < n:
        return []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]
