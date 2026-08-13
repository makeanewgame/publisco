"""Kod içinde üretilen, telifsiz "smoke" kitaplar.

Gerçek golden dataset (bkz. `eval/golden/books/`) henüz PDF içermeyen bir
makinede bile (yeni checkout, CI) eval framework'ünün uçtan uca çalıştığını
doğrulamak için var — `pnpm test:conversion -- --smoke` yalnızca bunları
kullanır. `modal_worker/tests/conftest.py`'deki PDF üretim desenlerinin
aynısını (pymupdf ile) izler.

Bilinçli olarak ASCII-only metin kullanılır: pymupdf'in gömülü fontları
Türkçe'ye özgü karakterleri (ı, ş, ğ, ...) güvenilir render etmeyebilir --
bu smoke kitapların amacı dil tespiti değil, pipeline mekaniğini (chunk'lama,
bölümleme, OCR fallback, header/footer kırpma) doğrulamak.
"""

from __future__ import annotations

import io

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from .types import GoldenBook


def _clean_text_book_pdf() -> bytes:
    doc = pymupdf.open()
    for text in [
        "Bu ilk bolumun ilk sayfasidir ve gercek bir hikaye anlatir. " * 5,
        "Bu ilk bolumun ikinci sayfasidir ve hikaye burada devam eder. " * 5,
        "Ikinci bolum burada baslar ve farkli bir olay orgusu sunar. " * 5,
        "Ikinci bolumun son sayfasidir ve hikaye burada tamamlanir. " * 5,
    ]:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _scanned_book_pdf() -> bytes:
    doc = pymupdf.open()

    for phrase in ["HELLO WORLD", "GOODBYE WORLD"]:
        image = Image.new("RGB", (900, 300), color="white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=80)
        draw.text((40, 100), phrase, fill="black", font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        page = doc.new_page()
        page.insert_image(page.rect, stream=buffer.getvalue())

    unreadable_page = doc.new_page()
    unreadable_page.draw_rect(unreadable_page.rect, color=(0, 0, 0), fill=(0.5, 0.5, 0.5))

    # Sayfa sırası: HELLO (okunabilir) -> unreadable (goruntuye duser) -> GOODBYE (okunabilir).
    doc.move_page(len(doc) - 1, 1)

    data = doc.tobytes()
    doc.close()
    return data


def _header_footer_book_pdf() -> bytes:
    doc = pymupdf.open()
    for i in range(1, 23):
        page = doc.new_page()
        page.insert_text((72, 90), "RUNNING HEADER TEXT", fontsize=10)
        page.insert_text((72, 400), f"Bu sayfa {i} icin gercek bir paragraftir ve icerikte kalmalidir. " * 3, fontsize=12)
        page.insert_text((72, 750), str(i), fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def load_synthetic_books() -> list[GoldenBook]:
    return [
        GoldenBook(
            id="smoke-clean-text",
            category="normal-text-novel",
            language="en",
            is_scanned=False,
            pdf_loader=_clean_text_book_pdf,
            config={
                "title": "Smoke Test Book",
                "author": "Smoke Author",
                "language": "en",
                "chapters": [
                    {"start_page": 1, "title": "First Chapter"},
                    {"start_page": 3, "title": "Second Chapter"},
                ],
            },
            expected_chapters=["First Chapter", "Second Chapter"],
            expected_image_count=0,
            must_include_phrases=[
                "ilk bolumun ilk sayfasidir ve gercek bir hikaye",
                "ikinci bolum burada baslar ve farkli bir olay orgusu",
            ],
            expected_paragraph_range=(3, 6),
            notes="Sentetik, temiz gomulu-metin kitabi -- referanssiz + phrase-check metrikleri icin.",
        ),
        GoldenBook(
            id="smoke-scanned",
            category="scanned-novel",
            language="en",
            is_scanned=True,
            pdf_loader=_scanned_book_pdf,
            config={"title": "Smoke Scanned Book", "author": "Smoke Author", "language": "en"},
            expected_image_count=1,
            must_include_phrases=["hello world", "goodbye world"],
            notes="OCR ile okunabilen 2 sayfa + OCR'in kurtaramadigi 1 sayfa (goruntuye dusmeli).",
        ),
        GoldenBook(
            id="smoke-header-footer",
            category="complex-headings",
            language="en",
            is_scanned=False,
            pdf_loader=_header_footer_book_pdf,
            config={"title": "Smoke Header Footer Book", "author": "Smoke Author", "language": "en"},
            expected_image_count=0,
            must_include_phrases=["gercek bir paragraftir ve icerikte kalmalidir"],
            must_exclude_phrases=["running header text"],
            expected_paragraph_range=(20, 24),
            notes="22 sayfa tekrarlayan header/footer -- kalibrasyon + duplicate-detection smoke testi.",
        ),
    ]
