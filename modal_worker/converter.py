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

import hashlib
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


# text_to_html_blocks'un "kısa tek satır -> h2" sezgiselinin YANLIŞ tetiklenmemesi için
# kara liste sinyalleri. Amaç kısa gerçek alt başlıkları (ör. "İntro", "4.1 Kayaların
# Mineralojik ve Petrografik Özellikleri") yakalamak; ama tablo/denklem/kaynakça-ağırlıklı
# belgelerde (bkz. ROADMAP.md madde 1, book-with-images_966108'de 721 sahte h2 bulundu)
# aynı sezgisel denklem parçalarını, eksen etiketlerini ve TOC nokta-dolgularını da
# başlık sanıyordu -- bunlar metinsel olarak "gerçek başlık" sınıfından ayırt edilebilir,
# tablo hücresi/liste kelimesi gibi daha belirsiz durumlar (ör. "Numune", "Doku") ise
# yazı tipi/boyut bilgisi olmadan güvenilir ayırt edilemediğinden kapsam dışı bırakıldı.
_HEADING_MATH_CHARS = "∑∆√±≤≥×÷−=∫∂∞"


def _looks_like_math_or_citation(text: str) -> bool:
    """Yunan harfi/matematiksel Unicode blok karakteri (denklem), sembol fontu kaçağı
    (Private Use Area, ör. Symbol fontundaki φ/τ karşılıkları), parantez içinde 4
    haneli bir yıl (kaynakça/atıf parçası, ör. "(İmre, 2011)") veya TOC nokta-dolgusu
    (ör. "ÖZGEÇMİŞ.......... 139") içeriyorsa gerçek bir başlık DEĞİL, gövde metninden
    kopmuş bir parça sayılır."""
    if any(ch in _HEADING_MATH_CHARS for ch in text):
        return True
    for ch in text:
        cp = ord(ch)
        if 0x0370 <= cp <= 0x03FF or 0x1D400 <= cp <= 0x1D7FF or 0xE000 <= cp <= 0xF8FF:
            return True
    if re.search(r"\(\s*[^)]*\d{4}[^)]*\)", text) or text.startswith("("):
        return True
    if re.search(r"\.{4,}", text):
        return True
    return False


def _looks_like_axis_label(text: str) -> bool:
    """Grafik eksen etiketleri/kısa kod çiftleri gibi (ör. "a b", "0 100 200 300") her
    "kelimesi" 2 karakter veya daha kısa olan ya da tamamen rakam+boşluktan oluşan
    satırlar -- gerçek başlıklarda en az bir okunabilir kelime bulunur."""
    words = text.split()
    if not words:
        return False
    if all(len(w) <= 2 for w in words):
        return True
    if re.fullmatch(r"[\d\s.,-]+", text):
        return True
    return False


HEADING_FONT_SIZE_RATIO = 1.15  # gövde punto boyutunun bu kat ve üzeri satırlar başlık adayı sayılır
_BOLD_FONT_FLAG = 1 << 4  # PyMuPDF span "flags" bitfield: bit 4 = kalın (bold)


def _is_bold_span(font_name: str, flags: int) -> bool:
    """PyMuPDF'in span düzeyinde döndürdüğü `flags` bitfield'ı (bit 4 = kalın)
    çoğu font için güvenilir, ama bazı özel/gömülü fontlarda hiç set edilmeyip
    yalnızca font ADINA (`...-Bold`, `...Bd` vb.) yansıyabiliyor -- ikisi
    birden kontrol ediliyor."""
    return bool(flags & _BOLD_FONT_FLAG) or "bold" in (font_name or "").lower()


def _looks_like_heading_font(font_size: float, is_bold: bool, body_font_size: float | None) -> bool:
    """Bir satırın punto boyutu/kalınlığı, sağlanan gövde metni punto
    boyutuna göre başlık gibi mi görünüyor? `body_font_size` bilinmiyorsa
    (ör. font bilgisi taşımayan eski çağrı yolları) her zaman True döner --
    yani font kontrolü devre dışı kalır, karar salt şekil sezgiseline kalır."""
    if not body_font_size:
        return True
    return is_bold or font_size >= body_font_size * HEADING_FONT_SIZE_RATIO


def _paragraph_text_to_html(
    paragraph_text: str,
    font_size: float | None = None,
    is_bold: bool = False,
    body_font_size: float | None = None,
) -> str | None:
    """Tek bir (birden fazla satır içerebilen) paragraf metnini `<h2>` ya da
    `<p>`'ye çevirir -- `text_to_html_blocks`'un asıl sezgiseli, blok-bazlı
    (sayfa-içi görsellerle harmanlanan) akışın da (bkz. `_build_interleaved_page_html`)
    aynı başlık/paragraf mantığını kullanabilmesi için ayrı bir fonksiyona çıkarıldı.

    `font_size`/`is_bold`/`body_font_size` yalnızca font bilgisi taşıyan
    çağıranlarda (gömülü metin katmanlı sayfalar) doludur -- o durumda kısa/
    noktalamasız bir satırın gerçekten `<h2>` sayılması için şekil sezgiselinin
    yanına punto/kalınlık kontrolü de eklenir (bkz. ROADMAP.md madde 1: aksi
    halde gövdeyle AYNI boyuttaki kısa satırlar -- ör. bir UI kılavuzundaki
    "Kaydır", "Detay 1" gibi kısa etiketler -- yanlışlıkla başlık sayılıyordu)."""
    lines = [line.strip() for line in paragraph_text.splitlines() if line.strip()]
    if not lines:
        return None

    is_heading_shaped = len(lines) == 1 and len(lines[0].split()) <= 6 and not re.search(r"[.!?]$", lines[0])
    is_heading = (
        is_heading_shaped
        and not _looks_like_math_or_citation(lines[0])
        and not _looks_like_axis_label(lines[0])
        and _looks_like_heading_font(font_size or 0.0, is_bold, body_font_size)
    )
    if is_heading:
        return f"<h2>{html.escape(lines[0])}</h2>"

    block_text = " ".join(lines)
    return f"<p>{html.escape(block_text)}</p>"


def text_to_html_blocks(text: str) -> str:
    """Metni başlık ve paragraf bloklarına dönüştürür."""
    cleaned = clean_text(text)
    if not cleaned:
        return ""

    paragraphs = re.split(r"\n\s*\n", cleaned)
    html_blocks = [block for block in (_paragraph_text_to_html(p) for p in paragraphs) if block is not None]
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


_SENTENCE_END_CHARS = ".!?:;…\"'”’)»›」"
MARGIN_CONTINUATION_X_TOLERANCE = 30.0  # bir bloğun, üstündeki bloğun devamı sayılması için izin verilen x0 farkı (pt)
MARGIN_CONTINUATION_MIN_GAP = 12.0  # dikey boşluk eşiği için taban (çok kısa bloklarda satır yüksekliği yetersiz kalmasın diye)


def _looks_like_paragraph_continuation(
    all_blocks: list[tuple[float, float, float, float, str]], x0: float, y0: float, y1: float
) -> bool:
    """Kenar payı şeridindeki KISA bir blok, gerçekten tekrarlayan bir koşu
    başlığı/sayfa no mu, yoksa hemen üstündeki (şerit dışındaki) bir
    paragrafın normal satır sarmasıyla oraya düşmüş devamı mı? Hemen üstünde
    (küçük dikey boşluk, benzer x0) duran ve NOKTALAMAYLA BİTMEYEN (cümle
    tamamlanmamış) bir blok varsa bu bir devam satırıdır -- gerçek koşu
    başlıkları/sayfa no'ları sayfada YALNIZ başına durur, üstlerinde yarım
    kalan bir cümle olmaz. Bkz. NOTES.md/ROADMAP.md: `book-with-images_966108`
    sayfa 30'da agresif kalibre edilmiş (%15) bir üst kenar payı yüzünden
    "dayanımı tayin edilmiştir." gibi bir paragraf kuyruğu sessizce
    kayboluyordu."""
    height = max(y1 - y0, 1.0)
    gap_threshold = max(height * 1.5, MARGIN_CONTINUATION_MIN_GAP)
    for ox0, _oy0, _ox1, oy1, other_text in all_blocks:
        if oy1 > y0 or oy1 < y0 - gap_threshold:
            continue
        if abs(ox0 - x0) > MARGIN_CONTINUATION_X_TOLERANCE:
            continue
        stripped = other_text.rstrip()
        if not stripped or stripped[-1] in _SENTENCE_END_CHARS:
            continue
        return True
    return False


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


