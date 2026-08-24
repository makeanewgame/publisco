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
def pdf_with_embedded_image_bytes() -> bytes:
    """Metinle karışık, sayfanın yalnızca bir kısmını kaplayan gerçek gömülü bir
    görsel içeren (ikon-boyutu filtresini geçecek kadar büyük) bir PDF üretir —
    normal metin sayfalarındaki gömülü görsellerin artık çıkarıldığını test eder."""
    image = Image.new("RGB", (300, 200), color="red")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Bu sayfada hem metin hem gomulu bir gorsel var. " * 6, fontsize=12)
    page.insert_image(pymupdf.Rect(72, 300, 372, 500), stream=buffer.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_duplicate_image_across_pages_bytes() -> bytes:
    """Aynı görseli (aynı bayt içeriği) iki AYRI sayfaya gömer -- sayfa-aşırı
    (cross-page) görsel dedup'ı test etmek için (bkz. NOTES.md/ROADMAP.md
    Faz 2'den açık kalan sınırlama: aynı görsel her sayfada tekrarsa ayrı
    dosya olarak ekleniyordu)."""
    image = Image.new("RGB", (300, 200), color="blue")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_bytes = buffer.getvalue()

    doc = pymupdf.open()
    for text in ("Birinci sayfa metni. " * 6, "Ikinci sayfa metni. " * 6):
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
        page.insert_image(pymupdf.Rect(72, 300, 372, 500), stream=image_bytes)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_two_columns_bytes() -> bytes:
    """İki sütunlu bir sayfa (akademik makale düzeni) üretir -- sol sütunda 3,
    sağ sütunda 3 ayrı blok. Bloklar kasıtlı olarak önce SAĞ sonra SOL sütun
    sırasıyla eklenir (PDF içindeki ham obje sırası y-koordinatıyla ilgisiz
    olabilir) -- okuma sırası düzeltmesinin gerçekten y-sonra-x/iç sıraya
    değil, sütuna göre çalıştığını test eder."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4

    right_lines = [
        "Sag sutun ilk paragraf metni burada baslar.",
        "Sag sutun ikinci paragraf metni burada.",
        "Sag sutun ucuncu paragraf metni burada.",
    ]
    left_lines = [
        "Sol sutun ilk paragraf metni burada baslar.",
        "Sol sutun ikinci paragraf metni burada.",
        "Sol sutun ucuncu paragraf metni burada.",
    ]

    y = 100
    for text in right_lines:
        page.insert_text((320, y), text, fontsize=12)
        y += 100
    y = 100
    for text in left_lines:
        page.insert_text((72, y), text, fontsize=12)
        y += 100

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


@pytest.fixture
def pdf_with_recurring_header_footer_bytes() -> bytes:
    """22 sayfalık (kalibrasyon eşiği olan 20 sayfayı aşan), her sayfada aynı
    konumda tekrar eden bir koşu başlığı ve artan bir sayfa no'su olan bir PDF
    üretir. Header/footer, sabit %8 varsayılan kenar payının DIŞINDA (~%11)
    konumlandırılır -- dinamik kalibrasyonun, sabit oranın kaçıracağı bir
    örüntüyü yakalayabildiğini test etmek için."""
    doc = pymupdf.open()
    for i in range(1, 23):
        page = doc.new_page()
        page.insert_text((72, 90), "KOSU BASLIGI", fontsize=10)
        page.insert_text((72, 400), f"Bu sayfa {i} icin gercek bir paragraftir ve icerikte kalmalidir.", fontsize=12)
        page.insert_text((72, 750), str(i), fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def multi_chunk_pdf_bytes() -> bytes:
    """`CHUNK_PAGE_SIZE`'ı (25) aşan, birden fazla chunk'a bölünmesi gereken
    çok sayfalı bir PDF üretir — plan/map/reduce sınır davranışını test eder."""
    return _make_pdf([f"Sayfa {i} icin test metnidir. " * 6 for i in range(1, 31)])
