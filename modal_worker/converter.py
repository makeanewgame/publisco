"""PDF -> EPUB dönüştürme motoru (Modal map-reduce sürümü).

`apps/worker/app/converter.py`'den (Hostinger'daki eski tek-process FastAPI
worker) taşındı. Sayfa-bazlı yardımcı fonksiyonlar (metin çıkarma, OCR,
temizleme, HTML üretimi, dil/bölüm/başlık-yazar tespiti) DEĞİŞMEDEN taşındı —
bunlar olgun ve test kapsamlı. Yeni olan kısım, eskiden tek bir
`convert_pdf_to_epub` içinde sırayla yürüyen mantığın üç faza bölünmesi:

- `plan_conversion`: PDF'i bir kere açar, bölüm sınırlarını ve
  `(start_page, end_page)` chunk listesini hesaplar (paralelleşmez).
- `process_page_range` / `process_page`: bir sayfa aralığını (bir Modal
  container'ının kendi indirdiği PDF baytlarından) işler, sonucu mutlak sayfa
  numarasıyla etiketlenmiş `PageResult` olarak döner (`.map()` ile paralel
  çağrılır).
- `assemble_epub`: plan fazındaki bölüm haritasına göre sayfa sonuçlarını
  birleştirip EPUB'ı üretir (paralelleşmez).

`convert_pdf_to_epub`, bu üç fazı tek bir process içinde sırayla çalıştıran
bir kolaylık sarmalayıcısıdır — testlerin ve küçük PDF'lerin eski tek-çağrılık
arayüzü kullanmaya devam edebilmesi için var; asıl dağıtık orkestrasyon
`main.py`'deki Modal fonksiyonlarında (plan/map/reduce ayrı ayrı) yaşar.

`max_epub_size_mb` (hedef boyuta sıkıştırma) bilinçli olarak taşınmadı — v1
kapsamı dışında bırakıldı (bkz. NOTES.md).
"""

from __future__ import annotations

import html
import io
import logging
import re
import statistics
import uuid
from dataclasses import dataclass, field
from typing import Any

import pymupdf as fitz  # `fitz` ismi pymupdf'te deprecated; gerçek modülü bu adla kullanıyoruz.
from ebooklib import epub
from PIL import Image

logger = logging.getLogger("modal_worker.converter")


class ConversionError(Exception):
    """PDF açılamadığında veya dönüştürme tamamen başarısız olduğunda fırlatılır."""


