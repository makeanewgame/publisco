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

# Bir `must_exclude_phrases` ifadesi yalnızca SAYFA DÖŞEMESİ gibi davranıyorsa sızıntı
# sayılır: en az bu kadar kez VE kitabın sayfalarının en az bu oranında geçmeli. Koşu
# başlığı/altbilgi/filigran her sayfada (çift-tek sayfa dönüşümlü başlıkta her iki
# sayfada bir, yani ~0.5) tekrar eder; kısmi bir sızıntı bile bu oranın üstünde kalır.
# Düz alt-dize araması ise ifadenin TEK bir geçişini de ihlal sayıyordu ve tam
# koşudaki ihlallerin neredeyse hepsi böyle yanlış pozitiflerdi (2026-10-11 ölçümü,
# bkz. TAMAMLANANLAR_v2.md): ön-metinde bir kez geçen künye/atıf satırı (oran
# 0.00-0.20, hep 1-2 geçiş), kitabın asıl içeriği olan dağınık tekrarlar (`progit`'te
# "Scott Chacon" `git log` örneklerinde 71 kez = 0.14) ve dizin girdileri. Tek gerçek
# sızıntı (`mathematical_singular-integrals`'te dergi başlığı, 3 geçiş / 5 sayfa = 0.60)
# iki eşiği de rahatça geçiyor. Eşik `duplicates.py`'nin 0.5'inden düşük çünkü exclude
# ifadeleri elle seçilmiş (ön olasılık yüksek) ve dönüşümlü başlıkların tam sızıntısı
# bile ancak 0.5'e ulaşır. En az-tekrar şartı, 1-2 sayfalık belgelerde tek bir künye
# geçişinin oranı şişirmesini engeller (bedeli: 1-2 sayfalık belgede sızıntı görünmez).
EXCLUDE_LEAK_MIN_OCCURRENCES = 3
EXCLUDE_LEAK_PAGE_RATIO = 0.25


@dataclass
class TextCompletenessResult:
    phrase_include_recall: float | None = None
    phrase_include_misses: list[str] = field(default_factory=list)
    phrase_exclude_violations: list[str] = field(default_factory=list)
    # Metinde geçen ama sayfa döşemesi gibi tekrar ETMEYEN exclude ifadeleri (ifade ->
    # geçiş sayısı) -- yalnızca raporlanır, skoru etkilemez (bkz. `duplicates.py`'deki
    # repeated/leaked ayrımının aynısı).
    phrase_exclude_incidental: dict[str, int] = field(default_factory=dict)

    word_recall: float | None = None
    word_precision: float | None = None
    ngram_overlap: float | None = None
    missing_words_sample: list[str] = field(default_factory=list)
    extra_words_sample: list[str] = field(default_factory=list)


def _is_page_leak(occurrences: int, total_pages: int | None) -> bool:
    if not total_pages or total_pages <= 0:
        # Sayfa sayısı bilinmiyorsa (ör. doğrudan çağrılan eski testler) ayrım
        # yapılamaz, her geçiş sızıntı sayılır (eski davranışla geriye dönük uyumlu).
        return True
    return (
        occurrences >= EXCLUDE_LEAK_MIN_OCCURRENCES
        and occurrences / total_pages >= EXCLUDE_LEAK_PAGE_RATIO
    )


def _check_phrases(
    generated_text: str,
    exclude_check_text: str,
    must_include: list[str],
    must_exclude: list[str],
    total_pages: int | None = None,
) -> tuple[float | None, list[str], list[str], dict[str, int]]:
    """`exclude_check_text` ayrı tutulur çünkü `must_exclude_phrases` "sızan koşu
    başlığı" niyetiyle yazılır, ama kitabın kendi başlığı TOC'suz kitaplarda
    bölüm `<h1>`'i olarak tam olarak bir kez meşru şekilde göründüğünden, tüm
    metin (h1 dahil) üzerinde düz substring araması bu meşru başlığı sahte bir
    ihlal sayar. Çağıran (`evaluate.py`) h1'i çıkarılmış bir metin geçebilir;
    geçmezse `generated_text` ile aynı davranır (bkz. `evaluate_text_completeness`
    varsayılanı). Aynı niyet yüzünden bir exclude ifadesi ancak sayfa döşemesi gibi
    tekrar ediyorsa ihlaldir (bkz. `EXCLUDE_LEAK_PAGE_RATIO`)."""
    normalized_generated = normalize_phrase(generated_text)

    include_misses = [p for p in must_include if normalize_phrase(p) not in normalized_generated]
    include_recall = None
    if must_include:
        include_recall = (len(must_include) - len(include_misses)) / len(must_include)

    normalized_exclude_check = normalize_phrase(exclude_check_text)
    exclude_violations: list[str] = []
    exclude_incidental: dict[str, int] = {}
    for phrase in must_exclude:
        occurrences = normalized_exclude_check.count(normalize_phrase(phrase))
        if not occurrences:
            continue
        if _is_page_leak(occurrences, total_pages):
            exclude_violations.append(phrase)
        else:
            exclude_incidental[phrase] = occurrences

    return include_recall, include_misses, exclude_violations, exclude_incidental


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
    include_recall, include_misses, exclude_violations, exclude_incidental = _check_phrases(
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
        phrase_exclude_incidental=exclude_incidental,
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
