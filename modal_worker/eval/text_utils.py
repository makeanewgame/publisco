"""Metriklerin ortak kullandığı metin normalizasyon yardımcıları."""

from __future__ import annotations

import re
import unicodedata


_QUOTE_VARIANTS = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    }
)


def normalize_phrase(text: str) -> str:
    """Karşılaştırma için: unicode NFC + casefold + boşluk sadeleştirme + tipografik
    tırnak/apostrof varyantlarının (' ' " " vb.) düz ' / " karakterlerine indirgenmesi
    (PDF'ler genelde tipografik tırnak kullanırken golden metadata'daki ifadeler düz
    tırnakla yazılıyor -- bu fark olmasa da eşleşmeyi bozuyordu, bkz. NOTES.md).
    `must_include_phrases` / `must_exclude_phrases` kontrolünde kullanılır."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.translate(_QUOTE_VARIANTS)
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