# ---------------------------------------------------------------------------
# Metin temizleme / HTML üretimi
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """PDF'e özgü satır sonu / tireleme sorunlarını temizler."""
    text = re.sub(r"[-\xad]\s*\n\s*", "", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def text_to_html_blocks(text: str) -> str:
    """Metni başlık ve paragraf bloklarına dönüştürür."""
    cleaned = clean_text(text)
    if not cleaned:
        return ""

    paragraphs = re.split(r"\n\s*\n", cleaned)
    html_blocks = []

    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue

        if len(lines) == 1 and len(lines[0].split()) <= 6 and not re.search(r"[.!?]$", lines[0]):
            html_blocks.append(f"<h2>{html.escape(lines[0])}</h2>")
            continue

        block_text = " ".join(lines)
        html_blocks.append(f"<p>{html.escape(block_text)}</p>")

    return "\n".join(html_blocks)


def build_visual_page_html(page_num: int, image_path: str, caption: str | None = None) -> str:
    """Görsel odaklı bir sayfa için HTML oluşturur."""
    parts = ['<div class="visual-page">', f"<h2>Sayfa {page_num}</h2>"]
    parts.append(f'<img src="{image_path}" alt="Sayfa {page_num}" />')
    if caption:
        parts.append(f'<p class="caption">{html.escape(caption)}</p>')
    parts.append("</div>")
    return "\n".join(parts)


HEADER_FOOTER_DEFAULT_MARGIN_RATIO = 0.08  # kalibrasyon atlanır/başarısız olursa düşülen sabit varsayılan (üst/alt %8)
HEADER_FOOTER_MAX_CHARS = 60  # bu bölgede yalnızca kısa bloklar (koşu başlığı/sayfa no) filtrelenir
NOISE_MAX_CHARS = 20  # bu uzunluğa kadar, hiç harf içermeyen bloklar gürültü sayılır

_HAS_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def _is_in_margin(block: tuple, page_height: float, top_ratio: float, bottom_ratio: float) -> bool:
    """Blok, sayfanın üst veya alt kenar payı şeridinin tamamen içinde mi?
    (kısmen taşan bloklar -- ör. normal bir paragrafın ilk satırı -- kenar
    payına girmiş sayılmaz, yalnızca tamamen şeridin içinde kalanlar sayılır.)
    `top_ratio`/`bottom_ratio`, plan fazında `detect_header_footer_margins`
    ile kitaba özel kalibre edilir (bkz. o fonksiyon); kalibrasyon
    atlanmışsa/başarısızsa `HEADER_FOOTER_DEFAULT_MARGIN_RATIO` kullanılır."""
    if page_height <= 0:
        return False
    y0, y1 = block[1], block[3]
    top_margin = page_height * top_ratio
    bottom_margin = page_height * (1 - bottom_ratio)
    return y1 <= top_margin or y0 >= bottom_margin


def _is_noise_block(text: str) -> bool:
    """Tek karakterlik parçaları (dikey çizgi/süslemenin OCR/metin çıkarıcı
    tarafından "i", "#" gibi yanlış yorumlanması) ve kısa, hiç harf
    içermeyen blokları (yalnız rakam/sembol -- ör. başıboş sayfa no,
    "* * *" bölüm ayracı) gürültü sayar."""
    if len(text) <= 1:
        return True
    if len(text) <= NOISE_MAX_CHARS and not _HAS_LETTER_RE.search(text):
        return True
    return False


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def build_header_blacklist(config: dict[str, Any]) -> set[str]:
    """Plan fazında zaten bilinen kitap başlığı/yazarından, sayfa
    üstü/altı koşu başlıklarını eleyecek bir kara liste kurar."""
    blacklist: set[str] = set()
    for key in ("title", "author"):
        value = config.get(key)
        if value and str(value).strip():
            blacklist.add(_normalize_for_match(str(value)))
    return blacklist


def _is_blacklisted(text: str, blacklist: set[str]) -> bool:
    if not blacklist:
        return False
    normalized = _normalize_for_match(text)
    if normalized in blacklist:
        return True
    # Kısa bloklarda (ör. "HIRS KRALI | 14"), başlık/yazar bir alt dizi olarak da gecebilir.
    if len(text) <= HEADER_FOOTER_MAX_CHARS:
        return any(entry in normalized for entry in blacklist if len(entry) >= 3)
    return False


PARAGRAPH_INDENT_MIN_PT = 4.0  # indent-sinyali icin taban esik (cok kucuk fontlarda bile anlamli)
PARAGRAPH_INDENT_LINE_HEIGHT_RATIO = 0.4  # esik, satir yuksekliginin bu oranindan da az olamaz
PARAGRAPH_GAP_MULTIPLIER = 1.8  # tipik satir-ici bosluktan bu kat fazla dikey bosluk = yeni paragraf


def _merge_blocks_into_paragraphs(blocks: list[tuple[float, float, float, float, str]]) -> list[str]:
    """Bir sayfadaki (x0, y0, x1, y1, metin) bloklarini gercek paragraflara birlestirir.

    PyMuPDF'in blok tespiti, gomulu/OCR metin katmani satir-satir yerlestirilmis
    (ozellikle taranmis kitaplarda yaygin) PDF'lerde her fiziksel SATIRI ayri bir
    "blok" olarak dondurebiliyor -- bu bloklari dogrudan ayri paragraf sayarsak
    (`extract_page_text`'in eski davranisi), sarmali (wrap) tek bir paragraf
    onlarca sahte paragrafa bolunur.

    Iki bagimsiz sinyalle gercek paragraf sinirlarini yeniden kurar:
    (1) girinti -- bir satirin sol baslangici, sayfadaki en soldaki (bosluksuz)
    hizaya gore belirgin sekilde icerideyse, bu yeni bir paragrafin ilk satiridir
    (klasik roman dizgisinde standart paragraf-basi girintisi);
    (2) anormal dikey bosluk -- girinti kullanmayan (bos-satir ile ayrilan) dizgi
    stillerini de yakalamak icin ikincil bir agdir.

    Bu iki sinyal yalnizca TEK SATIRLIK bloklara uygulanir. Temiz/LaTeX
    kaynakli akademik PDF'lerde PyMuPDF bir blogu zaten COK SATIRLI (kendi
    icinde "\n" ile birlesmis, tum bir paragraf) donduruyor -- boyle bir blok
    zaten tamamlanmis bir paragraf, komsularina girinti/bosluk sezgisiyle
    EKLENMEMELI (gercek paragraflar-arasi bosluk, PyMuPDF'in kendi
    paragraf-ici satir araligindan bile kucuk olabiliyor -- eklenirse iki
    ayri paragraf tek bir dev paragrafa yanlislikla kaynasir, ayrica
    cok-satirli bloklarin yuksekligi tek-satir istatistiklerini de bozar)."""
    if not blocks:
        return []

    single_line_blocks = [b for b in blocks if "\n" not in b[4]]
    if single_line_blocks:
        heights = [y1 - y0 for _, y0, _, y1, _ in single_line_blocks]
        line_height = statistics.median(heights)

        gaps = [single_line_blocks[i][1] - single_line_blocks[i - 1][3] for i in range(1, len(single_line_blocks))]
        normal_gaps = [g for g in gaps if g <= line_height * 1.5]
        typical_gap = statistics.median(normal_gaps) if normal_gaps else line_height * 0.6

        flush_x0 = min(x0 for x0, _, _, _, _ in single_line_blocks)
        indent_threshold = flush_x0 + max(PARAGRAPH_INDENT_MIN_PT, line_height * PARAGRAPH_INDENT_LINE_HEIGHT_RATIO)
    else:
        typical_gap = indent_threshold = None

    paragraphs: list[str] = []
    current_lines: list[str] = []
    current_is_multiline = False
    prev_y1: float | None = None

    for x0, y0, _x1, y1, text in blocks:
        is_multiline = "\n" in text
        if is_multiline or current_is_multiline:
            is_new_paragraph = bool(current_lines)
        else:
            is_new_paragraph = not current_lines
            if not is_new_paragraph:
                indented = x0 > indent_threshold
                big_gap = (y0 - prev_y1) > typical_gap * PARAGRAPH_GAP_MULTIPLIER
                is_new_paragraph = indented or big_gap

        if is_new_paragraph and current_lines:
            paragraphs.append("\n".join(current_lines))
            current_lines = []

        current_lines.append(text)
        current_is_multiline = is_multiline
        prev_y1 = y1

    if current_lines:
        paragraphs.append("\n".join(current_lines))

    return paragraphs


COLUMN_SPAN_MARGIN_RATIO = 0.05  # sütun sınırına yakın bloklar için tolerans payı (sayfa genişliğinin oranı)
COLUMN_MIN_BLOCKS_PER_SIDE = 3  # bu sayının altında sol/sağ blok varsa iki sütunlu sayılmaz (yanlış-pozitif riski)
COLUMN_MIN_SIDE_BLOCK_RATIO = 0.6  # sol+sağ bloklar, sayfadaki tüm blokların en az bu oranını oluşturmalı


def _split_into_reading_order_segments(
    blocks: list[tuple[float, float, float, float, str]], page_width: float
) -> list[list[tuple[float, float, float, float, str]]]:
    """`page.get_text('blocks', sort=True)`'in kendi sıralaması yalnızca
    y-sonra-x'e göre çalışır -- tek sütunlu sayfalarda doğru, ama İKİ
    SÜTUNLU sayfalarda (akademik makaleler) sol/sağ sütun bloklarını aynı
    yükseklikte satır satır iç içe geçirir; oysa gerçek okuma sırası önce
    tüm sol sütun, sonra tüm sağ sütun olmalı.

    Sayfa gerçekten iki sütunluysa (bloklar sayfa orta çizgisinin belirgin
    biçimde solunda/sağında iki gruba ayrılıyorsa, her iki grupta da
    yeterli blok varsa) bloku bu kurala göre "bölüm"lere ayırır -- tam
    genişlik kaplayan bloklar (başlık, tam-genişlik şekil/tablo) bir
    bölümü kapatıp kendi bölümü olarak araya girer. Sonucu tek bir düz
    blok listesi DEĞİL, bölümlerin listesi olarak döner -- her bölüm
    çağıran tarafından ayrı ayrı `_merge_blocks_into_paragraphs`'a
    verilmeli, çünkü o fonksiyonun girinti tespiti tüm bloklarda TEK bir
    global sol-hiza (`flush_x0`) varsayıyor; sütunlar aynı pas'ta
    birleştirilirse sağ sütunun her satırı sol sütuna göre "girintili"
    görünüp yanlışlıkla ayrı birer paragrafa bölünür.

    İki sütunlu olduğu net değilse (tek sütun -- golden set'in büyük
    çoğunluğu), TEK bir bölüm olarak, mevcut y-sonra-x sırasıyla döner —
    yani tek sütunlu sayfalarda davranış hiç değişmez."""
    if not blocks:
        return []

    x_mid = page_width / 2
    span_margin = page_width * COLUMN_SPAN_MARGIN_RATIO

    def _side(block: tuple[float, float, float, float, str]) -> str:
        x0, _y0, x1, _y1, _text = block
        if x1 <= x_mid + span_margin:
            return "left"
        if x0 >= x_mid - span_margin:
            return "right"
        return "span"

    sides = [_side(b) for b in blocks]
    left_count = sides.count("left")
    right_count = sides.count("right")
    is_two_column = (
        left_count >= COLUMN_MIN_BLOCKS_PER_SIDE
        and right_count >= COLUMN_MIN_BLOCKS_PER_SIDE
        and (left_count + right_count) / len(blocks) >= COLUMN_MIN_SIDE_BLOCK_RATIO
    )
    if not is_two_column:
        return [sorted(blocks, key=lambda b: (b[1], b[0]))]

    ordered_indices = sorted(range(len(blocks)), key=lambda i: blocks[i][1])
    segments: list[list[tuple[float, float, float, float, str]]] = []
    section_left: list[tuple[float, float, float, float, str]] = []
    section_right: list[tuple[float, float, float, float, str]] = []

    def _flush_section() -> None:
        if section_left:
            segments.append(sorted(section_left, key=lambda b: b[1]))
            section_left.clear()
        if section_right:
            segments.append(sorted(section_right, key=lambda b: b[1]))
            section_right.clear()

    for i in ordered_indices:
        side = sides[i]
        if side == "span":
            _flush_section()
            segments.append([blocks[i]])
        elif side == "left":
            section_left.append(blocks[i])
        else:
            section_right.append(blocks[i])
    _flush_section()

    return segments


# PyMuPDF, fontu 'MacRomanEncoding' sanıp eski Mac OS TÜRKÇE kod sayfasıyla
# (yalnızca İ/ı/Ğ/ğ/Ş/ş'nin bulunduğu birkaç bayt konumunda standart Mac
# Roman'dan farklı) üretilmiş PDF'leri yanlış çözünce ortaya çıkan karakterler
# -- ör. 'B‹L‹MSEL' aslında 'BİLİMSEL'. Python'un mac_roman/mac_turkish
# codec'leri arasında round-trip (encode+decode) DENENDİ ama PyMuPDF'in
# kendi iç MacRomanEncoding tablosu (Euro işareti eklenmeden ÖNCEKİ klasik
# Apple tablosu) Python'un güncel 'mac_roman' codec'inden bazı bayt
# konumlarında farklı çıktı verdiğinden (ör. PyMuPDF '¤' U+00A4 basıyor,
# Python'un tablosunda o bayt '€' U+20AC'a karşılık geliyor ve 'İ'ye
# encode edilemiyor) round-trip bu kitapta sessizce başarısız oluyordu.
# Bunun yerine gerçek kitap üzerinde ampirik olarak doğrulanmış doğrudan
# karakter eşlemesi kullanılıyor (bkz. NOTES.md/TAMAMLANANLAR.md).
_MAC_TURKISH_MOJIBAKE_MAP = {
    "‹": "İ",  # U+2039 SINGLE LEFT-POINTING ANGLE QUOTATION MARK
    "›": "ı",  # U+203A SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
    "ﬁ": "Ş",  # U+FB01 LATIN SMALL LIGATURE FI
    "ﬂ": "ş",  # U+FB02 LATIN SMALL LIGATURE FL
    "¤": "ğ",  # U+00A4 CURRENCY SIGN
    "⁄": "Ğ",  # U+2044 FRACTION SLASH
}
# Bunlardan yalnızca bu üçü, gerçek düzgün metinde neredeyse hiç
# rastlanmayacak kadar spesifik -- gate/tetikleyici olarak yalnızca bunlar
# kullanılıyor. '¤'/'⁄' tek başına (ör. gerçek bir para birimi/kesir
# işareti olarak) yanlış tetiklememesi için MacRomanEncoding + bu üç
# işaretçiden en az biri şart koşuluyor.
_MAC_TURKISH_MOJIBAKE_TELLS = {"‹", "›", "ﬁ", "ﬂ"}


def _page_has_macroman_font(page) -> bool:
    """Sayfada `_fix_mac_turkish_mojibake`'in düzeltme uygulayabileceği
    riskli bir font (PyMuPDF'in 'MacRomanEncoding' dediği) var mı? Bu tek
    başına yeterli değil -- çoğu MacRomanEncoding fontu gerçekten doğru/
    İngilizce metin içindir; asıl karar `_fix_mac_turkish_mojibake`'teki
    işaretçi karakterlerle veriliyor."""
    try:
        return any(f[5] == "MacRomanEncoding" for f in page.get_fonts(full=True))
    except Exception:
        return False


def _fix_mac_turkish_mojibake(text: str, has_macroman_font: bool) -> str:
    if not has_macroman_font or not (set(text) & _MAC_TURKISH_MOJIBAKE_TELLS):
        return text
    for wrong, right in _MAC_TURKISH_MOJIBAKE_MAP.items():
        text = text.replace(wrong, right)
    return text


def _extract_text_blocks(
    page,
    blacklist: set[str] | None = None,
    top_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
    bottom_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
) -> list[str]:
    """Sayfayı PyMuPDF'in blok bazlı çıkarımıyla okur, filtrelenmiş blokları
    gerçek paragraflara birleştirir (bkz. `_merge_blocks_into_paragraphs`).

    Üç sezgisel filtre uygulanır: (1) sayfanın üst/alt kenar payındaki kısa
    bloklar (koşu başlığı/sayfa no) atlanır, (2) kitap başlığı/yazarıyla
    eşleşen bloklar (kara liste) atlanır, (3) hiç harf içermeyen kısa veya
    tek karakterlik bloklar (gürültü) atlanır. Kalan bloklar, iki sütunlu
    sayfalarda okuma sırasını koruyacak şekilde bölümlere ayrılır (bkz.
    `_split_into_reading_order_segments`)."""
    try:
        raw_blocks = page.get_text("blocks", sort=False)
    except Exception:
        return []

    page_height = page.rect.height
    has_macroman_font = _page_has_macroman_font(page)

    kept: list[tuple[float, float, float, float, str]] = []
    for block in raw_blocks:
        if len(block) < 7 or block[6] != 0:  # sadece metin blokları (1 = görsel)
            continue
        text = _fix_mac_turkish_mojibake(block[4].strip(), has_macroman_font)
        if not text:
            continue
        if _is_in_margin(block, page_height, top_margin_ratio, bottom_margin_ratio) and len(text) <= HEADER_FOOTER_MAX_CHARS:
            continue
        if _is_blacklisted(text, blacklist or set()):
            continue
        if _is_noise_block(text):
            continue
        kept.append((block[0], block[1], block[2], block[3], text))

    paragraphs: list[str] = []
    for segment in _split_into_reading_order_segments(kept, page.rect.width):
        paragraphs.extend(_merge_blocks_into_paragraphs(segment))
    return paragraphs


def extract_page_text(
    page,
    min_chars: int = 40,
    blacklist: set[str] | None = None,
    top_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
    bottom_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
) -> str | None:
    """Sayfadan metin çıkarır (blok sınırları paragraf ayracı `\\n\\n` olarak korunur).
    Metin çok azsa (muhtemelen taranmış sayfa) None döner."""
    text = "\n\n".join(
        _extract_text_blocks(
            page, blacklist=blacklist, top_margin_ratio=top_margin_ratio, bottom_margin_ratio=bottom_margin_ratio
        )
    )
    if len(text.strip()) < min_chars:
        return None
    return text


def should_use_visual_page(config: dict, text: str, page_num: int) -> bool:
    """Manga/artbook benzeri sayfalarda görsel akışa geçer, normal metin kitaplarda değil."""
    if config.get("visual_mode", False):
        return True

    if not config.get("auto_visual_mode", False):
        return False

    if not text:
        return True

    cleaned = " ".join(text.split())
    if not cleaned:
        return True

    char_count = len(cleaned)
    if char_count < 120:
        return True

    words = len(re.findall(r"\b\w+\b", cleaned))
    if words <= 25:
        return True

    if page_num in set(config.get("diagram_pages", [])):
        return True

    return False


def _ocr_with_retry(doc, page_index: int, ocr_fn, dpi: int = 300) -> Any | None:
    """`ocr_fn`'i sayfanın (alfa kanalsız, RGB) render'ı üzerinde çalıştırır.

    Tesseract bazı sayfalarda (ör. çok büyük/olağandışı render boyutu) iç
    hata verip sıfır olmayan bir çıkış koduyla çökebiliyor; bu durumda
    pytesseract stderr'i UTF-8 olarak decode etmeye çalışırken de hata
    fırlatabiliyor (`UnicodeDecodeError`), gerçek tesseract hatasını gizleyip
    yanıltıcı bir mesaj bırakıyor. Böyle bir çökmede aynı sayfayı daha düşük
    DPI ile bir kez daha denemek genelde yeterli oluyor; o da başarısız
    olursa sessizce None döner (çağıran taraf sayfayı/alanı görsel/boş
    bırakır)."""
    attempts = [dpi] if dpi <= 200 else [dpi, 200]
    for attempt_dpi in attempts:
        try:
            pix = doc[page_index].get_pixmap(dpi=attempt_dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            return ocr_fn(img)
        except Exception as exc:  # tesseract binary kurulu değilse, çökerse vs.
            logger.warning(
                "OCR hatası (sayfa %d, dpi=%d): %s: %s",
                page_index + 1, attempt_dpi, type(exc).__name__, exc,
            )
    return None


def _extract_ocr_text_blocks(
    image: Any,
    lang: str,
    blacklist: set[str] | None = None,
    top_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
    bottom_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
) -> list[str]:
    """OCR çıktısını (`image_to_data`, satır+koordinat+confidence) okuyup gömülü-metin
    yolundaki (`_extract_text_blocks`) ile aynı kenar payı/kara liste/gürültü
    filtrelerini uygular. `image_to_string` (eski davranış) hiç filtre uygulamadığı
    için koşu başlığı/yazar OCR sayfalarında sızıyordu (bkz. NOTES.md)."""
    import pytesseract
    from pytesseract import Output

    data = pytesseract.image_to_data(image, lang=lang, output_type=Output.DICT)
    image_height = image.height

    lines: dict[tuple[int, int, int], list[tuple[int, int, int, int, str]]] = {}
    for i in range(len(data.get("text", []))):
        text = data["text"][i].strip()
        if not text:
            continue
        try:
            if float(data["conf"][i]) < 0:
                continue
        except (TypeError, ValueError):
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        left, top, width, height = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        lines.setdefault(key, []).append((left, top, left + width, top + height, text))

    kept: list[tuple[float, float, float, float, str]] = []
    for key in sorted(lines.keys()):
        words = lines[key]
        x0 = min(w[0] for w in words)
        y0 = min(w[1] for w in words)
        x1 = max(w[2] for w in words)
        y1 = max(w[3] for w in words)
        text = " ".join(w[4] for w in words)

        block = (x0, y0, x1, y1)
        if _is_in_margin(block, image_height, top_margin_ratio, bottom_margin_ratio) and len(text) <= HEADER_FOOTER_MAX_CHARS:
            continue
        if _is_blacklisted(text, blacklist or set()):
            continue
        if _is_noise_block(text):
            continue
        kept.append((x0, y0, x1, y1, text))

    return _merge_blocks_into_paragraphs(kept)


def try_ocr_page(
    doc,
    page_index: int,
    lang: str = "tur+eng",
    dpi: int = 300,
    blacklist: set[str] | None = None,
    top_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
    bottom_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
) -> str | None:
    """pytesseract kuruluysa OCR dener (gömülü-metin yolundakiyle aynı kenar payı/kara
    liste filtreleriyle); kurulu değilse sessizce None döner."""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return None

    def _ocr_fn(img):
        paragraphs = _extract_ocr_text_blocks(
            img, lang, blacklist=blacklist, top_margin_ratio=top_margin_ratio, bottom_margin_ratio=bottom_margin_ratio
        )
        return "\n\n".join(paragraphs)

    return _ocr_with_retry(doc, page_index, _ocr_fn, dpi=dpi)


# ---------------------------------------------------------------------------
# Otomatik dil tespiti
# ---------------------------------------------------------------------------

DEFAULT_OCR_LANGUAGE = "tur+eng"

# langdetect (ISO 639-1) -> Tesseract dil kodu eşlemesi.
LANGUAGE_MAP: dict[str, str] = {
    "tr": "tur",
    "en": "eng",
    "de": "deu",
    "fr": "fra",
    "es": "spa",
    "it": "ita",
    "pt": "por",
    "nl": "nld",
    "ru": "rus",
    "ar": "ara",
    "pl": "pol",
    "sv": "swe",
    "el": "ell",
    "ja": "jpn",
    "ko": "kor",
    "zh-cn": "chi_sim",
    "zh-tw": "chi_tra",
}


def detect_document_language(doc, max_pages: int = 5) -> tuple[str, str]:
    """Belgenin dilini tahmin eder: önce gömülü metinden, bulunamazsa ilk sayfanın
    geniş dil setiyle OCR'ından. `(iso_kodu, tesseract_dili)` döner; tespit
    edilemezse `("tr", DEFAULT_OCR_LANGUAGE)`'a düşer."""
    try:
        from langdetect import DetectorFactory, LangDetectException, detect
    except ImportError:
        logger.warning("langdetect kurulu değil, otomatik dil tespiti atlanıyor.")
        return "tr", DEFAULT_OCR_LANGUAGE

    DetectorFactory.seed = 0  # deterministik sonuç için

    sample_parts: list[str] = []
    for page_index in range(min(max_pages, len(doc))):
        text = extract_page_text(doc[page_index])
        if text:
            sample_parts.append(text)
        if sum(len(p) for p in sample_parts) >= 500:
            break

    sample = " ".join(sample_parts).strip()
    if not sample:
        # Gömülü metin yok (muhtemelen taranmış belge): ilk sayfayı geniş bir
        # dil setiyle OCR'layıp örnek metin elde etmeyi dene.
        sample = (try_ocr_page(doc, 0, lang=DEFAULT_OCR_LANGUAGE) or "").strip()

    if not sample:
        return "tr", DEFAULT_OCR_LANGUAGE

    try:
        iso_code = detect(sample)
    except LangDetectException:
        return "tr", DEFAULT_OCR_LANGUAGE

    tesseract_lang = LANGUAGE_MAP.get(iso_code, "eng")
    logger.info("Belge dili otomatik tespit edildi: %s (tesseract: %s)", iso_code, tesseract_lang)
    return iso_code, tesseract_lang


def resolve_auto_language(doc, config: dict[str, Any]) -> dict[str, Any]:
    """`language`/`ocr_language` alanlarından `"auto"` olanları gerçek değerlere çözer."""
    requested_language = config.get("language", "tr")
    requested_ocr_lang = config.get("ocr_language", DEFAULT_OCR_LANGUAGE)
    if requested_language != "auto" and requested_ocr_lang != "auto":
        return config

    detected_iso, detected_tesseract = detect_document_language(doc)
    resolved = dict(config)
    if requested_language == "auto":
        resolved["language"] = detected_iso
    if requested_ocr_lang == "auto":
        resolved["ocr_language"] = detected_tesseract
    return resolved


def page_to_image_bytes(doc, page_index: int, dpi: int = 200, quality: int = 90) -> bytes:
    pix = doc[page_index].get_pixmap(dpi=dpi)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


MIN_EMBEDDED_IMAGE_DIMENSION = 40  # bu boyuttan (piksel) küçük gömülü görseller ikon/madde imi/süsleme sayılıp atlanır

_EPUB_CORE_IMAGE_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
}


def extract_embedded_page_images(doc, page_index: int, page_num: int) -> list[tuple[str, bytes, str]]:
    """Sayfadaki, metinle karışık gömülü görselleri (fotoğraf/figür/diyagram)
    çıkarır -- `(dosya adı, bayt, media_type)` üçlüleri döner.

    Önceden `_extract_text_blocks` yalnızca metin bloklarını işliyordu
    (`block[6] != 0` filtresiyle görsel bloklar atlanıyordu) ve normal metin
    sayfalarındaki gömülü görseller hiç çıkarılmıyordu (yalnızca
    `diagram_pages`/tam-sayfa-görsel fallback'inde korunuyorlardı) — bkz.
    NOTES.md. Bu fonksiyon o boşluğu dolduruyor.

    İki savunma: (1) küçük ikon/madde imi/süsleme görselleri
    (`MIN_EMBEDDED_IMAGE_DIMENSION` altı) atlanır -- her sayfada onlarca
    küçük dekoratif görsel olabilir, bunları birer `<img>` yapmak gürültü
    yaratır. (2) EPUB'ın çekirdek medya tiplerinde olmayan formatlar (ör.
    JP2/JPX, CMYK JPEG) Pillow ile JPEG'e yeniden kodlanır; Pillow da
    açamazsa (bozuk/desteklenmeyen kodek) o görsel sessizce atlanır -- tek
    bozuk bir görsel yüzünden tüm sayfanın metni kaybolmamalı."""
    images: list[tuple[str, bytes, str]] = []
    seen_xrefs: set[int] = set()
    page = doc[page_index]

    for img_index, img in enumerate(page.get_images(full=True)):
        xref = img[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        width, height = img[2], img[3]
        if width < MIN_EMBEDDED_IMAGE_DIMENSION or height < MIN_EMBEDDED_IMAGE_DIMENSION:
            continue

        try:
            extracted = doc.extract_image(xref)
        except Exception as exc:
            logger.warning("Sayfa %s: gömülü görsel (xref=%s) çıkarılamadı: %s", page_num, xref, exc)
            continue

        ext = (extracted.get("ext") or "").lower()
        image_bytes = extracted["image"]
        media_type = _EPUB_CORE_IMAGE_MEDIA_TYPES.get(ext)
        if media_type is None:
            try:
                pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                buf = io.BytesIO()
                pil_image.save(buf, format="JPEG", quality=90, optimize=True)
                image_bytes = buf.getvalue()
                ext = "jpg"
                media_type = "image/jpeg"
            except Exception as exc:
                logger.warning(
                    "Sayfa %s: gömülü görsel (xref=%s, format=%s) Pillow ile açılamadı, atlandı: %s",
                    page_num, xref, ext or "bilinmiyor", exc,
                )
                continue

        img_name = f"images/page_{page_num}_img_{img_index}.{ext}"
        images.append((img_name, image_bytes, media_type))

    return images


# ---------------------------------------------------------------------------
# Otomatik tespit (bölümler / başlık / yazar) — `/analyze` ve plan fazı kullanır
# ---------------------------------------------------------------------------

def detect_chapters(doc) -> list[dict[str, Any]]:
    """PDF'in gömülü outline/bookmark'larından üst seviye bölümleri çıkarır."""
    try:
        toc = doc.get_toc(simple=True)
    except Exception:
        return []

    chapters: list[dict[str, Any]] = []
    seen_pages: set[int] = set()
    for level, title, page in toc:
        if level != 1:
            continue
        clean_title = title.strip()
        if not clean_title or page < 1 or page in seen_pages:
            continue
        seen_pages.add(page)
        chapters.append({"start_page": page, "title": clean_title})

    chapters.sort(key=lambda c: c["start_page"])

    if chapters and chapters[0]["start_page"] > 1:
        # TOC ilk bölümden önceki (kapak/önsöz gibi) sayfaları atlıyorsa, onları
        # kaybetmemek için başa bir giriş bölümü ekliyoruz.
        chapters.insert(0, {"start_page": 1, "title": "Giriş"})

    return chapters


def _pick_title_author_from_sized_lines(
    lines: list[tuple[float, str]], tolerance_ratio: float = 0.15
) -> tuple[str | None, str | None]:
    """(punto/karakter yüksekliği, metin) çiftlerinden -- orijinal okuma
    sırasında -- başlık/yazar seçer. En büyük değere yakın (tolerans içinde)
    ardışık/dağınık satırların hepsi başlığa dahil edilir (çok satırlı
    başlıkları desteklemek için), ondan belirgin şekilde küçük ilk satır
    yazar adayı olarak alınır."""
    if not lines:
        return None, None

    max_size = max(size for size, _ in lines)
    threshold = max_size * (1 - tolerance_ratio)

    title_lines = [text for size, text in lines if size >= threshold]
    title = " ".join(title_lines) if title_lines else None

    author = None
    for size, text in lines:
        if size < threshold:
            author = text
            break

    return title, author


def _extract_cover_title_author_via_ocr(
    doc, page_index: int, lang: str = DEFAULT_OCR_LANGUAGE
) -> tuple[str | None, str | None]:
    """Kapakta metin katmanı yoksa (taranmış/görsel kapak), OCR'ın kelime
    kutucuklarından satır yüksekliğini punto büyüklüğünün yerine kullanarak
    aynı büyük-satır/küçük-satır heuristiğini dener. pytesseract kurulu
    değilse veya OCR başarısız olursa sessizce (None, None) döner."""
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError:
        return None, None

    data = _ocr_with_retry(
        doc, page_index, lambda img: pytesseract.image_to_data(img, lang=lang, output_type=Output.DICT)
    )
    if data is None:
        return None, None

    line_groups: dict[tuple[int, int, int], list[int]] = {}
    for i, word in enumerate(data.get("text", [])):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        line_groups.setdefault(key, []).append(i)

    lines: list[tuple[float, str]] = []
    for indices in line_groups.values():
        words = [data["text"][i].strip() for i in indices if data["text"][i].strip()]
        if not words:
            continue
        heights = [data["height"][i] for i in indices]
        lines.append((sum(heights) / len(heights), " ".join(words)))

    return _pick_title_author_from_sized_lines(lines)


def _extract_cover_title_author(doc, page_index: int = 0) -> tuple[str | None, str | None]:
    """Kapak sayfasını dener: önce gömülü metin katmanından (punto
    büyüklüğüne göre), metin katmanı yoksa (taranmış/görsel kapak) OCR ile
    aynı heuristiği satır yüksekliği üzerinden dener."""
    try:
        page = doc[page_index]
        data = page.get_text("dict")
        has_macroman_font = _page_has_macroman_font(page)
    except Exception:
        data = {}
        has_macroman_font = False

    lines: list[tuple[float, str]] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = _fix_mac_turkish_mojibake(
                "".join(span.get("text", "") for span in spans).strip(), has_macroman_font
            )
            if not text:
                continue
            size = max((span.get("size", 0) for span in spans), default=0)
            lines.append((size, text))

    if lines:
        return _pick_title_author_from_sized_lines(lines)

    return _extract_cover_title_author_via_ocr(doc, page_index)


def detect_title_author(doc) -> tuple[str | None, str | None]:
    """Önce PDF metadata'sını, eksik kalan alan(lar) için kapak sayfasını dener."""
    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip() or None
    author = (meta.get("author") or "").strip() or None

    if (not title or not author) and len(doc) > 0:
        cover_title, cover_author = _extract_cover_title_author(doc, 0)
        title = title or cover_title
        author = author or cover_author

    return title, author


def analyze_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    """PDF'ten başlık/yazar/bölümleri otomatik tespit etmeye çalışır (tek container,
    senkron — Modal'daki `analyze` web_endpoint'i tarafından kullanılır).

    Tespit edilemeyen alanlar `warnings` listesinde adlandırılır; çağıran taraf
    (frontend) bunu kullanıcıya uyarı olarak gösterir, dönüşümü engellemez.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ConversionError("PDF açılamadı, dosya bozuk olabilir.") from exc

    try:
        title, author = detect_title_author(doc)
        chapters = detect_chapters(doc)
        page_count = doc.page_count
    finally:
        doc.close()

    warnings: list[str] = []
    if not title:
        warnings.append("title")
    if not author:
        warnings.append("author")
    if not chapters:
        warnings.append("chapters")

    return {
        "title": title,
        "author": author,
        "chapters": chapters,
        "warnings": warnings,
        "page_count": page_count,
    }


# ---------------------------------------------------------------------------
# Ayar yardımcıları
# ---------------------------------------------------------------------------

IMAGE_PROFILES = {
    "high": {"dpi": 240, "quality": 92},
    "balanced": {"dpi": 220, "quality": 85},
    "kindle": {"dpi": 200, "quality": 78},
    "small": {"dpi": 180, "quality": 70},
}


def get_image_settings(config: dict) -> tuple[int, int]:
    profile = config.get("image_profile", "balanced")
    if profile in IMAGE_PROFILES:
        p = IMAGE_PROFILES[profile]
        return p["dpi"], p["quality"]

    dpi = config["image_dpi"] if isinstance(config.get("image_dpi"), int) else 220
    quality = config["image_quality"] if isinstance(config.get("image_quality"), int) else 85
    return dpi, quality


# ---------------------------------------------------------------------------
# Kenar payı kalibrasyonu — yalnızca plan fazında, sabit
# `HEADER_FOOTER_DEFAULT_MARGIN_RATIO` yerine kitaba özel bir tahmin üretir
# ---------------------------------------------------------------------------

HEADER_FOOTER_MAX_MARGIN_RATIO = 0.15  # kalibrasyon ne bulursa bulsun, asla bunu aşan bir kenar payı kırpmaz
HEADER_FOOTER_CANDIDATE_RATIO = 0.20  # kalibrasyon sırasında aday blok aranan bölge (nihai tavandan geniş tutulur)
HEADER_FOOTER_BAND_PADDING_RATIO = 0.01  # tespit edilen banda eklenen küçük pay
HEADER_FOOTER_SAMPLE_MIN_PAGES = 20  # bu sayfa sayısının altındaki kitaplarda kalibrasyon atlanır (örneklem güvenilmez)
HEADER_FOOTER_SAMPLE_COUNT = 10
HEADER_FOOTER_MIN_REPEAT_RATIO = 0.5  # tekrar eden blok, örneklenen sayfaların en az bu oranında görülmeli


def _sample_page_numbers(start_page: int, end_page: int, count: int) -> list[int]:
    """Kitaba yayılmış (art arda değil) `count` kadar sayfa numarası seçer --
    ilk/son sayfayı örneklemeden hariç tutar, çünkü bunlar ön/arka madde
    (kapak, ithaf, boş sayfa) olma ihtimali yüksek, running header/footer
    genelde onlarda olmaz ve örüntüyü yanıltabilirler."""
    total = end_page - start_page + 1
    if total <= 2:
        return list(range(start_page, end_page + 1))

    inner_start, inner_end = start_page + 1, end_page - 1
    inner_total = inner_end - inner_start + 1
    count = min(count, inner_total)
    step = inner_total / count
    return sorted({inner_start + int(i * step) for i in range(count)})


def _repeat_key(text: str) -> str:
    """Sayfa no gibi sayfadan sayfaya değişen ama konumu sabit kalan kısa
    blokları aynı 'şablon' olarak eşlemek için salt rakamlardan oluşan
    metinleri jenerikleştirir (ör. "13" ve "14" aynı anahtara düşer)."""
    stripped = text.strip()
    if stripped.isdigit():
        return "#"
    return _normalize_for_match(stripped)


def _calibrated_margin_ratio(hits: dict[str, list[float]], min_repeats: int, from_top: bool) -> float | None:
    """Örnek sayfalar arasında en az `min_repeats` kez tekrar eden bloklardan
    kenar payı oranını çıkarır; tutarlı bir örüntü yoksa None döner."""
    recurring_ratios = [ratio for ratios in hits.values() if len(ratios) >= min_repeats for ratio in ratios]
    if not recurring_ratios:
        return None

    edge = max(recurring_ratios) if from_top else min(recurring_ratios)
    margin_ratio = edge if from_top else (1 - edge)
    return min(margin_ratio + HEADER_FOOTER_BAND_PADDING_RATIO, HEADER_FOOTER_MAX_MARGIN_RATIO)


def detect_header_footer_margins(
    doc, start_page: int, end_page: int, sample_count: int = HEADER_FOOTER_SAMPLE_COUNT
) -> tuple[float, float]:
    """Kitaba yayılmış birkaç sayfayı örnekleyip üst/alt kenarlarda -- aynı
    metinle (koşu başlığı) ya da aynı konumdaki kısa sayısal blokla (sayfa
    no) -- tutarlı şekilde tekrar eden bir örüntü arar; bulursa gerçek kenar
    payı oranlarını, bulamazsa (yeterli sayfa yoksa, header/footer yoksa,
    örüntü tutarsızsa) sabit varsayılanı (`HEADER_FOOTER_DEFAULT_MARGIN_RATIO`)
    döner. `HEADER_FOOTER_MAX_MARGIN_RATIO` tavanı, kalibrasyon yanlış
    pozitif üretse bile gerçek içeriği yutmasını engeller."""
    total_pages = end_page - start_page + 1
    if total_pages < HEADER_FOOTER_SAMPLE_MIN_PAGES:
        return HEADER_FOOTER_DEFAULT_MARGIN_RATIO, HEADER_FOOTER_DEFAULT_MARGIN_RATIO

    top_hits: dict[str, list[float]] = {}
    bottom_hits: dict[str, list[float]] = {}
    sampled_pages = 0

    for page_num in _sample_page_numbers(start_page, end_page, sample_count):
        page_index = page_num - 1
        if not (0 <= page_index < len(doc)):
            continue
        page = doc[page_index]
        page_height = page.rect.height
        if page_height <= 0:
            continue
        try:
            raw_blocks = page.get_text("blocks", sort=True)
        except Exception:
            continue

        sampled_pages += 1
        candidate_band = page_height * HEADER_FOOTER_CANDIDATE_RATIO
        for block in raw_blocks:
            if len(block) < 7 or block[6] != 0:
                continue
            text = block[4].strip()
            if not text or len(text) > HEADER_FOOTER_MAX_CHARS:
                continue
            y0, y1 = block[1], block[3]
            key = _repeat_key(text)
            if y1 <= candidate_band:
                top_hits.setdefault(key, []).append(y1 / page_height)
            elif y0 >= page_height - candidate_band:
                bottom_hits.setdefault(key, []).append(y0 / page_height)

    if sampled_pages == 0:
        return HEADER_FOOTER_DEFAULT_MARGIN_RATIO, HEADER_FOOTER_DEFAULT_MARGIN_RATIO

    min_repeats = max(2, round(sampled_pages * HEADER_FOOTER_MIN_REPEAT_RATIO))
    top_ratio = _calibrated_margin_ratio(top_hits, min_repeats, from_top=True)
    bottom_ratio = _calibrated_margin_ratio(bottom_hits, min_repeats, from_top=False)

    resolved_top = top_ratio if top_ratio is not None else HEADER_FOOTER_DEFAULT_MARGIN_RATIO
    resolved_bottom = bottom_ratio if bottom_ratio is not None else HEADER_FOOTER_DEFAULT_MARGIN_RATIO
    logger.info(
        "Kenar payı kalibrasyonu: %d sayfa örneklendi, üst=%.3f alt=%.3f (varsayılan=%.3f)",
        sampled_pages, resolved_top, resolved_bottom, HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
    )
    return resolved_top, resolved_bottom


# ---------------------------------------------------------------------------
# Plan fazı — tek container, paralelleşmez
# ---------------------------------------------------------------------------

CHUNK_PAGE_SIZE = 25


@dataclass
class ChapterPlan:
    start_page: int
    end_page: int
    title: str


@dataclass
class PlanResult:
    total_pages: int
    resolved_config: dict[str, Any]
    chapters: list[ChapterPlan]
    chunks: list[tuple[int, int]]
    cover_image: bytes | None = None


def plan_conversion(pdf_bytes: bytes, config: dict[str, Any]) -> PlanResult:
    """PDF'i bir kere açıp bölüm sınırlarını, kapak görselini ve paralel işlenecek
    `(start_page, end_page)` chunk listesini (`CHUNK_PAGE_SIZE` sayfalık) hesaplar.
    `config` alanları `book_config.json` ile aynı şemayı izler."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ConversionError(f"PDF açılamadı: {exc}") from exc

    try:
        resolved_config = resolve_auto_language(doc, config)
        total_pages = len(doc)

        start_page = max(1, resolved_config.get("start_page", 1))
        end_page = min(total_pages, resolved_config.get("end_page", total_pages))

        top_margin_ratio, bottom_margin_ratio = detect_header_footer_margins(doc, start_page, end_page)
        resolved_config = dict(resolved_config)
        resolved_config["header_margin_ratio"] = top_margin_ratio
        resolved_config["footer_margin_ratio"] = bottom_margin_ratio

        chapters_cfg = resolved_config.get("chapters") or [
            {"start_page": start_page, "title": resolved_config.get("title", "Kitap")}
        ]
        chapters_cfg = sorted(chapters_cfg, key=lambda c: c["start_page"])

        chapters: list[ChapterPlan] = []
        for i, chap in enumerate(chapters_cfg):
            chap_start = chap["start_page"]
            chap_end = (
                chapters_cfg[i + 1]["start_page"] - 1 if i + 1 < len(chapters_cfg) else end_page
            )
            chap_end = min(chap_end, end_page)
            chapters.append(ChapterPlan(start_page=chap_start, end_page=chap_end, title=chap["title"]))

        cover_image: bytes | None = None
        cover_page = resolved_config.get("cover_page")
        if cover_page:
            image_dpi, image_quality = get_image_settings(resolved_config)
            cover_image = page_to_image_bytes(doc, cover_page - 1, dpi=image_dpi, quality=image_quality)
            logger.info("Kapak eklendi (sayfa %s)", cover_page)

        chunks: list[tuple[int, int]] = []
        cursor = start_page
        while cursor <= end_page:
            chunk_end = min(cursor + CHUNK_PAGE_SIZE - 1, end_page)
            chunks.append((cursor, chunk_end))
            cursor = chunk_end + 1

        return PlanResult(
            total_pages=total_pages,
            resolved_config=resolved_config,
            chapters=chapters,
            chunks=chunks,
            cover_image=cover_image,
        )
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Map fazı — paralel, `.map()` ile çağrılır
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    page_num: int
    html: str
    images: list[tuple[str, bytes, str]] = field(default_factory=list)  # (dosya adı, bayt, media_type)


def process_page(
    doc,
    page_num: int,
    config: dict[str, Any],
    force_ocr: bool = False,
    header_blacklist: set[str] | None = None,
) -> PageResult:
    """Tek bir sayfayı işler (metin/OCR/görsel), sonucu mutlak sayfa numarasıyla
    etiketlenmiş `PageResult` olarak döner — görsel dosya adları da sayfa
    numarasını içerir ki farklı chunk'larda paralel üretilen görseller
    reduce fazında çakışmasın.

    `header_blacklist`, kitap başlığı/yazarından kurulmuş bir küme --
    `extract_page_text`'e geçirilip koşu başlığı/yazar satırlarının paragraf
    olarak sızmasını engeller (bkz. `build_header_blacklist`)."""
    page_index = page_num - 1
    diagram_pages = set(config.get("diagram_pages", []))
    ocr_lang = config.get("ocr_language", DEFAULT_OCR_LANGUAGE)
    visual_mode = bool(config.get("visual_mode", False))
    auto_visual_mode = bool(config.get("auto_visual_mode", False))
    image_dpi, image_quality = get_image_settings(config)
    page_captions = config.get("page_captions", {})
    top_margin_ratio = config.get("header_margin_ratio", HEADER_FOOTER_DEFAULT_MARGIN_RATIO)
    bottom_margin_ratio = config.get("footer_margin_ratio", HEADER_FOOTER_DEFAULT_MARGIN_RATIO)

    html_parts: list[str] = []
    images: list[tuple[str, bytes, str]] = []

    if page_num in diagram_pages:
        img_name = f"images/page_{page_num}_diagram.jpg"
        images.append((img_name, page_to_image_bytes(doc, page_index, dpi=image_dpi, quality=image_quality), "image/jpeg"))
        html_parts.append(f'<img src="{img_name}" alt="Şema/tablo - sayfa {page_num}" />')

    text = extract_page_text(
        doc[page_index],
        blacklist=header_blacklist,
        top_margin_ratio=top_margin_ratio,
        bottom_margin_ratio=bottom_margin_ratio,
    )
    # Gömülü metin katmanı yoksa (taranmış sayfa) OCR'a düşülüyor -- bu durumda
    # sayfanın PDF içindeki "gömülü görseli" genelde taramanın kendisi (tek,
    # tüm sayfayı kaplayan bir raster XObject) olduğundan, aşağıdaki gömülü
    # görsel çıkarımı bu sayfalarda ATLANMALI -- yoksa OCR'lanan metnin hemen
    # altına aynı sayfanın gereksiz bir kopyası (tam sayfa görsel) eklenir.
    is_scanned_page = text is None
    if text is None:
        text = try_ocr_page(
            doc,
            page_index,
            ocr_lang,
            blacklist=header_blacklist,
            top_margin_ratio=top_margin_ratio,
            bottom_margin_ratio=bottom_margin_ratio,
        )
        if not text or not text.strip():
            # Ne gömülü metin ne de OCR sonucu var (taranmış sayfa, OCR
            # kurulu değil vb.) — sayfayı atlarsak içerik tamamen kaybolur,
            # bu yüzden visual_mode ayarından bağımsız olarak görsel ekliyoruz.
            img_name = f"images/page_{page_num}.jpg"
            images.append(
                (img_name, page_to_image_bytes(doc, page_index, dpi=image_dpi, quality=image_quality), "image/jpeg")
            )
            caption = page_captions.get(str(page_num))
            html_parts.append(build_visual_page_html(page_num, img_name, caption=caption))
            logger.info(
                "Sayfa %s için metin bulunamadı (taranmış olabilir), görsel olarak eklendi.",
                page_num,
            )
            return PageResult(page_num=page_num, html="\n".join(html_parts), images=images)
    elif force_ocr:
        ocr_text = try_ocr_page(
            doc,
            page_index,
            ocr_lang,
            blacklist=header_blacklist,
            top_margin_ratio=top_margin_ratio,
            bottom_margin_ratio=bottom_margin_ratio,
        )
        if ocr_text:
            text = ocr_text

    use_visual = visual_mode or (auto_visual_mode and should_use_visual_page(config, text, page_num))
    if use_visual:
        img_name = f"images/page_{page_num}.jpg"
        images.append(
            (img_name, page_to_image_bytes(doc, page_index, dpi=image_dpi, quality=image_quality), "image/jpeg")
        )
        caption = page_captions.get(str(page_num))
        html_parts.append(build_visual_page_html(page_num, img_name, caption=caption))
        return PageResult(page_num=page_num, html="\n".join(html_parts), images=images)

    cleaned = clean_text(text)
    block_html = text_to_html_blocks(cleaned)
    if block_html:
        html_parts.append(block_html)

    # Sayfa normal metin olarak işlendi (görsele düşmedi) -- ama metinle
    # karışık gömülü görseller (fotoğraf/figür/diyagram) olabilir, bunlar
    # `extract_page_text`'in metin-blok filtresinde hiç görünmüyordu (bkz.
    # NOTES.md). `diagram_pages`'te zaten tüm sayfa görsel olarak eklendiği
    # için, taranmış sayfalarda da (yukarıdaki `is_scanned_page` notuna bkz.)
    # burada tekrar çıkarmıyoruz.
    if not is_scanned_page and page_num not in diagram_pages:
        for img_name, img_bytes, media_type in extract_embedded_page_images(doc, page_index, page_num):
            images.append((img_name, img_bytes, media_type))
            html_parts.append(f'<img src="{img_name}" alt="Sayfa {page_num} görseli" />')

    return PageResult(page_num=page_num, html="\n".join(html_parts), images=images)


def process_page_range(
    pdf_bytes: bytes,
    start_page: int,
    end_page: int,
    config: dict[str, Any],
    force_ocr: bool = False,
) -> list[PageResult]:
    """Bir `(start_page, end_page)` chunk'ını işler — Modal'ın `process_chunk`
    fonksiyonu bu PDF baytlarını blob URL'inden kendisi indirip burayı çağırır."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ConversionError(f"PDF açılamadı: {exc}") from exc

    skip_pages = set(config.get("skip_pages", []))
    total_pages = len(doc)
    header_blacklist = build_header_blacklist(config)
    results: list[PageResult] = []
    try:
        for page_num in range(start_page, end_page + 1):
            if page_num < 1 or page_num > total_pages or page_num in skip_pages:
                continue
            results.append(
                process_page(doc, page_num, config, force_ocr=force_ocr, header_blacklist=header_blacklist)
            )
    finally:
        doc.close()
    return results


# ---------------------------------------------------------------------------
# Reduce fazı — tek container
# ---------------------------------------------------------------------------

def assemble_epub(plan: PlanResult, page_results: list[PageResult]) -> bytes:
    """Sayfa sonuçlarını plan fazındaki bölüm haritasına göre (chunk sınırından
    bağımsız, sayfa numarası sırasına göre) `EpubHtml` item'larına toplayıp
    EPUB üretir."""
    config = plan.resolved_config
    by_page = {pr.page_num: pr for pr in page_results}

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(config.get("title", "Başlıksız Kitap"))
    book.set_language(config.get("language", "tr").split("-")[0])
    book.add_author(config.get("author", "Bilinmiyor"))

    if plan.cover_image is not None:
        book.set_cover("cover.jpg", plan.cover_image)

    css = epub.EpubItem(
        uid="style",
        file_name="style/style.css",
        media_type="text/css",
        content=(
            "body { text-align: justify; font-family: serif; line-height: 1.6; }"
            "h1 { text-align: center; margin: 1.2em 0 1em; }"
            "h2 { margin: 1.2em 0 0.5em; }"
            "p { margin: 0 0 0.8em; text-indent: 0; }"
            "img { max-width: 100%; display: block; margin: 1em auto; }"
            ".visual-page { margin: 1.5em 0; }"
            ".caption { font-size: 0.95em; text-align: center; color: #444; }"
        ),
    )
    book.add_item(css)

    chapter_items = []
    for i, chap in enumerate(plan.chapters):
        html_parts = [f"<h1>{html.escape(chap.title)}</h1>"]

        for page_num in range(chap.start_page, chap.end_page + 1):
            pr = by_page.get(page_num)
            if pr is None:
                continue
            for img_name, img_bytes, media_type in pr.images:
                book.add_item(
                    epub.EpubItem(
                        uid=img_name.replace("/", "_"), file_name=img_name, media_type=media_type, content=img_bytes
                    )
                )
            if pr.html:
                html_parts.append(pr.html)

        chap_file = f"chap_{i + 1:02d}.xhtml"
        epub_chap = epub.EpubHtml(title=chap.title, file_name=chap_file, lang=book.language)
        epub_chap.content = "\n".join(html_parts)
        epub_chap.add_item(css)
        book.add_item(epub_chap)
        chapter_items.append(epub_chap)
        logger.info("Bölüm eklendi: %s (sayfa %s-%s)", chap.title, chap.start_page, chap.end_page)

    book.toc = tuple(chapter_items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapter_items

    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Tek-process kolaylık sarmalayıcısı (testler + küçük PDF'ler için)
# ---------------------------------------------------------------------------

def convert_pdf_to_epub(pdf_bytes: bytes, config: dict[str, Any], force_ocr: bool = False) -> bytes:
    """Plan -> map -> reduce fazlarını tek bir process içinde sırayla çalıştırır.

    Modal'daki gerçek dağıtık akış (`main.py`) bu üç fazı ayrı container'lara
    böler; bu fonksiyon aynı sonucu tek process'te üretir (testler ve küçük
    PDF'ler için pratik bir kolaylık — davranış olarak eşdeğerdir).
    """
    plan = plan_conversion(pdf_bytes, dict(config))
    page_results: list[PageResult] = []
    for start_page, end_page in plan.chunks:
        page_results.extend(
            process_page_range(pdf_bytes, start_page, end_page, plan.resolved_config, force_ocr=force_ocr)
        )
    return assemble_epub(plan, page_results)
