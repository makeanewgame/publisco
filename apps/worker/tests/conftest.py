import io

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont


def _make_pdf(paragraphs: list[str]) -> bytes:
    doc = pymupdf.open()
    for paragraph in paragraphs:
        page = doc.new_page()
        page.insert_text((72, 72), paragraph, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """İki sayfalı, gerçek metin içeren küçük bir PDF üretir (fixture dosyasına gerek kalmaz)."""
    return _make_pdf(
        [
            "Bu birinci sayfanin test paragrafidir. " * 6,
            "Bu ikinci sayfanin test paragrafidir. " * 6,
        ]
    )


@pytest.fixture
def corrupt_pdf_bytes() -> bytes:
    return b"bu gecerli bir PDF degil"


@pytest.fixture
def scanned_pdf_bytes() -> bytes:
    """Metin katmanı olmayan (sadece görsel içeren), taranmış sayfayı taklit eden bir PDF üretir."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(page.rect, color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def ocr_scanned_page_bytes() -> bytes:
    """Metin katmanı olmayan ama sayfa görselinde OCR ile okunabilir gerçek metin
    içeren bir PDF üretir (gerçek taranmış bir sayfayı taklit eder)."""
    image = Image.new("RGB", (800, 300), color="white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=90)
    draw.text((40, 90), "HELLO WORLD", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=buffer.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def blank_pdf_bytes() -> bytes:
    """Ne metni ne metadata'sı olan, boş bir sayfalık bir PDF üretir."""
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_metadata_bytes() -> bytes:
    """Başlık/yazarı gömülü PDF metadata'sında olan bir PDF üretir."""
    doc = pymupdf.open()
    doc.new_page()
    doc.set_metadata({"title": "Metadata Basligi", "author": "Metadata Yazari"})
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_cover_text_bytes() -> bytes:
    """Metadata'sı olmayan ama kapak sayfasında farklı punto boyutlarında metin olan bir PDF üretir."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Buyuk Baslik", fontsize=32)
    page.insert_text((72, 160), "Yazar Adi", fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_multiline_cover_title_bytes() -> bytes:
    """Metadata'sı olmayan, kapak sayfasında iki satıra yayılmış (aynı
    puntoda) bir başlık ve ondan küçük puntoda bir yazar satırı olan bir
    PDF üretir."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Buyuk Baslik", fontsize=32)
    page.insert_text((72, 140), "Ikinci Satiri", fontsize=32)
    page.insert_text((72, 200), "Yazar Adi", fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def scanned_cover_pdf_bytes() -> bytes:
    """Metin katmanı olmayan (taranmış/görsel) ama görselde OCR ile
    okunabilir, farklı boyutlarda başlık ve yazar metni içeren bir kapak
    sayfası üretir."""
    image = Image.new("RGB", (900, 500), color="white")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default(size=90)
    author_font = ImageFont.load_default(size=36)
    draw.text((40, 60), "COVER TITLE TEXT", fill="black", font=title_font)
    draw.text((40, 220), "Some Author Name", fill="black", font=author_font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=buffer.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_two_paragraphs_bytes() -> bytes:
    """Aynı sayfada, görsel olarak birbirinden ayrık (dolayısıyla ayrı blok sayılması
    gereken) iki paragraf içeren bir PDF üretir."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Bu birinci paragraftir ve yeterince uzun bir cumledir.", fontsize=12)
    page.insert_text((72, 400), "Bu ikinci paragraftir, birinciden tamamen ayri bir blok olmalidir.", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_toc_bytes() -> bytes:
    """Gömülü outline/bookmark'ı olan, ilk bölümü sayfa 1'den başlamayan bir PDF üretir."""
    doc = pymupdf.open()
    for _ in range(5):
        doc.new_page()
    doc.set_toc([[1, "Birinci Bolum", 2], [1, "Ikinci Bolum", 4]])
    data = doc.tobytes()
    doc.close()
    return data
