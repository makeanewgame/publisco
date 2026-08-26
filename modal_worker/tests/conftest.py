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
def pdf_with_unplaced_image_resource_bytes() -> bytes:
    """Bir sayfanın Resources/XObject sözlüğünde REFERANS EDİLEN ama o sayfanın
    içerik akışında hiç ÇİZİLMEYEN bir görsel xref'i üretir -- `page.get_images()`
    bunu listeler ama `page.get_image_rects()` boş döner (gerçek PDF'lerde
    kullanılmayan/paylaşılan kaynaklarda görülüyor, bkz. ROADMAP.md madde 2,
    `book-with-images_966108` sayfa 17'deki xref=2 örneği)."""
    image = Image.new("RGB", (300, 200), color="green")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = pymupdf.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Bu sayfada hem metin hem gomulu bir gorsel var. " * 6, fontsize=12)
    page1.insert_image(pymupdf.Rect(72, 300, 372, 500), stream=buffer.getvalue())
    xref = page1.get_images(full=True)[0][0]

    page2 = doc.new_page()
    page2.insert_text((72, 72), "Bu sayfada metin var ama resim cizilmemis. " * 6, fontsize=12)
    doc.xref_set_key(page2.xref, "Resources", f"<< /XObject << /Im0 {xref} 0 R >> >>")

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
def pdf_with_image_between_paragraphs_bytes() -> bytes:
    """İki paragraf arasına (dikey konum olarak) yerleştirilmiş gerçek boyutlu
    (ikon-filtresini rahatça geçen) bir görsel içeren bir PDF üretir --
    görselin artık sayfa SONUNA değil, PDF'teki gerçek konumuna (paragraflar
    arasına) yerleştirildiğini test etmek için (bkz. ROADMAP.md madde 2)."""
    image = Image.new("RGB", (300, 200), color="teal")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Bu ilk paragraf resimden once gelir ve yeterince uzundur.", fontsize=12)
    page.insert_image(pymupdf.Rect(72, 200, 372, 400), stream=buffer.getvalue())
    page.insert_text((72, 450), "Bu ikinci paragraf resimden sonra gelir ve farklidir.", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_small_raw_but_large_display_image_bytes() -> bytes:
    """Ham piksel boyutu küçük (eski `MIN_EMBEDDED_IMAGE_DIMENSION=40px` eşiğinin
    altında) ama sayfada BÜYÜK gösterilen (yukarı ölçeklenen) bir görsel üretir --
    boyut filtresinin artık ham piksel yerine sayfada GÖRÜNEN (rect) boyutuna
    baktığını test eder (bkz. ROADMAP.md madde 2, `MIN_EMBEDDED_IMAGE_DISPLAY_PT`)."""
    image = Image.new("RGB", (20, 20), color="purple")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Bu sayfada kucuk ham ama buyuk gosterilen bir gorsel var. " * 4, fontsize=12)
    page.insert_image(pymupdf.Rect(72, 300, 172, 400), stream=buffer.getvalue())  # 100x100 pt gösterim
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_large_raw_but_tiny_display_image_bytes() -> bytes:
    """Ham piksel boyutu BÜYÜK ama sayfada küçük (ikon boyutunda) gösterilen
    bir görsel üretir -- eski (ham piksel bazlı) filtre bunu yanlışlıkla
    tutuyordu; yeni (görünen/rect boyutu bazlı) filtre atlamalı."""
    image = Image.new("RGB", (500, 500), color="orange")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Bu sayfada buyuk ham ama kucuk gosterilen bir gorsel var. " * 4, fontsize=12)
    page.insert_image(pymupdf.Rect(72, 300, 82, 310), stream=buffer.getvalue())  # 10x10 pt gösterim
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
def pdf_with_four_columns_bytes() -> bytes:
    """DÖRT sütunlu bir sayfa (dergi/rehber tarzı düzen) üretir -- her sütunda
    3 blok, gerçek bir kitapta gözlenen geometriye yakın (bkz. NOTES.md/
    ROADMAP.md'deki `book-with-images_ankaranin-trekking-rotalari` sayfa 5
    bulgusu): sütun 1-2 arası dar (~11pt) bir boşluk, sütun 2-3 arası geniş
    (~100pt) bir boşluk, sütun 3-4 arası yine dar bir boşluk. Eski algoritma
    sayfayı yalnızca ORTA ÇİZGİYE göre iki "yarı"ya ayırdığından (sütun 1+2 =
    sol yarı, sütun 3+4 = sağ yarı), bu düzende her yarının kendi içindeki 2
    alt-sütunu birbirine karıştırırdı. Bloklar kasıtlı olarak sütun 4'ten
    sütun 1'e doğru (tersten) eklenir -- ham PDF obje sırasının etkisiz
    olduğunu doğrulamak için."""
    doc = pymupdf.open()
    page = doc.new_page(width=765, height=553)

    columns = [
        (28, ["Sutun bir ilk paragraf.", "Sutun bir ikinci paragraf.", "Sutun bir ucuncu paragraf."]),
        (187, ["Sutun iki ilk paragraf.", "Sutun iki ikinci paragraf.", "Sutun iki ucuncu paragraf."]),
        (434, ["Sutun uc ilk paragraf.", "Sutun uc ikinci paragraf.", "Sutun uc ucuncu paragraf."]),
        (592, ["Sutun dort ilk paragraf.", "Sutun dort ikinci paragraf.", "Sutun dort ucuncu paragraf."]),
    ]
    for x, lines in reversed(columns):
        y = 100
        for text in lines:
            page.insert_text((x, y), text, fontsize=10)
            y += 150

    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_indented_single_column_bytes() -> bytes:
    """Tek sütunlu, ama her paragrafın İLK SATIRI girintili (hanging/first-
    line indent) bir sayfa üretir -- devam satırları x0=72'de, her paragrafın
    ilk satırı x0=100'de başlar. Bu, blokları x0'a göre kümeleyen sütun
    tespitinin YANLIŞLIKLA iki "sütun" (girintili/girintisiz) bulmaması
    gerektiğini doğrular -- gerçek bir kitapta (NOTES.md'deki bulgu)
    tam olarak bu düzende sahte bir 2-sütun tespiti yaşanmıştı."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    y = 72
    for i in range(4):
        page.insert_text((100, y), f"Paragraf {i+1} ilk satiri buradan baslar.", fontsize=11)
        y += 18
        page.insert_text((72, y), "devam satiri burada surer ve biraz daha uzar.", fontsize=11)
        y += 18
        page.insert_text((72, y), "son satir da burada tamamlanir simdi.", fontsize=11)
        y += 30

    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_with_scattered_map_labels_bytes() -> bytes:
    """Tek gerçek metin sütunu (sol) + bir harita/diyagram üzerine
    serpiştirilmiş DAR, KISA etiketler (sağ, ör. yükseklik/mesafe rakamları)
    içeren bir sayfa üretir. Etiketler benzer x0'da kümelenip sayı bakımından
    (`COLUMN_MIN_BLOCKS_PER_COLUMN`) eşiği geçse bile, DAR oldukları için
    (`COLUMN_MIN_BLOCK_WIDTH_RATIO`) gerçek bir sütun sayılmamalı -- gerçek
    bir kitapta (NOTES.md'deki bulgu) tam olarak bu düzende sahte bir sütun
    tespit edilmişti."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    y = 72
    for text in [
        "Bu gercek bir paragraf metnidir ve yeterince uzundur.",
        "Ikinci satirda da metin devam etmektedir boylece.",
        "Ucuncu satir paragrafi burada tamamlanmaktadir simdi.",
    ]:
        page.insert_text((72, y), text, fontsize=11)
        y += 30

    for text in ["921m", "767m", "8 km"]:
        page.insert_text((450, y), text, fontsize=8)
        y += 40

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
