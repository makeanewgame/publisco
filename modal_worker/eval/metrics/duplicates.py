"""Referanssız metrik: koşu başlığı/sayfa no/footer gibi tekrarlayan
blokları ve tekrarlayan kelime dizilerini (n-gram) yakalar.

Ground truth gerektirmez -- `assemble_epub`'ın ürettiği metnin kendi içindeki
tutarsız tekrarları arar (bkz. `converter._repeat_key`'in eval tarafındaki
karşılığı: rakamlar `#`'e genellenir, ör. sayfa no sızıntısı tek bir anahtara
düşer)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from eval.text_utils import tokenize_words, word_ngrams

SHORT_BLOCK_MAX_CHARS = 60
SHORT_BLOCK_MIN_REPEATS = 3
DUPLICATE_NGRAM_SIZE = 8


def _repeat_key(text: str) -> str:
    stripped = text.strip()
    if stripped.isdigit():
        return "#"
    return re.sub(r"\s+", " ", stripped).strip().casefold()


@dataclass
class DuplicatesResult:
    repeated_short_blocks: dict[str, int] = field(default_factory=dict)
    repeated_short_block_total_occurrences: int = 0
    duplicate_ngram_ratio: float = 0.0


def evaluate_duplicates(full_text: str) -> DuplicatesResult:
    blocks = [b.strip() for b in full_text.split("\n\n") if b.strip()]

    short_block_counts: Counter[str] = Counter()
    short_block_samples: dict[str, str] = {}
    for block in blocks:
        if len(block) <= SHORT_BLOCK_MAX_CHARS:
            key = _repeat_key(block)
            short_block_counts[key] += 1
            short_block_samples.setdefault(key, block)

    repeated_short_blocks = {
        short_block_samples[key]: count
        for key, count in short_block_counts.items()
        if count >= SHORT_BLOCK_MIN_REPEATS
    }
    repeated_total = sum(repeated_short_blocks.values())

    tokens = tokenize_words(full_text)
    ngrams = word_ngrams(tokens, DUPLICATE_NGRAM_SIZE)
    ngram_ratio = 0.0
    if ngrams:
        counts = Counter(ngrams)
        duplicate_occurrences = sum(c - 1 for c in counts.values() if c > 1)
        ngram_ratio = duplicate_occurrences / len(ngrams)

    return DuplicatesResult(
        repeated_short_blocks=repeated_short_blocks,
        repeated_short_block_total_occurrences=repeated_total,
        duplicate_ngram_ratio=ngram_ratio,
    )
