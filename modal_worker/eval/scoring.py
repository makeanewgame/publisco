"""Ham metriklerden 0-100 arası tek bir "Conversion Quality Score" üretir.

Ağırlıklar rastgele değil, kullanıcı deneyimi kritikliğine göre seçildi
(bkz. eval planı):

    Text completeness (recall %60 + precision %40)   35
    Structure (paragraf %10 + heading/TOC %10)        20
    Text cleanliness (duplicate %8 + broken words %7) 15
    OCR quality                                       10
    Images                                            10
    Reading order (5-gram overlap)                    10
                                                       ---
                                                       100

Bir bileşen o kitapta ölçülemiyorsa (ör. referanssız bir kitapta reading-order,
taranmamış bir kitapta OCR) o bileşen dışlanır ve kalan ağırlıklar kendi
aralarında yeniden normalize edilir -- eksik veri ceza almaz.

Hard gate'ler (skoru üstten kırpar, ağırlıklı ortalamadan bağımsız):
  - epubcheck error/fatal varsa: skor en fazla 59 (Poor tavanı) -- açılmayan/
    geçersiz bir EPUB "Good" olamaz.
  - Metin tamlığı (word recall veya phrase recall) < 0.5 ise: skor en fazla 39
    (Failed) -- metnin yarısından fazlası kayıpsa diğer metrikler önemsiz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eval.metrics.broken_words import BrokenWordsResult
from eval.metrics.duplicates import DuplicatesResult
from eval.metrics.epub_validity import EpubValidityResult
from eval.metrics.images import ImagesResult
from eval.metrics.ocr_quality import OcrQualityResult
from eval.metrics.structure import StructureResult
from eval.metrics.text_completeness import TextCompletenessResult

COMPONENT_WEIGHTS = {
    "text_completeness": 35,
    "structure": 20,
    "cleanliness": 15,
    "ocr_quality": 10,
    "images": 10,
    "reading_order": 10,
}

GATE_VALIDITY_CAP = 59
GATE_COMPLETENESS_CAP = 39
GATE_COMPLETENESS_THRESHOLD = 0.5

CATEGORY_BANDS = [
    (90, 100, "Excellent"),
    (75, 89.999, "Good"),
    (60, 74.999, "Fair"),
    (40, 59.999, "Poor"),
    (0, 39.999, "Failed"),
]


@dataclass
class ScoringInput:
    text_completeness: TextCompletenessResult
    structure: StructureResult
    duplicates: DuplicatesResult
    broken_words: BrokenWordsResult
    ocr_quality: OcrQualityResult
    images: ImagesResult
    epub_validity: EpubValidityResult
    must_exclude_phrase_count: int = 0


@dataclass
class ScoringOutput:
    overall_score: float
    category: str
    component_scores: dict[str, float | None] = field(default_factory=dict)
    gates_triggered: list[str] = field(default_factory=list)


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _text_completeness_score(result: TextCompletenessResult, must_exclude_count: int) -> float | None:
    if result.word_recall is not None and result.word_precision is not None:
        base = 0.6 * result.word_recall + 0.4 * result.word_precision
    elif result.phrase_include_recall is not None:
        base = result.phrase_include_recall
    else:
        return None

    if must_exclude_count:
        violation_ratio = len(result.phrase_exclude_violations) / must_exclude_count
        base = base * (1 - violation_ratio)

    return _clip(base)


def _paragraph_range_score(paragraph_count: int, expected_range: tuple[int, int] | None) -> float | None:
    if expected_range is None:
        return None
    low, high = expected_range
    if low <= paragraph_count <= high:
        return 1.0
    nearest_bound = low if paragraph_count < low else high
    if nearest_bound == 0:
        return 0.0
    distance_ratio = abs(paragraph_count - nearest_bound) / nearest_bound
    return _clip(1 - distance_ratio)


def _structure_score(result: StructureResult) -> float | None:
    paragraph_score = _paragraph_range_score(result.paragraph_count, result.expected_paragraph_range)

    chapter_score = None
    if result.chapter_recall is not None and result.chapter_precision is not None:
        chapter_score = 0.6 * result.chapter_recall + 0.4 * result.chapter_precision

    sub_scores = [s for s in (paragraph_score, chapter_score) if s is not None]
    if not sub_scores:
        return None
    return sum(sub_scores) / len(sub_scores)


def _cleanliness_score(duplicates: DuplicatesResult, broken_words: BrokenWordsResult) -> float | None:
    ngram_penalty = min(1.0, duplicates.duplicate_ngram_ratio * 5)
    block_penalty = min(1.0, duplicates.repeated_short_block_total_occurrences / 20)
    duplicate_score = 1 - max(ngram_penalty, block_penalty)

    if not broken_words.available:
        return _clip(duplicate_score)

    broken_score = 1 - min(1.0, broken_words.per_1000_words / 5)

    # Bucket icinde: duplicate 8/15, broken 7/15 agirlik.
    weighted = (duplicate_score * 8 + broken_score * 7) / 15
    return _clip(weighted)


def _ocr_score(result: OcrQualityResult) -> float | None:
    if not result.available or result.scanned_page_count == 0 or result.avg_confidence is None:
        return None
    base = result.avg_confidence / 100
    penalty = 1 - 0.3 * (result.low_confidence_page_pct or 0.0)
    return _clip(base * penalty)


def _images_score(result: ImagesResult) -> float | None:
    if result.expected_image_count is not None:
        expected = max(1, result.expected_image_count)
        recall = 1 - (result.missing_vs_expected or 0) / expected
        precision_base = max(1, result.epub_content_image_count or result.expected_image_count)
        precision = 1 - (result.unexpected_vs_expected or 0) / precision_base
        return _clip(0.7 * recall + 0.3 * precision)

    if result.pdf_image_count == 0:
        return 1.0

    recall = 1 - result.missing_vs_pdf / result.pdf_image_count
    return _clip(recall)


def _reading_order_score(result: TextCompletenessResult) -> float | None:
    return result.ngram_overlap


def _category_for_score(score: float) -> str:
    for low, high, label in CATEGORY_BANDS:
        if low <= score <= high:
            return label
    return "Failed"


def score_book(inputs: ScoringInput) -> ScoringOutput:
    component_scores: dict[str, float | None] = {
        "text_completeness": _text_completeness_score(inputs.text_completeness, inputs.must_exclude_phrase_count),
        "structure": _structure_score(inputs.structure),
        "cleanliness": _cleanliness_score(inputs.duplicates, inputs.broken_words),
        "ocr_quality": _ocr_score(inputs.ocr_quality),
        "images": _images_score(inputs.images),
        "reading_order": _reading_order_score(inputs.text_completeness),
    }

    available = {name: score for name, score in component_scores.items() if score is not None}
    if not available:
        return ScoringOutput(overall_score=0.0, category="Failed", component_scores=component_scores, gates_triggered=["no_measurable_components"])

    total_weight = sum(COMPONENT_WEIGHTS[name] for name in available)
    weighted_sum = sum(score * COMPONENT_WEIGHTS[name] for name, score in available.items())
    overall = (weighted_sum / total_weight) * 100

    gates_triggered: list[str] = []

    if inputs.epub_validity.available and (inputs.epub_validity.error_count > 0 or inputs.epub_validity.fatal_count > 0):
        if overall > GATE_VALIDITY_CAP:
            overall = GATE_VALIDITY_CAP
        gates_triggered.append("epub_invalid")

    completeness_signal = inputs.text_completeness.word_recall
    if completeness_signal is None:
        completeness_signal = inputs.text_completeness.phrase_include_recall
    if completeness_signal is not None and completeness_signal < GATE_COMPLETENESS_THRESHOLD:
        if overall > GATE_COMPLETENESS_CAP:
            overall = GATE_COMPLETENESS_CAP
        gates_triggered.append("text_completeness_below_threshold")

    overall = _clip(overall, 0, 100)

    return ScoringOutput(
        overall_score=round(overall, 1),
        category=_category_for_score(overall),
        component_scores=component_scores,
        gates_triggered=gates_triggered,
    )