def _merge_blocks_into_paragraphs(
    blocks: list[tuple[float, float, float, float, str, float, bool]],
) -> list[tuple[str, float, bool]]:
    """Bir sayfadaki (x0, y0, x1, y1, metin, punto, kalın-mı) bloklarini gercek
    paragraflara birlestirir, her paragraf icin de (metin, punto, kalın-mı)
    dondurur -- punto/kalınlık, paragrafi baslatan İLK (birleştirilmemiş) bloktan
    alınır. Bu yalnizca paragraf TEK SATIRLIK kaldığında (yani hiç başka blokla
    birleşmediğinde) anlamlıdır -- başlık adayı kararı zaten yalnızca o durumda
    bu bilgiyi kullanıyor (bkz. `_paragraph_text_to_html`); çok-bloklu birleşik
    paragraflarda bu değerler kullanılmıyor, rastgele/önemsiz kalabilir.

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
        heights = [y1 - y0 for _, y0, _, y1, _, _, _ in single_line_blocks]
        line_height = statistics.median(heights)

        gaps = [single_line_blocks[i][1] - single_line_blocks[i - 1][3] for i in range(1, len(single_line_blocks))]
        normal_gaps = [g for g in gaps if g <= line_height * 1.5]
        typical_gap = statistics.median(normal_gaps) if normal_gaps else line_height * 0.6

        flush_x0 = min(x0 for x0, _, _, _, _, _, _ in single_line_blocks)
        indent_threshold = flush_x0 + max(PARAGRAPH_INDENT_MIN_PT, line_height * PARAGRAPH_INDENT_LINE_HEIGHT_RATIO)
    else:
        typical_gap = indent_threshold = None

    paragraphs: list[tuple[str, float, bool]] = []
    current_lines: list[str] = []
    current_is_multiline = False
    current_font: tuple[float, bool] = (0.0, False)
    prev_y1: float | None = None

    for x0, y0, _x1, y1, text, size, bold in blocks:
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
            paragraphs.append(("\n".join(current_lines), current_font[0], current_font[1]))
            current_lines = []

        if not current_lines:
            current_font = (size, bold)
        current_lines.append(text)
        current_is_multiline = is_multiline
        prev_y1 = y1

    if current_lines:
        paragraphs.append(("\n".join(current_lines), current_font[0], current_font[1]))

    return paragraphs


COLUMN_SPAN_WIDTH_RATIO = 0.5  # bir bloğun tam-genişlik (span) ADAYI sayılması için minimum genişlik oranı
COLUMN_BAND_GAP_MARGIN_RATIO = 0.06  # aynı sütuna ait blokları birleştirirken tolere edilen boşluk payı -- paragraf ilk-satır girintisini (tek sütunlu sayfalarda x0'ı iki gruba ayırabilen ~1-3em'lik sapma) yutacak kadar geniş, ama gerçek sütun-arası boşluktan (gözlenen minimum ~150pt) belirgin biçimde dar
COLUMN_MIN_BLOCKS_PER_COLUMN = 3  # bu sayının altında blok içeren aday bant sütun sayılmaz (yanlış-pozitif riski)
COLUMN_MIN_TOTAL_BLOCK_RATIO = 0.6  # sütun bantlarındaki bloklar, sayfadaki tüm blokların en az bu oranını oluşturmalı
COLUMN_MAX_COUNT = 6  # makul sütun sayısı üst sınırı (gürültülü/yanlış bant tespitini sınırlamak için)
COLUMN_MIN_BLOCK_WIDTH_RATIO = 0.08  # bant içindeki EN GENİŞ bloğun genişliği sayfa genişliğinin en az bu oranı olmalı


def _detect_column_bands(
    blocks: list[tuple[float, float, float, float, str]], page_width: float
) -> list[tuple[float, float]] | None:
    """Blokları x-aralığına göre soldan sağa sütun bantlarına ayırır.

    Genişliği `COLUMN_SPAN_WIDTH_RATIO`'dan fazla olan bloklar (başlık,
    tam-genişlik şekil/tablo) aday havuzuna alınmaz -- bunlar birden fazla
    sütunu köprüleyip bantları birbirine karıştırır. Kalan bloklar x0'a
    göre sıralanıp SADECE x0 yakınlığına (bir önceki bloğun x0'ına göre)
    bakılarak gruplanır -- kasıtlı olarak x1'e (bloğun sağ kenarına)
    BAKILMAZ, çünkü bir grubun x1'ini genişletmeye dayalı bir birleştirme,
    iki gerçek sütun arasındaki dar bir boşluğu köprüleyen tek bir geniş
    blok (ör. altında iki sütuna yayılan bir görsel altyazısı) yüzünden
    komşu sütunları yanlışlıkla birleştirebilir -- bu bant sadece o bloğun
    KENDİ x0'ına göre konumlanır, x1'i diğer blokların gruplamasını
    etkilemez. Her sütundaki paragraflar aynı sol hizaya (x0) yaslandığından
    bu, gerçek sütun sınırlarını (paragraf genişliği ne olursa olsun) güvenilir
    şekilde ayırır. En az 2 bant, her bantta en az `COLUMN_MIN_BLOCKS_PER_COLUMN`
    blok, her bantın EN GENİŞ bloğu sayfa genişliğinin en az
    `COLUMN_MIN_BLOCK_WIDTH_RATIO`'sunu kaplaması (harita/diyagram üzerine
    serpiştirilmiş küçük etiketlerin -- ör. yükseklik/mesafe rakamları --
    tesadüfen aynı x0'da kümelenip sahte "sütun" sayılmasını engeller, bkz.
    NOTES.md -- gerçek bir sütunda en az bir satır sütun genişliğine yakın
    uzunlukta olur, oysa dağınık etiketler hep dar tek kelimeliktir) ve
    bantlardaki blokların toplamının sayfadaki tüm bloklara oranı
    `COLUMN_MIN_TOTAL_BLOCK_RATIO`'yu karşılaması gerekir -- yoksa None
    döner (tek sütun kabul edilir)."""
    span_width = page_width * COLUMN_SPAN_WIDTH_RATIO
    candidates = sorted((b for b in blocks if (b[2] - b[0]) < span_width), key=lambda b: b[0])
    if len(candidates) < COLUMN_MIN_BLOCKS_PER_COLUMN * 2:
        return None

    gap_threshold = page_width * COLUMN_BAND_GAP_MARGIN_RATIO
    groups: list[list[tuple]] = []
    for block in candidates:
        if groups and block[0] - groups[-1][-1][0] <= gap_threshold:
            groups[-1].append(block)
        else:
            groups.append([block])

    min_block_width = page_width * COLUMN_MIN_BLOCK_WIDTH_RATIO
    kept = [
        g
        for g in groups
        if len(g) >= COLUMN_MIN_BLOCKS_PER_COLUMN
        and max(b[2] - b[0] for b in g) >= min_block_width
        # zincirleme (ardışık-çift) x0 gruplaması, aralarındaki adımlar küçük
        # olsa bile TOPLAMDA sürüklenip (ör. ortalanmış bir başlık altındaki
        # değişen uzunlukta isim listesi) gerçek bir sütunu taklit edebilir --
        # bir sütunun tüm blokları aynı sol hizaya yaslandığından grup içi
        # x0 YAYILIMI (spread) da `gap_threshold`'u aşmamalı.
        and (max(b[0] for b in g) - min(b[0] for b in g)) <= gap_threshold
    ]
    if len(kept) < 2 or len(kept) > COLUMN_MAX_COUNT:
        return None
    if sum(len(g) for g in kept) / len(blocks) < COLUMN_MIN_TOTAL_BLOCK_RATIO:
        return None

    return [(min(b[0] for b in g), max(b[2] for b in g)) for g in kept]


def _classify_block_band(block: tuple, band_ranges: list[tuple[float, float]]) -> int | None:
    """Bir bloğu, x-aralığı kesişen bant(lar)a göre sınıflandırır. Tam olarak
    tek bir bantla kesişiyorsa o bantın index'ini, hiçbiriyle kesişmiyorsa
    (bantlar arası boşlukta/kenar boşluğunda kalan bir blok -- merkezine en
    yakın banda atanır) en yakın bantın index'ini, İKİ VEYA DAHA FAZLA
    bantla kesişiyorsa (gerçek tam-genişlik span -- başlık/şekil) None
    döner. Bantlar `_detect_column_bands` tarafından üst üste binmeyecek
    şekilde üretildiğinden, bandı üreten bloklar her zaman kendi bantlarıyla
    kesişir ve komşu banda taşmaz."""
    x0, x1 = block[0], block[2]
    overlaps = [i for i, (bx0, bx1) in enumerate(band_ranges) if x1 > bx0 and x0 < bx1]
    if len(overlaps) == 1:
        return overlaps[0]
    if len(overlaps) >= 2:
        return None

    mid = (x0 + x1) / 2
    return min(range(len(band_ranges)), key=lambda i: abs(mid - (band_ranges[i][0] + band_ranges[i][1]) / 2))


def _split_into_reading_order_segments(
    blocks: list[tuple[float, float, float, float, str]], page_width: float
) -> list[list[tuple[float, float, float, float, str]]]:
    """`page.get_text('blocks', sort=True)`'in kendi sıralaması yalnızca
    y-sonra-x'e göre çalışır -- tek sütunlu sayfalarda doğru, ama ÇOK
    SÜTUNLU sayfalarda (akademik makaleler, dergi/rehber tarzı düzenler)
    sütun bloklarını aynı yükseklikte satır satır iç içe geçirir; oysa
    gerçek okuma sırası önce tüm ilk sütun, sonra tüm ikinci sütun, ...
    olmalı (sütun sayısı 2 ile sınırlı değil).

    Sayfa gerçekten çok sütunluysa (bkz. `_detect_column_bands`) bloğu bu
    kurala göre "bölüm"lere ayırır -- tam genişlik kaplayan bloklar
    (başlık, tam-genişlik şekil/tablo) bir bölümü kapatıp kendi bölümü
    olarak araya girer. Sonucu tek bir düz blok listesi DEĞİL, bölümlerin
    listesi olarak döner -- her bölüm çağıran tarafından ayrı ayrı
    `_merge_blocks_into_paragraphs`'a verilmeli, çünkü o fonksiyonun
    girinti tespiti tüm bloklarda TEK bir global sol-hiza (`flush_x0`)
    varsayıyor; sütunlar aynı pas'ta birleştirilirse sonraki sütunların her
    satırı öncekine göre "girintili" görünüp yanlışlıkla ayrı birer
    paragrafa bölünür.

    Çok sütunlu olduğu net değilse (tek sütun -- golden set'in büyük
    çoğunluğu), TEK bir bölüm olarak, mevcut y-sonra-x sırasıyla döner —
    yani tek sütunlu sayfalarda davranış hiç değişmez.

    Blok tuple'ının yalnızca ilk dört alanı (x0, y0, x1, y1) geometri için
    kullanılır -- gerisi (metin, ya da `_build_interleaved_page_html`'in
    metin/görsel ayrımı için eklediği ekstra alanlar) dokunulmadan aynı
    tuple içinde taşınır, bu fonksiyon tuple'ın uzunluğuna bağlı değildir."""
    if not blocks:
        return []

    band_ranges = _detect_column_bands(blocks, page_width)
    if band_ranges is None:
        return [sorted(blocks, key=lambda b: (b[1], b[0]))]

    ordered_indices = sorted(range(len(blocks)), key=lambda i: blocks[i][1])
    segments: list[list[tuple[float, float, float, float, str]]] = []
    sections: list[list[tuple[float, float, float, float, str]]] = [[] for _ in band_ranges]

    def _flush_sections() -> None:
        for section in sections:
            if section:
                segments.append(sorted(section, key=lambda b: b[1]))
                section.clear()

    for i in ordered_indices:
        block = blocks[i]
        band_idx = _classify_block_band(block, band_ranges)
        if band_idx is None:
            _flush_sections()
            segments.append([block])
        else:
            sections[band_idx].append(block)
    _flush_sections()

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


