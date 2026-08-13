"""Eval framework'ünün metrik/scoring mantığı için testler.

Pipeline testlerinden (`test_converter.py`) ayrı tutulur -- burada test edilen,
converter.py'nin davranışı değil, eval'in o davranışı doğru ölçüp ölçmediği.
Bilinen-girdi/bilinen-sonuç sentetik örnekler kullanılır.
"""

from __future__ import annotations

import pytest

from eval.epub_reader import read_epub
from eval.golden.synthetic import load_synthetic_books
from eval.metrics.broken_words import evaluate_broken_words
from eval.metrics.duplicates import evaluate_duplicates
from eval.metrics.images import evaluate_images
from eval.metrics.structure import evaluate_structure
from eval.metrics.text_completeness import evaluate_text_completeness
from eval.runner import run_conversion
from eval.scoring import (
    GATE_COMPLETENESS_CAP,
    GATE_VALIDITY_CAP,
    ScoringInput,
    score_book,
)
from eval.metrics.broken_words import BrokenWordsResult
from eval.metrics.duplicates import DuplicatesResult
from eval.metrics.epub_validity import EpubValidityResult
from eval.metrics.images import ImagesResult
from eval.metrics.ocr_quality import OcrQualityResult
from eval.metrics.structure import StructureResult
from eval.metrics.text_completeness import TextCompletenessResult


# --- text_completeness -------------------------------------------------------

def test_word_recall_precision_perfect_match():
    result = evaluate_text_completeness(
        generated_text="the quick brown fox jumps over the lazy dog",
        reference_text="the quick brown fox jumps over the lazy dog",
        must_include_phrases=[],
        must_exclude_phrases=[],
    )
    assert result.word_recall == 1.0
    assert result.word_precision == 1.0
    assert result.ngram_overlap == 1.0


def test_word_recall_drops_when_text_missing():
    result = evaluate_text_completeness(
        generated_text="the quick brown fox",
        reference_text="the quick brown fox jumps over the lazy dog",
        must_include_phrases=[],
        must_exclude_phrases=[],
    )
    assert 0 < result.word_recall < 1
    assert result.word_precision == 1.0
    assert "jumps" in result.missing_words_sample or "dog" in result.missing_words_sample


def test_word_precision_drops_when_model_hallucinates_extra_text():
    """LLM 'metin uydurmuş' senaryosunun ölçülebilir karşılığı: generated
    metinde referansta olmayan kelimeler varsa precision düşmeli."""
    result = evaluate_text_completeness(
        generated_text="the quick brown fox jumps over the lazy dog and then flew to the moon",
        reference_text="the quick brown fox jumps over the lazy dog",
        must_include_phrases=[],
        must_exclude_phrases=[],
    )
    assert result.word_recall == 1.0
    assert result.word_precision < 1.0


def test_phrase_include_and_exclude():
    result = evaluate_text_completeness(
        generated_text="Bu gercek bir paragraftir ve KOSU BASLIGI icermemelidir.",
        reference_text=None,
        must_include_phrases=["gercek bir paragraftir"],
        must_exclude_phrases=["kosu basligi"],
    )
    assert result.phrase_include_recall == 1.0
    assert result.phrase_exclude_violations == ["kosu basligi"]


def test_ngram_overlap_drops_on_reordered_text():
    """İki-sütun okuma sırası bozulması: kelime kümesi aynı kalsa bile
    n-gram (sıra duyarlı) örtüşmesi düşmeli."""
    reference = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    reordered = "alpha gamma beta epsilon delta theta zeta kappa eta iota"
    result = evaluate_text_completeness(
        generated_text=reordered, reference_text=reference, must_include_phrases=[], must_exclude_phrases=[]
    )
    assert result.word_recall == 1.0  # ayni kelime kumesi
    assert result.ngram_overlap < 0.5  # ama sira bozuk


# --- duplicates ----------------------------------------------------------------

def test_duplicates_flags_repeated_short_blocks():
    text = "\n\n".join(["RUNNING HEADER"] * 5 + ["Bu gercek, tekil bir paragraftir ve tekrar etmemektedir."])
    result = evaluate_duplicates(text)
    assert result.repeated_short_block_total_occurrences >= 5


def test_duplicates_low_on_clean_unique_text():
    paragraphs = [
        "Ayse sabah erken kalkip pencereden disariya baktiginda karin yagdigini gordu.",
        "Mehmet elindeki kitabi masaya birakip kahvesini yudumlamaya devam etti.",
        "Uzaktaki daglarin ardindan yukselen gunes butun sehri aydinlatiyordu.",
        "Kopek bahcede kosarken komsu cocuklar onu izleyip gulusuyordu.",
        "Trenin dudugu caldiginda yolcular platforma dogru kosmaya basladi.",
        "Deniz kenarindaki kucuk kafede taze balik kokusu havada asili kaliyordu.",
        "Kutuphanedeki eski raflarda tozlu ciltler sessizce bekliyordu.",
        "Cocuklar parkta salincaklarda saatlerce oyun oynayip gulustuler.",
        "Yagmur baslar baslamaz herkes sokaklardan hizla evlerine kosustu.",
        "Ressam tuvaline son firca darbesini vurup geriye cekildi.",
    ]
    result = evaluate_duplicates("\n\n".join(paragraphs))
    assert result.repeated_short_blocks == {}
    assert result.duplicate_ngram_ratio < 0.1


