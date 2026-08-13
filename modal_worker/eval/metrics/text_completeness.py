"""Metin bütünlüğü: üretilen EPUB metni, referansla (varsa) ne kadar örtüşüyor.

İki bağımsız katman:
  - Phrase check (her kitapta çalışır, Tier-1 referans): `must_include_phrases`
    generated metinde var mı, `must_exclude_phrases` sızmış mı (ör. koşu
    başlığı/footer).
  - Word-level recall/precision + 5-gram overlap (yalnız `reference_text`
    olan Tier-2 kitaplarda): kelime kümesi örtüşmesi + okuma sırası duyarlı
    n-gram örtüşmesi (iki-sütun sıralama bozulmasını, kelime kümesi aynı
    kalsa bile n-gram overlap'i düşürerek yakalar).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from eval.text_utils import normalize_phrase, tokenize_words, word_ngrams

NGRAM_SIZE = 5
SAMPLE_LIMIT = 10


@dataclass
class TextCompletenessResult:
    phrase_include_recall: float | None = None
    phrase_include_misses: list[str] = field(default_factory=list)
    phrase_exclude_violations: list[str] = field(default_factory=list)

    word_recall: float | None = None
    word_precision: float | None = None
    ngram_overlap: float | None = None
    missing_words_sample: list[str] = field(default_factory=list)
    extra_words_sample: list[str] = field(default_factory=list)


def _check_phrases(
    generated_text: str, must_include: list[str], must_exclude: list[str]
) -> tuple[float | None, list[str], list[str]]:
    normalized_generated = normalize_phrase(generated_text)

    include_misses = [p for p in must_include if normalize_phrase(p) not in normalized_generated]
    include_recall = None
    if must_include:
        include_recall = (len(must_include) - len(include_misses)) / len(must_include)

    exclude_violations = [p for p in must_exclude if normalize_phrase(p) in normalized_generated]

    return include_recall, include_misses, exclude_violations


def _word_recall_precision(reference_words: Counter, generated_words: Counter) -> tuple[float, float, list[str], list[str]]:
    ref_total = sum(reference_words.values())
    gen_total = sum(generated_words.values())

    overlap = sum((reference_words & generated_words).values())

    recall = overlap / ref_total if ref_total else 0.0
    precision = overlap / gen_total if gen_total else 0.0

    missing = reference_words - generated_words
    extra = generated_words - reference_words

    missing_sample = [word for word, _ in missing.most_common(SAMPLE_LIMIT)]
    extra_sample = [word for word, _ in extra.most_common(SAMPLE_LIMIT)]

    return recall, precision, missing_sample, extra_sample


def _ngram_overlap(reference_tokens: list[str], generated_tokens: list[str], n: int = NGRAM_SIZE) -> float | None:
    ref_ngrams = word_ngrams(reference_tokens, n)
    if not ref_ngrams:
        return None
    ref_set = set(ref_ngrams)
    gen_set = set(word_ngrams(generated_tokens, n))
    if not ref_set:
        return None
    return len(ref_set & gen_set) / len(ref_set)


def evaluate_text_completeness(
    generated_text: str,
    reference_text: str | None,
    must_include_phrases: list[str],
    must_exclude_phrases: list[str],
) -> TextCompletenessResult:
    include_recall, include_misses, exclude_violations = _check_phrases(
        generated_text, must_include_phrases, must_exclude_phrases
    )

    result = TextCompletenessResult(
        phrase_include_recall=include_recall,
        phrase_include_misses=include_misses,
        phrase_exclude_violations=exclude_violations,
    )

    if reference_text:
        reference_tokens = tokenize_words(reference_text)
        generated_tokens = tokenize_words(generated_text)
        recall, precision, missing_sample, extra_sample = _word_recall_precision(
            Counter(reference_tokens), Counter(generated_tokens)
        )
        result.word_recall = recall
        result.word_precision = precision
        result.missing_words_sample = missing_sample
        result.extra_words_sample = extra_sample
        result.ngram_overlap = _ngram_overlap(reference_tokens, generated_tokens)

    return result
