"""Görsel korunumu: PDF'deki gömülü görsel sayısı ile EPUB içeriğindeki
görsel sayısını karşılaştırır.

Bilinen bug'ı (NOTES.md: "metin sayfalarındaki gömülü görseller sessizce
kayboluyor") sayısal olarak görünür kılmak bu metriğin asıl amacı --
`pdf_image_count`, metin çıkarma yolunun atladığı görselleri de sayar."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImagesResult:
    pdf_image_count: int = 0
    epub_content_image_count: int = 0
    expected_image_count: int | None = None
    missing_vs_pdf: int = 0
    missing_vs_expected: int | None = None
    unexpected_vs_expected: int | None = None


def _count_pdf_images(pdf_bytes: bytes, start_page: int, end_page: int) -> int:
    import pymupdf as fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        total_pages = len(doc)
        count = 0
        for page_num in range(start_page, end_page + 1):
            page_index = page_num - 1
            if not (0 <= page_index < total_pages):
                continue
            count += len(doc[page_index].get_images(full=False))
        return count
    finally:
        doc.close()


def evaluate_images(
    pdf_bytes: bytes,
    start_page: int,
    end_page: int,
    epub_content_image_count: int,
    expected_image_count: int | None,
) -> ImagesResult:
    pdf_image_count = _count_pdf_images(pdf_bytes, start_page, end_page)

    result = ImagesResult(
        pdf_image_count=pdf_image_count,
        epub_content_image_count=epub_content_image_count,
        expected_image_count=expected_image_count,
        missing_vs_pdf=max(0, pdf_image_count - epub_content_image_count),
    )

    if expected_image_count is not None:
        result.missing_vs_expected = max(0, expected_image_count - epub_content_image_count)
        result.unexpected_vs_expected = max(0, epub_content_image_count - expected_image_count)

    return result
