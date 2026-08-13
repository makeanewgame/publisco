"""Tek bir `GoldenBook`'u uçtan uca değerlendirir: dönüştür -> EPUB'ı oku ->
tüm metrikleri hesapla -> skorla -> `BookResult` döner.
"""

from __future__ import annotations

from eval.epub_reader import read_epub
from eval.golden.types import GoldenBook
from eval.metrics.broken_words import BrokenWordsResult, evaluate_broken_words
from eval.metrics.duplicates import DuplicatesResult, evaluate_duplicates
from eval.metrics.epub_validity import EpubValidityResult, evaluate_epub_validity
from eval.metrics.images import ImagesResult, evaluate_images
from eval.metrics.ocr_quality import OcrQualityResult, evaluate_ocr_quality
from eval.metrics.structure import StructureResult, evaluate_structure
from eval.metrics.text_completeness import TextCompletenessResult, evaluate_text_completeness
from eval.runner import BookResult, run_conversion
from eval.scoring import ScoringInput, score_book


def _asdict(obj) -> dict:
    from dataclasses import asdict, is_dataclass

    return asdict(obj) if is_dataclass(obj) else obj


def evaluate_book(book: GoldenBook, force_ocr: bool = False) -> BookResult:
    pdf_bytes = book.pdf_loader()
    artifact = run_conversion(pdf_bytes, book.config, book.id, force_ocr=force_ocr)

    if artifact.error:
        return BookResult(
            book_id=book.id,
            category=book.category,
            score=0.0,
            category_label="Failed",
            error=artifact.error,
            gates_triggered=["conversion_error"],
            duration_seconds=artifact.duration_seconds,
        )

    content = read_epub(artifact.epub_bytes)

    text_completeness = evaluate_text_completeness(
        generated_text=content.full_text,
        reference_text=book.reference_text,
        must_include_phrases=book.must_include_phrases,
        must_exclude_phrases=book.must_exclude_phrases,
    )

    structure = evaluate_structure(
        paragraphs=content.paragraphs,
        headings=content.headings,
        generated_chapter_titles=content.chapter_titles,
        expected_chapters=book.expected_chapters,
        expected_paragraph_range=book.expected_paragraph_range,
    )

    duplicates = evaluate_duplicates(content.full_text)

    language = artifact.plan.resolved_config.get("language", book.language)
    broken_words = evaluate_broken_words(content.full_text, language)

    start_page = artifact.plan.chunks[0][0] if artifact.plan.chunks else 1
    end_page = artifact.plan.chunks[-1][1] if artifact.plan.chunks else artifact.plan.total_pages

    ocr_quality = evaluate_ocr_quality(pdf_bytes, artifact.plan.resolved_config, start_page, end_page)
    images = evaluate_images(pdf_bytes, start_page, end_page, content.content_image_count, book.expected_image_count)
    epub_validity = evaluate_epub_validity(artifact.epub_bytes)

    scoring_output = score_book(
        ScoringInput(
            text_completeness=text_completeness,
            structure=structure,
            duplicates=duplicates,
            broken_words=broken_words,
            ocr_quality=ocr_quality,
            images=images,
            epub_validity=epub_validity,
            must_exclude_phrase_count=len(book.must_exclude_phrases),
        )
    )

    return BookResult(
        book_id=book.id,
        category=book.category,
        score=scoring_output.overall_score,
        category_label=scoring_output.category,
        metric_scores={k: v for k, v in scoring_output.component_scores.items()},
        metric_details={
            "text_completeness": _asdict(text_completeness),
            "structure": _asdict(structure),
            "duplicates": _asdict(duplicates),
            "broken_words": _asdict(broken_words),
            "ocr_quality": _asdict(ocr_quality),
            "images": _asdict(images),
            "epub_validity": _asdict(epub_validity),
            "chapter_titles": content.chapter_titles,
            "paragraph_count": len(content.paragraphs),
        },
        gates_triggered=scoring_output.gates_triggered,
        duration_seconds=artifact.duration_seconds,
    )
