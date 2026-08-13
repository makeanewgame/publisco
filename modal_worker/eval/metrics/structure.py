"""Paragraf sayısı ve bölüm/başlık (TOC) yapısını referansla karşılaştırır.

Başlangıçta mükemmel semantik eşleşme aranmıyor (bkz. eval planı): başlık
eşleştirmesi `difflib.SequenceMatcher` ile bulanık (fuzzy) yapılır -- OCR'dan
gelen küçük karakter farkları ("Bölüm 1" vs "Bolum 1") eşleşmeyi bozmasın diye.
Heading-level (H1 vs H2) doğruluğu v1'de yalnızca teşhis amaçlı raporlanır,
skora girmez -- mevcut pipeline tüm bölüm başlıklarını H1 üretiyor (bkz.
`assemble_epub`), alt başlık seviyesi ayrımı henüz yok.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from eval.text_utils import normalize_phrase

TITLE_MATCH_THRESHOLD = 0.6


@dataclass
class StructureResult:
    paragraph_count: int = 0
    expected_paragraph_range: tuple[int, int] | None = None

    chapter_recall: float | None = None
    chapter_precision: float | None = None
    unmatched_expected_chapters: list[str] = field(default_factory=list)
    unmatched_generated_chapters: list[str] = field(default_factory=list)

    heading_count: int = 0


def _fuzzy_match_titles(
    expected: list[str], generated: list[str], threshold: float = TITLE_MATCH_THRESHOLD
) -> tuple[set[int], set[int]]:
    matched_expected: set[int] = set()
    matched_generated: set[int] = set()

    for i, exp_title in enumerate(expected):
        best_j, best_score = None, 0.0
        for j, gen_title in enumerate(generated):
            if j in matched_generated:
                continue
            score = SequenceMatcher(None, normalize_phrase(exp_title), normalize_phrase(gen_title)).ratio()
            if score > best_score:
                best_j, best_score = j, score
        if best_j is not None and best_score >= threshold:
            matched_expected.add(i)
            matched_generated.add(best_j)

    return matched_expected, matched_generated


def evaluate_structure(
    paragraphs: list[str],
    headings: list[tuple[int, str]],
    generated_chapter_titles: list[str],
    expected_chapters: list[str] | None,
    expected_paragraph_range: tuple[int, int] | None,
) -> StructureResult:
    result = StructureResult(
        paragraph_count=len(paragraphs),
        expected_paragraph_range=expected_paragraph_range,
        heading_count=len(headings),
    )

    if expected_chapters:
        matched_expected, matched_generated = _fuzzy_match_titles(expected_chapters, generated_chapter_titles)
        result.chapter_recall = len(matched_expected) / len(expected_chapters)
        result.chapter_precision = (
            len(matched_generated) / len(generated_chapter_titles) if generated_chapter_titles else 0.0
        )
        result.unmatched_expected_chapters = [
            t for i, t in enumerate(expected_chapters) if i not in matched_expected
        ]
        result.unmatched_generated_chapters = [
            t for j, t in enumerate(generated_chapter_titles) if j not in matched_generated
        ]

    return result
