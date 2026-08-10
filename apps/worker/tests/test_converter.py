import io
import zipfile

import pymupdf
import pytest

from app.converter import (
    ConversionError,
    analyze_pdf,
    clean_text,
    convert_pdf_to_epub,
    detect_chapters,
    detect_title_author,
    extract_page_text,
    text_to_html_blocks,
)


def test_clean_text_merges_hyphenated_linebreaks():
    assert clean_text("kita-\nplar") == "kitaplar"


def test_clean_text_collapses_single_linebreaks_but_keeps_paragraphs():
    text = "birinci satir\nikinci satir\n\nyeni paragraf"
    assert clean_text(text) == "birinci satir ikinci satir\n\nyeni paragraf"


def test_text_to_html_blocks_wraps_paragraphs():
    html = text_to_html_blocks("Bu bir paragraftir ve yeterince uzundur.")
    assert html.startswith("<p>")
    assert html.endswith("</p>")


def test_convert_pdf_to_epub_produces_valid_epub_zip(sample_pdf_bytes):
    config = {"title": "Test Kitap", "author": "Test Yazar", "language": "tr"}
    result = convert_pdf_to_epub(sample_pdf_bytes, config)

    assert isinstance(result, bytes)
    assert result[:4] == b"PK\x03\x04"  # EPUB bir ZIP arşividir


def test_convert_pdf_to_epub_raises_on_invalid_pdf(corrupt_pdf_bytes):
    with pytest.raises(ConversionError):
        convert_pdf_to_epub(corrupt_pdf_bytes, {"title": "X"})