def test_duplicates_normalizes_page_numbers_to_shared_key():
    text = "\n\n".join(str(i) for i in range(1, 6))
    result = evaluate_duplicates(text)
    assert result.repeated_short_block_total_occurrences == 5


# --- broken_words --------------------------------------------------------------

def test_broken_words_detects_cross_block_hyphen_break():
    text = "Bu kelime cok uzun oldugu icin boluenmis: extraordi-\n\nnary bir durum."
    result = evaluate_broken_words(text, "en")
    if not result.available:
        pytest.skip("wordfreq kurulu değil")
    assert result.confirmed_count >= 1


def test_broken_words_does_not_flag_legitimate_compound():
    text = "This is a well-known fact about the world."
    result = evaluate_broken_words(text, "en")
    if not result.available:
        pytest.skip("wordfreq kurulu değil")
    assert result.confirmed_count == 0


# --- structure -------------------------------------------------------------

def test_structure_fuzzy_matches_chapter_titles_with_small_differences():
    result = evaluate_structure(
        paragraphs=["p1", "p2"],
        headings=[],
        generated_chapter_titles=["Bolum 1: Baslangic", "Bolum 2: Gelisme"],
        expected_chapters=["Bölüm 1: Başlangıç", "Bölüm 2: Gelişme"],
        expected_paragraph_range=None,
    )
    assert result.chapter_recall == 1.0
    assert result.chapter_precision == 1.0


def test_structure_reports_unmatched_chapters():
    result = evaluate_structure(
        paragraphs=[],
        headings=[],
        generated_chapter_titles=["Completely Different Title"],
        expected_chapters=["Chapter One", "Chapter Two"],
        expected_paragraph_range=None,
    )
    assert result.chapter_recall == 0.0
    assert "Chapter One" in result.unmatched_expected_chapters
    assert "Chapter Two" in result.unmatched_expected_chapters


# --- images ------------------------------------------------------------------

def test_images_reports_missing_against_expected(blank_pdf_bytes):
    result = evaluate_images(
        pdf_bytes=blank_pdf_bytes,
        start_page=1,
        end_page=1,
        epub_content_image_count=2,
        expected_image_count=5,
    )
    assert result.missing_vs_expected == 3
    assert result.unexpected_vs_expected == 0


def test_images_recall_against_raw_pdf_when_no_expected_count(blank_pdf_bytes):
    result = evaluate_images(
        pdf_bytes=blank_pdf_bytes,
        start_page=1,
        end_page=1,
        epub_content_image_count=0,
        expected_image_count=None,
    )
    # blank_pdf_bytes'ta hic gomulu gorsel yok -> beklenen de sifir, eksik yok.
    assert result.pdf_image_count == 0
    assert result.missing_vs_pdf == 0


# --- scoring: hard gates -------------------------------------------------------

def _base_scoring_input(**overrides) -> ScoringInput:
    defaults = dict(
        text_completeness=TextCompletenessResult(word_recall=0.95, word_precision=0.95, ngram_overlap=0.9),
        structure=StructureResult(paragraph_count=10),
        duplicates=DuplicatesResult(),
        broken_words=BrokenWordsResult(available=False),
        ocr_quality=OcrQualityResult(available=False),
        images=ImagesResult(pdf_image_count=0),
        epub_validity=EpubValidityResult(available=True, error_count=0, fatal_count=0),
    )
    defaults.update(overrides)
    return ScoringInput(**defaults)


def test_scoring_gate_caps_score_on_epub_validity_error():
    output = score_book(_base_scoring_input(epub_validity=EpubValidityResult(available=True, error_count=1)))
    assert output.overall_score <= GATE_VALIDITY_CAP
    assert "epub_invalid" in output.gates_triggered


def test_scoring_gate_caps_score_on_low_completeness():
    output = score_book(
        _base_scoring_input(
            text_completeness=TextCompletenessResult(word_recall=0.2, word_precision=0.9, ngram_overlap=0.9)
        )
    )
    assert output.overall_score <= GATE_COMPLETENESS_CAP
    assert "text_completeness_below_threshold" in output.gates_triggered


def test_scoring_high_quality_book_scores_excellent():
    output = score_book(_base_scoring_input())
    assert output.overall_score >= 90
    assert output.category == "Excellent"
    assert output.gates_triggered == []


# --- integration: runner + epub_reader roundtrip -------------------------------

def test_synthetic_smoke_books_convert_and_score_without_error():
    for book in load_synthetic_books():
        artifact = run_conversion(book.pdf_loader(), book.config, book.id)
        assert artifact.error is None, f"{book.id}: {artifact.error}"
        content = read_epub(artifact.epub_bytes)
        for phrase in book.must_include_phrases:
            assert phrase.casefold() in content.full_text.casefold(), f"{book.id}: missing phrase '{phrase}'"
        for phrase in book.must_exclude_phrases:
            assert phrase.casefold() not in content.full_text.casefold(), f"{book.id}: leaked phrase '{phrase}'"
