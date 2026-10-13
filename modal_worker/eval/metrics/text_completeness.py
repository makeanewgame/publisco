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

# Bir `must_exclude_phrases` ifadesi, kitabın sayfa sayısına oranla en az bu
# sıklıkta geçiyorsa gerçek bir koşu başlığı/altbilgi sızıntısı sayılır ve
# skoru düşürür. Altında kalanlar (kitabın kendi içeriğinde meşru şekilde
# geçen yazar adı, ön-metindeki künye, sayfa 1'e özgü tek seferlik masthead)
# `phrase_exclude_sparse`'ta yalnızca RAPORLANIR -- düz "bir kez bile geçiyor
# mu" araması bunları sızıntıdan ayıramıyordu (bkz. NOTES.md, 2026-09-09
# exclude-phrase taraması). Eşik, `duplicates.LEAK_PAGE_RATIO_THRESHOLD`'dan
# (0.5) bilinçli olarak düşük: tek/çift sayfada dönüşümlü basılan bir koşu
# başlığı sayfaların yarısından AZINDA görünür ve 0.5'in hemen altında kalırdı.
# Ölçülen külliyatta en sık geçen MEŞRU ifade 0.14'te (`progit`, "Scott
# Chacon" 71/501), tek gerçek tekrarlı sızıntı 0.6'da (`singular-integrals`).
EXCLUDE_LEAK_PAGE_RATIO_THRESHOLD = 0.3


@dataclass
class TextCompletenessResult:
    phrase_include_recall: float | None = None
    phrase_include_misses: list[str] = field(default_factory=list)
    phrase_exclude_violations: list[str] = field(default_factory=list)
    phrase_exclude_sparse: list[str] = field(default_factory=list)
    phrase_exclude_occurrences: dict[str, int] = field(default_factory=dict)

    word_recall: float | None = None
    word_precision: float | None = None
    ngram_overlap: float | None = None
    missing_words_sample: list[str] = field(default_factory=list)
    extra_words_sample: list[str] = field(default_factory=list)


def _check_phrases(
    generated_text: str,
    exclude_check_text: str,
    must_include: list[str],
    must_exclude: list[str],
    total_pages: int | None = None,
) -> tuple[float | None, list[str], list[str], list[str], dict[str, int]]:
    """`exclude_check_text` ayrı tutulur çünkü `must_exclude_phrases` "sızan koşu
    başlığı" niyetiyle yazılır, ama kitabın kendi başlığı TOC'suz kitaplarda
    bölüm `<h1>`'i olarak tam olarak bir kez meşru şekilde göründüğünden, tüm
    metin (h1 dahil) üzerinde düz substring araması bu meşru başlığı sahte bir
    ihlal sayar. Çağıran (`evaluate.py`) h1'i çıkarılmış bir metin geçebilir;
    geçmezse `generated_text` ile aynı davranır (bkz. `evaluate_text_completeness`
    varsayılanı).

    `total_pages` verilirse geçen ifadeler sıklığa göre ikiye ayrılır: sayfa
    sayısına oranla `EXCLUDE_LEAK_PAGE_RATIO_THRESHOLD`'u aşanlar ihlal, kalanı
    "seyrek" (raporlanır, cezalandırılmaz). Verilmezse ayrım yapılamaz, geçen
    her ifade ihlal sayılır (eski davranışla geriye dönük uyumlu)."""
    normalized_generated = normalize_phrase(generated_text)

    include_misses = [p for p in must_include if normalize_phrase(p) not in normalized_generated]
    include_recall = None
    if must_include:
        include_recall = (len(must_include) - len(include_misses)) / len(must_include)

    normalized_exclude_check = normalize_phrase(exclude_check_text)
    exclude_violations: list[str] = []
    exclude_sparse: list[str] = []
    exclude_occurrences: dict[str, int] = {}
    for phrase in must_exclude:
        normalized_phrase = normalize_phrase(phrase)
        count = normalized_exclude_check.count(normalized_phrase) if normalized_phrase else 0
        if not count:
            continue
        exclude_occurrences[phrase] = count
        if total_pages and total_pages > 0 and count / total_pages < EXCLUDE_LEAK_PAGE_RATIO_THRESHOLD:
            exclude_sparse.append(phrase)
        else:
            exclude_violations.append(phrase)

    return include_recall, include_misses, exclude_violations, exclude_sparse, exclude_occurrences


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
    exclude_check_text: str | None = None,
    total_pages: int | None = None,
) -> TextCompletenessResult:
    include_recall, include_misses, exclude_violations, exclude_sparse, exclude_occurrences = _check_phrases(
        generated_text,
        exclude_check_text if exclude_check_text is not None else generated_text,
        must_include_phrases,
        must_exclude_phrases,
        total_pages,
    )

    result = TextCompletenessResult(
        phrase_include_recall=include_recall,
        phrase_include_misses=include_misses,
        phrase_exclude_violations=exclude_violations,
        phrase_exclude_sparse=exclude_sparse,
        phrase_exclude_occurrences=exclude_occurrences,
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