def _block_text_and_font(block: dict) -> tuple[str, float, bool]:
    """`page.get_text('dict')`'in bir metin bloğundan, `get_text('blocks')`'un
    ürettiğiyle aynı biçimde (satırlar `\\n` ile birleşik) düz metni, ve
    bloğun İLK span'ından temsili punto boyutu/kalınlığını çıkarır. Gerçek
    başlıklar (ve genelde gövde paragrafları da) tek span'lık tekdüze
    bloklar olduğundan bu yeterli -- yalnızca TEK SATIRLIK/tek-blokluk
    paragrafların başlık kararında kullanıldığından (bkz.
    `_merge_blocks_into_paragraphs`), çok satırlı bloklardaki olası
    stil farklılığı sonucu etkilemiyor."""
    lines_text = []
    size = 0.0
    bold = False
    first_span_seen = False
    for line in block.get("lines", []):
        line_text = "".join(span.get("text", "") for span in line.get("spans", []))
        lines_text.append(line_text)
        if not first_span_seen:
            for span in line.get("spans", []):
                size = span.get("size", 0.0)
                bold = _is_bold_span(span.get("font", ""), span.get("flags", 0))
                first_span_seen = True
                break
    return "\n".join(lines_text), size, bold


def _collect_filtered_text_blocks(
    page,
    blacklist: set[str] | None = None,
    top_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
    bottom_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
) -> list[tuple[float, float, float, float, str, float, bool]]:
    """Sayfadaki metin bloklarını PyMuPDF'ten (`get_text('dict')`, punto/
    kalınlık bilgisi taşıması için -- bkz. ROADMAP.md madde 1) okuyup üç
    sezgisel filtre uygular: (1) sayfanın üst/alt kenar payındaki kısa
    bloklar (koşu başlığı/sayfa no) atlanır, (2) kitap başlığı/yazarıyla
    eşleşen bloklar (kara liste) atlanır, (3) hiç harf içermeyen kısa veya
    tek karakterlik bloklar (gürültü) atlanır.

    Ham `(x0, y0, x1, y1, metin, punto, kalın-mı)` konumlarını (paragraf
    birleştirmesi yapılmadan) döner -- hem `_extract_text_blocks`'un (paragraf
    sınırı çıkarımı) hem `_build_interleaved_page_html`'in (görsellerle konum
    bazlı harmanlama) hem `detect_chapters`'ın (font-boyutu bölüm tespiti)
    ortak temeli."""
    try:
        raw_blocks = page.get_text("dict").get("blocks", [])
    except Exception:
        return []

    page_height = page.rect.height
    has_macroman_font = _page_has_macroman_font(page)

    # İki geçişli: önce TÜM metin bloklarının konumu/metni (filtre uygulanmadan)
    # toplanıyor -- kenar payı filtresinin "bu blok gerçekten yalnız başına
    # duran bir koşu başlığı/sayfa no mu, yoksa üstündeki bir paragrafın
    # devamı mı" ayrımını yapabilmesi (`_looks_like_paragraph_continuation`)
    # için tüm sayfanın bağlamına ihtiyacı var.
    positioned: list[tuple[float, float, float, float, str, float, bool]] = []
    for block in raw_blocks:
        if block.get("type") != 0:  # yalnızca metin blokları (1 = görsel)
            continue
        raw_text, size, bold = _block_text_and_font(block)
        text = _fix_mac_turkish_mojibake(raw_text.strip(), has_macroman_font)
        if not text:
            continue
        x0, y0, x1, y1 = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
        positioned.append((x0, y0, x1, y1, text, size, bold))

    all_positions = [(x0, y0, x1, y1, text) for x0, y0, x1, y1, text, _size, _bold in positioned]

    kept: list[tuple[float, float, float, float, str, float, bool]] = []
    for x0, y0, x1, y1, text, size, bold in positioned:
        if (
            _is_in_margin((x0, y0, x1, y1), page_height, top_margin_ratio, bottom_margin_ratio)
            and len(text) <= HEADER_FOOTER_MAX_CHARS
            and not _looks_like_paragraph_continuation(all_positions, x0, y0, y1)
        ):
            continue
        if _is_blacklisted(text, blacklist or set()):
            continue
        if _is_noise_block(text):
            continue
        kept.append((x0, y0, x1, y1, text, size, bold))
    return kept