def test_convert_pdf_to_epub_falls_back_to_page_image_when_no_text_found(scanned_pdf_bytes):
    """Taranmış/görsel sayfalarda metin+OCR başarısız olsa da sayfa sessizce atlanmamalı.

    Regresyon testi: eskiden bu durumda sayfa tamamen düşürülüyor, sonuçta
    içeriksiz (yalnızca başlık) bir EPUB üretiliyordu.
    """
    config = {"title": "Taranmis Kitap"}
    result = convert_pdf_to_epub(scanned_pdf_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        image_entries = [name for name in archive.namelist() if name.endswith(".png") or name.endswith(".jpg")]
        assert image_entries, "Metni çıkarılamayan sayfa görsel olarak eklenmeli, atlanmamalı"


def test_convert_pdf_to_epub_ocr_recovers_text_from_scanned_page(ocr_scanned_page_bytes):
    """Metin katmanı olmayan ama görselde okunabilir metin bulunan bir sayfada,
    OCR kuruluysa gerçek metin çıkarılmalı — sayfa sessizce görsele düşmemeli."""
    config = {"title": "OCR Kitap"}
    result = convert_pdf_to_epub(ocr_scanned_page_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        chapter_html = archive.read("EPUB/chap_01.xhtml").decode("utf-8")
        assert "hello" in chapter_html.lower(), "OCR ile çıkarılan metin bölüm HTML'inde görünmeli"

        image_entries = [name for name in archive.namelist() if name.endswith(".jpg")]
        assert not image_entries, "Gerçek OCR metni bulunduğunda sayfa görsele düşmemeli"


def test_convert_pdf_to_epub_respects_max_size(sample_pdf_bytes):
    config = {
        "title": "Boyut Testi",
        "diagram_pages": [1, 2],
        "max_epub_size_mb": 5,
    }
    result = convert_pdf_to_epub(sample_pdf_bytes, config)
    assert len(result) <= 5 * 1024 * 1024


def test_detect_chapters_reads_embedded_toc(pdf_with_toc_bytes):
    doc = pymupdf.open(stream=pdf_with_toc_bytes, filetype="pdf")
    chapters = detect_chapters(doc)
    doc.close()

    # TOC sayfa 2'den basliyor, sayfa 1 kaybolmasin diye basa bir giris bolumu eklenmeli.
    assert chapters == [
        {"start_page": 1, "title": "Giriş"},
        {"start_page": 2, "title": "Birinci Bolum"},
        {"start_page": 4, "title": "Ikinci Bolum"},
    ]


def test_detect_chapters_returns_empty_without_toc(sample_pdf_bytes):
    doc = pymupdf.open(stream=sample_pdf_bytes, filetype="pdf")
    chapters = detect_chapters(doc)
    doc.close()
    assert chapters == []


def test_detect_title_author_prefers_metadata(pdf_with_metadata_bytes):
    doc = pymupdf.open(stream=pdf_with_metadata_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title == "Metadata Basligi"
    assert author == "Metadata Yazari"


def test_detect_title_author_falls_back_to_cover_text(pdf_with_cover_text_bytes):
    doc = pymupdf.open(stream=pdf_with_cover_text_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title == "Buyuk Baslik"
    assert author == "Yazar Adi"


def test_detect_title_author_returns_none_when_nothing_found(blank_pdf_bytes):
    doc = pymupdf.open(stream=blank_pdf_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title is None
    assert author is None


def test_detect_title_author_merges_multiline_title(pdf_with_multiline_cover_title_bytes):
    """Regresyon: aynı (en büyük) puntoda birden çok satıra yayılmış bir
    başlığın eskiden yalnızca ilk satırı alınıyordu."""
    doc = pymupdf.open(stream=pdf_with_multiline_cover_title_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title == "Buyuk Baslik Ikinci Satiri"
    assert author == "Yazar Adi"


def test_detect_title_author_ocrs_scanned_cover(scanned_cover_pdf_bytes):
    """Kapakta metin katmanı yoksa (taranmış/görsel kapak), artık OCR ile
    aynı büyük-satır/küçük-satır heuristiği satır yüksekliği üzerinden
    denenmeli — eskiden bu durumda doğrudan (None, None) dönüyordu."""
    doc = pymupdf.open(stream=scanned_cover_pdf_bytes, filetype="pdf")
    title, author = detect_title_author(doc)
    doc.close()
    assert title is not None and "COVER" in title.upper()
    assert author is not None and "AUTHOR" in author.upper()


def test_analyze_pdf_reports_warnings_for_missing_fields(blank_pdf_bytes):
    result = analyze_pdf(blank_pdf_bytes)
    assert result["title"] is None
    assert result["author"] is None
    assert result["chapters"] == []
    assert set(result["warnings"]) == {"title", "author", "chapters"}


def test_analyze_pdf_omits_warnings_for_detected_fields(pdf_with_metadata_bytes):
    result = analyze_pdf(pdf_with_metadata_bytes)
    assert result["title"] == "Metadata Basligi"
    assert result["author"] == "Metadata Yazari"
    assert "title" not in result["warnings"]
    assert "author" not in result["warnings"]
    assert "chapters" in result["warnings"]  # bu PDF'te TOC yok


def test_analyze_pdf_raises_on_invalid_pdf(corrupt_pdf_bytes):
    with pytest.raises(ConversionError):
        analyze_pdf(corrupt_pdf_bytes)


def test_extract_page_text_preserves_paragraph_breaks(pdf_with_two_paragraphs_bytes):
    doc = pymupdf.open(stream=pdf_with_two_paragraphs_bytes, filetype="pdf")
    text = extract_page_text(doc[0])
    doc.close()

    assert text is not None
    assert "birinci paragraftir" in text
    assert "ikinci paragraftir" in text
    # iki blok da metinde var, aralarında paragraf ayracı (bos satir) olmali
    assert "\n\n" in text


def test_convert_pdf_to_epub_keeps_paragraphs_as_separate_p_tags(pdf_with_two_paragraphs_bytes):
    config = {"title": "Paragraf Testi"}
    result = convert_pdf_to_epub(pdf_with_two_paragraphs_bytes, config)

    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        chapter_files = [name for name in archive.namelist() if name.endswith(".xhtml") and "chap" in name]
        content = archive.read(chapter_files[0]).decode("utf-8")

    # Regresyon testi: eskiden get_text("text") tum sayfayi tek bir <p>'ye
    # duzlestiriyordu (paragraf araligi/bicimlendirme kayboluyordu).
    assert content.count("<p>") >= 2
    assert "birinci paragraftir" in content
    assert "ikinci paragraftir" in content