def _extract_text_blocks(
    page,
    blacklist: set[str] | None = None,
    top_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
    bottom_margin_ratio: float = HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
) -> list[str]:
    """Sayfayı PyMuPDF'in blok bazlı çıkarımıyla okur, filtrelenmiş blokları
    gerçek paragraflara birleştirir (bkz. `_merge_blocks_into_paragraphs`).
    Filtrelenmiş bloklar, iki sütunlu sayfalarda okuma sırasını koruyacak
    şekilde önce bölümlere ayrılır (bkz. `_split_into_reading_order_segments`)."""
    kept = _collect_filtered_text_blocks(page, blacklist, top_margin_ratio, bottom_margin_ratio)
    paragraphs: list[str] = []
    for segment in _split_into_reading_order_segments(kept, page.rect.width):
        paragraphs.extend(text for text, _size, _bold in _merge_blocks_into_paragraphs(segment))
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

    kept: list[tuple[float, float, float, float, str, float, bool]] = []
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
        # OCR çıktısının gerçek bir punto boyutu yok -- (0.0, False) dummy
        # değerleri, `_merge_blocks_into_paragraphs`'ın ortak (font-farkındalı)
        # imzasına uymak için var, başlık kararında kullanılmıyor (bu yol
        # yalnızca `_paragraph_text_to_html`'i font bilgisi VERMEDEN çağıran
        # eski düz `text_to_html_blocks` akışında tüketiliyor).
        kept.append((x0, y0, x1, y1, text, 0.0, False))

    return [text for text, _size, _bold in _merge_blocks_into_paragraphs(kept)]


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


MIN_EMBEDDED_IMAGE_DISPLAY_PT = 30.0  # bu boyuttan (nokta, sayfadaki GÖRÜNEN/render boyutu) küçük gömülü görseller ikon/madde imi/süsleme sayılıp atlanır

_EPUB_CORE_IMAGE_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
}


def extract_embedded_page_images(
    doc, page_index: int, page_num: int
) -> list[tuple[float, float, float, float, str, bytes, str]]:
    """Sayfadaki, metinle karışık gömülü görselleri (fotoğraf/figür/diyagram)
    çıkarır -- `(x0, y0, x1, y1, dosya adı, bayt, media_type)` yedilileri döner;
    konum, çağıranın (bkz. `_build_interleaved_page_html`) görseli metin
    akışındaki gerçek yerine (sayfa sonuna değil) yerleştirebilmesi içindir.

    Önceden `_extract_text_blocks` yalnızca metin bloklarını işliyordu
    (`block[6] != 0` filtresiyle görsel bloklar atlanıyordu) ve normal metin
    sayfalarındaki gömülü görseller hiç çıkarılmıyordu (yalnızca
    `diagram_pages`/tam-sayfa-görsel fallback'inde korunuyorlardı) — bkz.
    NOTES.md. Bu fonksiyon o boşluğu dolduruyor.

    Üç savunma: (1) sayfada gerçekten hiç ÇİZİLMEMİŞ (`get_image_rects` boş
    dönen) görseller atlanır -- `page.get_images(full=True)`, sayfanın
    kaynak sözlüğünde REFERANS EDİLEN her xref'i döner, bunların hepsi
    içerik akışında görünür şekilde yerleştirilmiş olmak zorunda değil (ör.
    kullanılmayan bir kaynak, başka bir sayfayla paylaşılan ama bu sayfada
    çizilmeyen bir XObject) -- bu durumda görseli yine de eklemek, sayfada
    gerçekte hiç görünmeyen bir `<img>` üretir (bkz. ROADMAP.md madde 2,
    `book-with-images_966108` sayfa 17'de xref=2 için gözlendi). Aynı xref
    birden fazla yerde çizilmişse konum için İLK dönen dikdörtgen kullanılır.
    (2) küçük ikon/madde imi/süsleme görseller atlanır -- ama filtre artık
    görselin PDF içindeki HAM piksel boyutuna değil, sayfada GÖRÜNEN
    (dikdörtgenin nokta cinsinden) boyutuna bakıyor (`MIN_EMBEDDED_IMAGE_DISPLAY_PT`)
    -- eskiden ham piksel boyutu kullanılıyordu, bu da küçük gösterilen büyük
    bir görseli kaçırıp büyük-ama-küçük-basılan bir görseli yanlışlıkla
    tutabiliyordu (bkz. ROADMAP.md madde 2). (3) EPUB'ın çekirdek medya
    tiplerinde olmayan formatlar (ör. JP2/JPX, CMYK JPEG) Pillow ile JPEG'e
    yeniden kodlanır; Pillow da açamazsa (bozuk/desteklenmeyen kodek) o
    görsel sessizce atlanır -- tek bozuk bir görsel yüzünden tüm sayfanın
    metni kaybolmamalı."""
    images: list[tuple[float, float, float, float, str, bytes, str]] = []
    seen_xrefs: set[int] = set()
    page = doc[page_index]

    for img_index, img in enumerate(page.get_images(full=True)):
        xref = img[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        rects = page.get_image_rects(xref)
        if not rects:
            continue
        rect = rects[0]
        if rect.width < MIN_EMBEDDED_IMAGE_DISPLAY_PT or rect.height < MIN_EMBEDDED_IMAGE_DISPLAY_PT:
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
        images.append((rect.x0, rect.y0, rect.x1, rect.y1, img_name, image_bytes, media_type))

    return images


# ---------------------------------------------------------------------------
# Otomatik tespit (bölümler / başlık / yazar) — `/analyze` ve plan fazı kullanır
# ---------------------------------------------------------------------------

CHAPTER_HEADING_MIN_WORDS = 2  # tek harf/kısaltmalar (ör. dizin sayfalarındaki "A","B","C") elenir
CHAPTER_HEADING_MAX_WORDS = 12  # çok uzun satırlar (yanlışlıkla büyük/kalın basılmış bir cümle) elenir
CHAPTER_TIER_RATIO = 0.9  # gömülü-metin (punto) adayları için: yalnızca en büyük katmana yakın olanlar
CHAPTER_TIER_RATIO_OCR = 0.75  # OCR (piksel satır yüksekliği) adayları için -- ölçüm daha gürültülü, gerçek örnekte (bkz. scanned_002) aynı bölüm başlığı stilinde bile ~%25'e varan yükseklik sapması gözlendi
CHAPTER_OUTLIER_CAP_RATIO = 2.0  # medyanın bu katından büyük TEK seferlik bir aday (ör. bir kapak illüstrasyonunun OCR yanlış okuması) tavan hesaplamasından hariç tutulur
CHAPTER_MIN_PAGE_GAP = 2  # ardışık iki bölüm başlığı arasında beklenen en az sayfa farkı (kısa bir "Giriş" bölümünü bir sonraki bölümden ayırt edecek kadar gevşek)
CHAPTER_OCR_SAMPLE_STRIDE = 5  # taranmış (embedded metni olmayan) sayfalarda kaç sayfada bir örnek OCR'lanır
CHAPTER_OCR_MAX_SAMPLES = 60  # çok uzun taranmış kitaplarda maliyeti sınırlamak için üst sınır


def _is_chapter_heading_shaped(text: str) -> bool:
    if not any(ch.isalpha() for ch in text):
        return False  # salt noktalama/süsleme (ör. "◆ ◆ ◆" bölüm-ayracı) bir başlık olamaz
    word_count = len(text.split())
    return CHAPTER_HEADING_MIN_WORDS <= word_count <= CHAPTER_HEADING_MAX_WORDS


def _is_mostly_uppercase(text: str, min_ratio: float = 0.8) -> bool:
    """OCR (piksel yükseklik) adayları için ek bir güvenilirlik süzgeci --
    gerçek bölüm başlıkları tipografik olarak sıkça BÜYÜK HARFLE dizilir,
    gövde metni ise değil. Gömülü-metin yolunun aksine (font/kalınlık
    metadata'sı var) OCR yolunda tek sinyal piksel satır yüksekliği, ve bu
    tek başına yetersiz kalabiliyor: gerçek bir örnekte (`scanned_001`, hiç
    gömülü metni olmayan, kötü kalite bir tarama), sayfa başına örneklenen
    OCR satırları arasında gerçek bir başlık YOKKEN bile rastgele gürültü
    (bir satırın biraz daha büyük ölçülmesi) 40'tan fazla sahte "bölüm"
    üretmişti -- hiçbiri büyük harfle değildi, sıradan gövde cümleleriydi."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    return sum(1 for ch in letters if ch.isupper()) / len(letters) >= min_ratio


_TURKISH_ASCII_FOLD = str.maketrans(
    {"İ": "I", "ı": "i", "Ü": "U", "ü": "u", "Ö": "O", "ö": "o", "Ç": "C", "ç": "c", "Ş": "S", "ş": "s", "Ğ": "G", "ğ": "g"}
)


def _fold_turkish_for_loose_match(text: str) -> str:
    """Türkçe'ye özgü harfleri ASCII karşılıklarına çevirip küçük harfe indirger
    -- `.casefold()` Türkçe İ/ı için beklenmedik sonuçlar üretir (`"İ".casefold()`
    tek bir "i" değil, "i" + birleşen nokta işareti verir), bu yüzden ÖNCE
    Türkçe harfleri ASCII'ye çevirip SONRA `.lower()` uyguluyoruz. Bir gerçek
    örnekte, kitabın kapak sayfasındaki başlık ("BiR GUN") gömülü fontta
    Türkçe aksanları (ü, İ) kaybetmiş şekilde çıkarılmıştı -- gerçek başlıkla
    ("Bir Gün") harfiyen karşılaştırma bu yüzden zaten başarısız olurdu; bu
    katlama olmadan bile normal casefold tek başına yetmezdi."""
    return re.sub(r"\s+", " ", text.translate(_TURKISH_ASCII_FOLD)).strip().lower()


def _matches_known_title_or_author(text: str, title: str | None, author: str | None) -> bool:
    """Bir bölüm başlığı adayı, kitabın kendi (kapaktan/metadata'dan tespit
    edilen) başlığı ya da yazarıyla mı örtüşüyor? Gerçek bir örnekte
    (`scanned_002`) kitabın başlığı ("Bir Gün Kediler Dünyadan Yok Olsaydı")
    kapak/başlık sayfasında BÜYÜK puntoyla iki kez tekrarlıyordu -- bunlar
    metinsel olarak gerçek bölüm başlıklarından (aynı ya da benzer büyük
    punto) ayırt edilemezdi, yalnızca "kitabın kendi başlığı" olduklarını
    bilerek elenebilirler. `_is_blacklisted` (koşu başlığı filtresi) burada
    kullanılamaz çünkü o, blacklist girdisinin (uzun başlık) aday metnin
    (kısa, başlığın yalnızca bir parçası) İÇİNDE aranmasını bekler -- burada
    ihtiyaç ters yönde (aday, başlığın bir parçası mı)."""
    normalized = _fold_turkish_for_loose_match(text)
    if len(normalized) < 3:
        return False
    for known in (title, author):
        if not known:
            continue
        known_normalized = _fold_turkish_for_loose_match(str(known))
        if len(known_normalized) < 3:
            continue
        if normalized in known_normalized or known_normalized in normalized:
            return True
    return False


def _detect_chapter_candidate_from_dict_page(page, body_font_size: float | None) -> tuple[str, float] | None:
    """Sayfanın gömülü metin katmanında en büyük punto/kalın başlık adayını
    (varsa) döner -- (metin, punto) ikilisi. Yalnızca `_looks_like_heading_font`
    testini geçen VE makul uzunlukta (`_is_chapter_heading_shaped`) satırlar
    aday sayılır; sayfadaki en büyük payı olan aday seçilir.

    `body_font_size` yoksa (belgenin tamamında güvenilir bir gövde-punto
    tabanı bulunamadıysa) bilerek HİÇBİR aday üretmiyoruz -- `_looks_like_heading_font`
    kendi başına `body_font_size is None` durumunda "her şey başlık" (True)
    döner (paragraf-başlık ayrımı bağlamında makul bir varsayılan), ama
    bölüm-tespiti bağlamında bu YIKICI: gerçek bir örnekte (`scanned_001`,
    kötü OCR'lanmış taranmış bir roman) gövde-punto tespit edilemeyince
    kitaptaki HER rastgele cümle "bölüm başlığı" sayılıp 40'tan fazla
    sahte bölüm üretiliyordu. Gövde-punto tabanı yoksa büyüklüğe güvenilecek
    hiçbir referans yok demektir -- boş liste dönmek (fallback'in üstünde,
    `detect_chapters` bunu "bölüm bulunamadı" olarak ele alır), 40 uydurma
    bölümden çok daha dürüst bir sonuç."""
    if not body_font_size:
        return None
    try:
        page_dict = page.get_text("dict")
    except Exception:
        return None

    best: tuple[float, str] | None = None
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text or not _is_chapter_heading_shaped(text):
                continue
            size = spans[0].get("size", 0.0)
            bold = _is_bold_span(spans[0].get("font", ""), spans[0].get("flags", 0))
            if not _looks_like_heading_font(size, bold, body_font_size):
                continue
            if best is None or size > best[0]:
                best = (size, text)
    return (best[1], best[0]) if best else None


def _detect_chapter_candidate_from_ocr(doc, page_index: int, ocr_lang: str) -> tuple[str, float] | None:
    """Taranmış (gömülü metni olmayan) bir sayfayı OCR'layıp en büyük satır-
    yüksekliğine sahip başlık adayını (varsa) döner -- (metin, piksel
    yüksekliği) ikilisi. Satır yüksekliği, gömülü-metin yolundaki punto
    boyutunun taranmış sayfalardaki karşılığıdır (bkz. kapak sayfası için
    aynı tekniği kullanan `_extract_cover_title_author_via_ocr`); "gövde"
    referansı olarak SAYFANIN KENDİ satırlarının medyanı kullanılıyor (ayrı
    bir doküman-geneli OCR taraması gerektirmemek için)."""
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError:
        return None

    data = _ocr_with_retry(
        doc, page_index, lambda img: pytesseract.image_to_data(img, lang=ocr_lang, output_type=Output.DICT)
    )
    if data is None:
        return None

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
        height = sum(data["height"][i] for i in indices) / len(indices)
        lines.append((height, " ".join(words)))

    if not lines:
        return None

    body_height = statistics.median(h for h, _ in lines)
    candidates = [
        (h, t)
        for h, t in lines
        if _is_chapter_heading_shaped(t) and _looks_like_heading_font(h, False, body_height) and _is_mostly_uppercase(t)
    ]
    if not candidates:
        return None
    best_height, best_text = max(candidates, key=lambda c: c[0])
    return best_text, best_height


CHAPTER_NUMBERING_PATTERN = re.compile(r"^(chapter|appendix)?\s*([0-9]+|[a-z])[.\):]\s", re.IGNORECASE)
CHAPTER_NUMBERING_MIN_MATCHES = 2  # en az bu kadar aday numaralandırma deseniyle eşleşirse, kitabın gerçekten numaralı bir bölüm şeması olduğu varsayılır


def _filter_chapter_candidates(
    candidates: list[tuple[int, str, float]], tier_ratio: float
) -> list[dict[str, Any]]:
    """TEK bir ölçüm biriminde (ya hep punto ya hep OCR piksel-yüksekliği) olan
    bir aday havuzunu nihai bölüm listesine indirger.

    Önce boyut süzgeçleri uygulanır: (1) medyanın `CHAPTER_OUTLIER_CAP_RATIO`
    katından büyük TEK seferlik uç değerler (ör. bir kapak illüstrasyonunun
    OCR yanlış okuması, gerçek bir örnekte 190px ölçülmüştü) tavan
    (`max_size`) hesabından hariç tutulur -- yoksa tek bir gürültülü aday,
    tüm gerçek adayları tavanın ALTINA düşürüp eleyebilir.

    Sonra "1. Chapter Title" / "Appendix A. ..." gibi açık bir numaralandırma
    deseniyle eşleşen adaylara bakılır: eşleşen en az
    `CHAPTER_NUMBERING_MIN_MATCHES` aday VARSA VE bu adayların kendi
    tavanı genel tavana (`tier_ratio` içinde) yakınsa, yalnızca bu
    numaralı adaylar kullanılır -- boyut katmanına bakılmaksızın (gerçek bir
    örnekte: `technical-with-code_functional-programing`, tüm gömülü
    outline düz/tek seviyeli olduğu için TOC'tan ayırt edilemeyen alt-
    başlıklarla dolu, ama gerçek bölümler HEP "N. Başlık" örüntüsünde VE en
    büyük punto katmanında). Numaralı adayların tavanı genel tavandan
    belirgin şekilde düşükse (gerçek bir örnekte:
    `book-with-images_ankaranin-trekking-rotalari`, numaralandırılmış
    olanlar aslında yürüyüş rotası alt-maddeleri, gerçek bölüm başlıkları
    numarasız ama daha büyük puntoda) numaralandırma sinyaline GÜVENİLMEZ,
    normal boyut-katmanı süzgecine düşülür: yalnızca (temizlenmiş) tavana
    yakın (`tier_ratio`) adaylar bölüm başlığı sayılır -- daha küçük
    katmanlar alt-başlık ya da dizin/sözlük ayracı olabilir.

    Her iki yolda da son adım aynı: ardışık iki aday arasında en az
    `CHAPTER_MIN_PAGE_GAP` sayfa olmalı, aynı bölgede kümelenenlerden
    yalnızca ilki alınır."""
    if not candidates:
        return []

    sizes = [size for _, _, size in candidates]
    median_size = statistics.median(sizes)
    plausible = [c for c in candidates if c[2] <= median_size * CHAPTER_OUTLIER_CAP_RATIO] or candidates
    max_size = max(size for _, _, size in plausible)

    numbered = [c for c in plausible if CHAPTER_NUMBERING_PATTERN.match(c[1].strip())]
    if len(numbered) >= CHAPTER_NUMBERING_MIN_MATCHES and max(s for _, _, s in numbered) >= max_size * tier_ratio:
        selected = sorted(((page_num, title) for page_num, title, _size in numbered), key=lambda c: c[0])
    else:
        selected = sorted(
            ((page_num, title) for page_num, title, size in plausible if size >= max_size * tier_ratio),
            key=lambda c: c[0],
        )

    chapters: list[dict[str, Any]] = []
    last_page = -CHAPTER_MIN_PAGE_GAP
    for page_num, title in selected:
        if page_num - last_page < CHAPTER_MIN_PAGE_GAP:
            continue
        chapters.append({"start_page": page_num, "title": title})
        last_page = page_num
    return chapters


def _detect_chapters_by_layout(doc, ocr_lang: str = DEFAULT_OCR_LANGUAGE) -> list[dict[str, Any]]:
    """TOC yoksa çağrılan fallback -- gömülü metin katmanı olan sayfalarda
    (ek maliyet yok, zaten okunan sayfa içeriğinden) font-boyutu/kalınlık
    sezgisiyle, hiç embedded metni olmayan (taranmış) sayfalarda ise yalnızca
    ÖRNEKLENEN sayfaları (`CHAPTER_OCR_SAMPLE_STRIDE`) OCR'layıp satır-
    yüksekliği sezgisiyle bölüm başlığı adayları arar. Örneklem yaklaşımı
    kullanıcı onayıyla seçildi (bkz. ROADMAP.md madde 3) -- tüm taranmış
    sayfaları OCR'lamanın maliyetinden/gecikmesinden kaçınmak için bazı
    bölümler kaçırılabilir.

    Gömülü-metin (punto, pt) ve OCR (satır yüksekliği, px) adayları FARKLI
    ölçüm birimlerinde olduğundan asla TEK bir havuzda kıyaslanmaz -- ilk
    denemede tam bunu yapan bir sürüm, gerçek bir taranmış kitapta (px
    biriminde) 190 değerindeki bir OCR yanlış okumasının (pt biriminde 17-23
    aralığındaki) 10 doğru bölüm adayını tavanın altına düşürüp elemesine yol
    açmıştı. Ayrıca kitabın kendi başlığı/yazarı (kapak sayfasında büyük
    puntoyla, gerçek bölüm başlıklarıyla ayırt edilemeyecek şekilde tekrar
    edebiliyor -- bkz. `_matches_known_title_or_author`) adaylardan ayrıca
    elenir."""
    total_pages = len(doc)
    body_font_size = detect_body_font_size(doc, 1, total_pages)
    title, author = detect_title_author(doc)

    embedded_candidates: list[tuple[int, str, float]] = []
    scanned_page_indices: list[int] = []

    for page_index in range(total_pages):
        page = doc[page_index]
        candidate = _detect_chapter_candidate_from_dict_page(page, body_font_size)
        if candidate is not None:
            if not _matches_known_title_or_author(candidate[0], title, author):
                embedded_candidates.append((page_index + 1, candidate[0], candidate[1]))
            continue
        try:
            has_text = bool((page.get_text() or "").strip())
        except Exception:
            has_text = False
        if not has_text:
            scanned_page_indices.append(page_index)

    ocr_candidates: list[tuple[int, str, float]] = []
    if scanned_page_indices:
        sample_indices = scanned_page_indices[::CHAPTER_OCR_SAMPLE_STRIDE][:CHAPTER_OCR_MAX_SAMPLES]
        for page_index in sample_indices:
            candidate = _detect_chapter_candidate_from_ocr(doc, page_index, ocr_lang)
            if candidate is not None and not _matches_known_title_or_author(candidate[0], title, author):
                ocr_candidates.append((page_index + 1, candidate[0], candidate[1]))

    chapters = _filter_chapter_candidates(embedded_candidates, CHAPTER_TIER_RATIO)
    chapters.extend(_filter_chapter_candidates(ocr_candidates, CHAPTER_TIER_RATIO_OCR))
    chapters.sort(key=lambda c: c["start_page"])
    return chapters


CHAPTER_TOC_MIN_PAGES_PER_CHAPTER = 2.0  # TOC'tan üretilen "bölüm" sayısı bunun altında bir sayfa/bölüm ortalaması veriyorsa (ör. sayfa başına bir bookmark) TOC güvenilmez sayılır


def _toc_chapters_look_plausible(raw_level1_count: int, total_pages: int) -> bool:
    """Bazı PDF'lerin gömülü outline'ı gerçek bölüm yapısını değil, tarayıcı
    yazılımının her sayfa için ürettiği bir dosya-adı bookmark'ını taşıyor
    (gerçek bir örnekte: `scanned_002`'nin 188 sayfası için 188 outline
    girdisi, hepsi "Kedi - 0004_1L" gibi kaynak dosya adları) ya da tamamen
    DÜZ (tek seviyeli) bir outline'da alt-başlıklar da level-1 olarak
    işaretlenmiş olabiliyor (gerçek bir örnekte:
    `technical-with-code_functional-programing`, 148 ham level-1 girdisi,
    gerçek bölüm sayısı yalnızca 7). Sayfa sayısına göre "bölüm" sayısı
    gerçekçi olmayacak kadar yüksekse (ör. ortalama <
    `CHAPTER_TOC_MIN_PAGES_PER_CHAPTER` sayfa/bölüm) TOC'a güvenmiyoruz,
    font-boyutu tabanlı fallback'e düşüyoruz -- kalibrasyon: gerçek kısa-
    makale TOC'ları (ör. 11 sayfada 5 bölüm, ~2.2 sayfa/bölüm) üstünde
    kalırken, sayfa-başına-bookmark/düz-outline örnekleri (~1.0-1.8) altında
    kalıyor. HAM (sayfa çakışmasına göre henüz deduplike edilmemiş) level-1
    sayısı kullanılır -- bazı düz outline'larda birden fazla girdi aynı
    sayfayı paylaşabiliyor (ör. "Global scope"/"Local scope" ikisi de aynı
    sayfada), bu da deduplike edilmiş sayıyı eşiğin yanlış tarafına
    kaydırabilir."""
    if raw_level1_count <= 1:
        return True
    return (total_pages / raw_level1_count) >= CHAPTER_TOC_MIN_PAGES_PER_CHAPTER


def detect_chapters(doc, ocr_lang: str = DEFAULT_OCR_LANGUAGE) -> list[dict[str, Any]]:
    """Önce PDF'in gömülü outline/bookmark'ından üst seviye bölümleri okumayı
    dener; TOC yoksa/boşsa/güvenilmezse (bkz. `_toc_chapters_look_plausible`)
    font-boyutu/kalınlık tabanlı bir fallback'e düşer (bkz.
    `_detect_chapters_by_layout`, ROADMAP.md madde 3)."""
    try:
        toc = doc.get_toc(simple=True)
    except Exception:
        toc = []

    chapters: list[dict[str, Any]] = []
    seen_pages: set[int] = set()
    raw_level1_count = 0
    for level, title, page in toc:
        if level != 1:
            continue
        clean_title = title.strip()
        if not clean_title or page < 1:
            continue
        raw_level1_count += 1
        if page in seen_pages:
            continue
        seen_pages.add(page)
        chapters.append({"start_page": page, "title": clean_title})

    chapters.sort(key=lambda c: c["start_page"])

    if chapters and not _toc_chapters_look_plausible(raw_level1_count, len(doc)):
        chapters = []

    if not chapters:
        chapters = _detect_chapters_by_layout(doc, ocr_lang)

    if chapters and chapters[0]["start_page"] > 1:
        # TOC (ya da fallback) ilk bölümden önceki (kapak/önsöz gibi) sayfaları
        # atlıyorsa, onları kaybetmemek için başa bir giriş bölümü ekliyoruz.
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
# Gövde punto tespiti — yalnızca plan fazında, madde 1'deki başlık/paragraf
# sezgiselinin ve font-boyutu tabanlı bölüm tespitinin "normal" kabul edeceği
# referans punto boyutunu üretir (bkz. ROADMAP.md madde 1)
# ---------------------------------------------------------------------------

BODY_FONT_SIZE_SAMPLE_COUNT = 10  # HEADER_FOOTER_SAMPLE_COUNT ile aynı örneklem yoğunluğu


def detect_body_font_size(
    doc, start_page: int, end_page: int, sample_count: int = BODY_FONT_SIZE_SAMPLE_COUNT
) -> float | None:
    """Kitaba yayılmış birkaç sayfayı örnekleyip gövde metninin baskın punto
    boyutunu tahmin eder -- her punto boyutunun kapladığı toplam KARAKTER
    sayısına göre (satır/blok sayısına göre değil) en çok kullanılanı seçer,
    ki kısa ama sık başlıklar çoğunluk gövde metnini domine edemesin. Yeterli
    örnek/metin yoksa None döner (çağıran taraf font-boyutu kontrolünü atlar,
    salt şekil sezgiseline döner -- bkz. `_looks_like_heading_font`)."""
    total_pages = end_page - start_page + 1
    if total_pages < 1:
        return None

    char_counts_by_size: dict[float, int] = {}
    for page_num in _sample_page_numbers(start_page, end_page, sample_count):
        page_index = page_num - 1
        if not (0 <= page_index < len(doc)):
            continue
        try:
            page_dict = doc[page_index].get_text("dict")
        except Exception:
            continue
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    char_count = len(span.get("text", "").strip())
                    if not char_count:
                        continue
                    size = round(span.get("size", 0.0), 1)
                    char_counts_by_size[size] = char_counts_by_size.get(size, 0) + char_count

    if not char_counts_by_size:
        return None
    return max(char_counts_by_size, key=char_counts_by_size.get)


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
        resolved_config["body_font_size"] = detect_body_font_size(doc, start_page, end_page)

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


def slice_pdf_pages(pdf_bytes: bytes, start_page: int, end_page: int) -> bytes:
    """1-based `[start_page, end_page]` aralığını içeren, bağımsız ve geçerli
    yeni bir PDF üretir. Modal orkestrasyonunda (`main.py`) her map-fazı
    container'ının Blob'dan orijinal PDF'in TAMAMINI indirmesi yerine yalnızca
    kendi sayfa aralığını içeren bu küçük PDF'i (plan fazında dilimlenip Modal
    RPC'siyle taşınıyor) almasını sağlamak için eklendi — bkz. NOTES.md
    (`process_chunk` egress israfı)."""
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        sub = fitz.open()
        try:
            sub.insert_pdf(src, from_page=start_page - 1, to_page=end_page - 1)
            return sub.tobytes()
        finally:
            sub.close()
    finally:
        src.close()


# ---------------------------------------------------------------------------
# Map fazı — paralel, `.map()` ile çağrılır
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    page_num: int
    html: str
    images: list[tuple[str, bytes, str]] = field(default_factory=list)  # (dosya adı, bayt, media_type)


def _flush_text_run(
    run: list[tuple[float, float, float, float, str, float, bool]],
    html_parts: list[str],
    body_font_size: float | None,
) -> None:
    """`run`'daki (tek okuma-sırası segmentindeki ardışık) metin bloklarını
    paragraflara birleştirip HTML'e ekler, `run`'ı temizler. `body_font_size`
    dolu ise (bkz. `detect_body_font_size`) başlık kararı şekil sezgiselinin
    yanına punto/kalınlık kontrolünü de ekler (bkz. ROADMAP.md madde 1)."""
    for paragraph, size, bold in _merge_blocks_into_paragraphs(run):
        block_html = _paragraph_text_to_html(clean_text(paragraph), size, bold, body_font_size)
        if block_html:
            html_parts.append(block_html)
    run.clear()


def _build_interleaved_page_html(
    doc,
    page_index: int,
    page_num: int,
    blacklist: set[str] | None,
    top_margin_ratio: float,
    bottom_margin_ratio: float,
    body_font_size: float | None = None,
) -> tuple[str, list[tuple[str, bytes, str]]]:
    """Sayfanın metin ve gömülü-görsel bloklarını TEK bir okuma-sırası akışında
    birleştirir -- görseller artık sayfanın SONUNA değil, PDF'teki gerçek
    konumlarına (ör. paragraf arasına) yerleştirilir (bkz. ROADMAP.md madde 2).

    Metin blokları (`_collect_filtered_text_blocks`) ve görsel blokları
    (`extract_embedded_page_images`) aynı (x0, y0, x1, y1, tür, veri) tuple
    biçimine getirilip `_split_into_reading_order_segments`'e (iki sütunlu
    sayfalarda sütun sırasını koruyan aynı fonksiyon) birlikte verilir; her
    segment içinde ardışık metin blokları `_merge_blocks_into_paragraphs`
    ile paragraflara birleştirilir, bir görsel bloğuna rastlanınca o ana
    kadarki paragraf akışı kapatılıp `<img>` eklenir ve paragraf birleştirme
    kaldığı yerden devam eder.

    Yalnızca gömülü metin katmanı bulunan (OCR'a düşmemiş, `force_ocr` ile
    ezilmemiş) sayfalarda kullanılır -- çağıran (`process_page`) OCR-türetilmiş
    metin için eski düz akışı kullanmaya devam eder (bkz. oradaki not:
    OCR koordinatları piksel-uzayında, PDF görselleri nokta-uzayında)."""
    page = doc[page_index]
    text_blocks = _collect_filtered_text_blocks(page, blacklist, top_margin_ratio, bottom_margin_ratio)
    image_blocks = extract_embedded_page_images(doc, page_index, page_num)

    combined: list[tuple[float, float, float, float, str, Any]] = [
        (x0, y0, x1, y1, "text", (text, size, bold)) for x0, y0, x1, y1, text, size, bold in text_blocks
    ]
    combined.extend(
        (x0, y0, x1, y1, "image", (img_name, img_bytes, media_type))
        for x0, y0, x1, y1, img_name, img_bytes, media_type in image_blocks
    )

    html_parts: list[str] = []
    images: list[tuple[str, bytes, str]] = []
    for segment in _split_into_reading_order_segments(combined, page.rect.width):
        text_run: list[tuple[float, float, float, float, str, float, bool]] = []
        for x0, y0, x1, y1, kind, payload in segment:
            if kind == "text":
                text, size, bold = payload
                text_run.append((x0, y0, x1, y1, text, size, bold))
                continue
            _flush_text_run(text_run, html_parts, body_font_size)
            img_name, img_bytes, media_type = payload
            images.append((img_name, img_bytes, media_type))
            html_parts.append(f'<img src="{img_name}" alt="Sayfa {page_num} görseli" />')
        _flush_text_run(text_run, html_parts, body_font_size)

    return "\n".join(html_parts), images


def process_page(
    doc,
    page_num: int,
    config: dict[str, Any],
    force_ocr: bool = False,
    header_blacklist: set[str] | None = None,
    doc_page_index: int | None = None,
) -> PageResult:
    """Tek bir sayfayı işler (metin/OCR/görsel), sonucu mutlak sayfa numarasıyla
    etiketlenmiş `PageResult` olarak döner — görsel dosya adları da sayfa
    numarasını içerir ki farklı chunk'larda paralel üretilen görseller
    reduce fazında çakışmasın.

    `header_blacklist`, kitap başlığı/yazarından kurulmuş bir küme --
    `extract_page_text`'e geçirilip koşu başlığı/yazar satırlarının paragraf
    olarak sızmasını engeller (bkz. `build_header_blacklist`).

    `doc_page_index`: `doc` yalnızca bir sayfa aralığını içeren dilimlenmiş
    bir PDF'se (bkz. `slice_pdf_pages`), `page_num - 1` artık `doc` içindeki
    gerçek indeksle eşleşmez -- bu durumda çağıran, `doc` içindeki gerçek
    (0-based) indeksi burada açıkça geçirir. `page_num` yine de tüm çıktı
    etiketlemesinde (görsel dosya adları, `PageResult.page_num`) MUTLAK sayfa
    numarası olarak kullanılmaya devam eder."""
    page_index = doc_page_index if doc_page_index is not None else page_num - 1
    diagram_pages = set(config.get("diagram_pages", []))
    ocr_lang = config.get("ocr_language", DEFAULT_OCR_LANGUAGE)
    visual_mode = bool(config.get("visual_mode", False))
    auto_visual_mode = bool(config.get("auto_visual_mode", False))
    image_dpi, image_quality = get_image_settings(config)
    page_captions = config.get("page_captions", {})
    top_margin_ratio = config.get("header_margin_ratio", HEADER_FOOTER_DEFAULT_MARGIN_RATIO)
    bottom_margin_ratio = config.get("footer_margin_ratio", HEADER_FOOTER_DEFAULT_MARGIN_RATIO)
    body_font_size = config.get("body_font_size")

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
    text_is_ocr_derived = is_scanned_page
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
            text_is_ocr_derived = True

    use_visual = visual_mode or (auto_visual_mode and should_use_visual_page(config, text, page_num))
    if use_visual:
        img_name = f"images/page_{page_num}.jpg"
        images.append(
            (img_name, page_to_image_bytes(doc, page_index, dpi=image_dpi, quality=image_quality), "image/jpeg")
        )
        caption = page_captions.get(str(page_num))
        html_parts.append(build_visual_page_html(page_num, img_name, caption=caption))
        return PageResult(page_num=page_num, html="\n".join(html_parts), images=images)

    # Sayfa normal metin olarak işlendi (görsele düşmedi) -- ama metinle
    # karışık gömülü görseller (fotoğraf/figür/diyagram) olabilir, bunlar
    # `extract_page_text`'in metin-blok filtresinde hiç görünmüyordu (bkz.
    # NOTES.md). `diagram_pages`'te zaten tüm sayfa görsel olarak eklendiği
    # için burada tekrar çıkarmıyoruz.
    if text_is_ocr_derived or page_num in diagram_pages:
        # OCR'dan türetilmiş metin (taranmış sayfa YA DA force_ocr) piksel-uzayı
        # koordinatlarında; gömülü görsellerin PDF-nokta-uzayı koordinatlarıyla
        # aynı sistemde değil, bu yüzden bu durumda (ve diagram_pages'te, zaten
        # tam sayfa görsel eklendiğinden) eski düz (interleave'siz) akış kullanılır.
        cleaned = clean_text(text)
        block_html = text_to_html_blocks(cleaned)
        if block_html:
            html_parts.append(block_html)
        if not is_scanned_page and page_num not in diagram_pages:
            for x0, y0, x1, y1, img_name, img_bytes, media_type in extract_embedded_page_images(
                doc, page_index, page_num
            ):
                images.append((img_name, img_bytes, media_type))
                html_parts.append(f'<img src="{img_name}" alt="Sayfa {page_num} görseli" />')
    else:
        # Normal gömülü-metin sayfası: metin ve görselleri PDF'teki gerçek
        # okuma sırasına göre TEK bir akışta harmanla (bkz. ROADMAP.md madde 2).
        page_html, page_images = _build_interleaved_page_html(
            doc, page_index, page_num, header_blacklist, top_margin_ratio, bottom_margin_ratio, body_font_size
        )
        if page_html:
            html_parts.append(page_html)
        images.extend(page_images)

    return PageResult(page_num=page_num, html="\n".join(html_parts), images=images)


def process_page_range(
    pdf_bytes: bytes,
    start_page: int,
    end_page: int,
    config: dict[str, Any],
    force_ocr: bool = False,
    sliced: bool = False,
) -> list[PageResult]:
    """Bir `(start_page, end_page)` chunk'ını işler.

    `sliced=False` (varsayılan): `pdf_bytes` kitabın TAMAMI, `page_num - 1`
    doğrudan `doc`'un indeksi (eski davranış — `convert_pdf_to_epub`/testler).

    `sliced=True`: `pdf_bytes`, `slice_pdf_pages(orijinal, start_page, end_page)`
    ile üretilmiş, yalnızca bu aralığı içeren küçük bir PDF (Modal'ın
    `process_chunk`'ı artık orijinal PDF'in tamamını Blob'dan indirmek yerine
    bunu kullanıyor, bkz. NOTES.md/`main.py`) -- `doc`'daki gerçek indeks
    `page_num - start_page`'dir, `page_num` yine de çıktıda mutlak sayfa
    numarası olarak kullanılmaya devam eder."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ConversionError(f"PDF açılamadı: {exc}") from exc

    skip_pages = set(config.get("skip_pages", []))
    doc_page_count = len(doc)
    header_blacklist = build_header_blacklist(config)
    results: list[PageResult] = []
    try:
        for page_num in range(start_page, end_page + 1):
            if page_num in skip_pages:
                continue
            doc_page_index = (page_num - start_page) if sliced else (page_num - 1)
            if doc_page_index < 0 or doc_page_index >= doc_page_count:
                continue
            results.append(
                process_page(
                    doc,
                    page_num,
                    config,
                    force_ocr=force_ocr,
                    header_blacklist=header_blacklist,
                    doc_page_index=doc_page_index,
                )
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

    # Sayfa-içi dedup (`extract_embedded_page_images`'teki `seen_xrefs`) yalnızca AYNI
    # sayfada tekrar eden xref'leri yakalıyor; aynı görsel (ör. yayınevi logosu/filigran)
    # farklı sayfalarda -- hatta farklı map-fazı container'larında -- tekrarsa her
    # tekrarda ayrı bir dosya olarak ekleniyordu (dosya adı sayfa numarasını içerdiğinden
    # xref eşitliği görünmüyor). Reduce fazı tüm `page_results`'ı tek yerde topladığından
    # (chunk sınırından bağımsız) içerik hash'ine göre kitap-geneli dedup burada güvenle
    # yapılabilir -- xref yerine gerçek bayt içeriği karşılaştırılıyor ki aynı görsel
    # farklı xref'lerle gömülmüş olsa bile (nadir ama mümkün) yine de tek kopya kalsın.
    seen_image_hashes: dict[bytes, str] = {}  # içerik hash'i -> ilk eklenen dosya adı

    chapter_items = []
    for i, chap in enumerate(plan.chapters):
        html_parts = [f"<h1>{html.escape(chap.title)}</h1>"]

        for page_num in range(chap.start_page, chap.end_page + 1):
            pr = by_page.get(page_num)
            if pr is None:
                continue
            for img_name, img_bytes, media_type in pr.images:
                content_hash = hashlib.sha256(img_bytes).digest()
                canonical_name = seen_image_hashes.get(content_hash)
                if canonical_name is not None:
                    if canonical_name != img_name:
                        pr.html = pr.html.replace(f'src="{img_name}"', f'src="{canonical_name}"')
                    continue
                seen_image_hashes[content_hash] = img_name
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
