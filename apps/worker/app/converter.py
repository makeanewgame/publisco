"""PDF -> EPUB dönüştürme motoru.

`pdf_to_epub_kit/pdf_to_epub.py` betiğinin (bağımsız/taşınabilir CLI kiti) aynı
dönüştürme mantığının servis içi (in-process, tamamen bellek üzerinde çalışan)
halidir. CLI betiğiyle bilinçli olarak ayrık tutulur: `pdf_to_epub_kit/pdf_to_epub.py`,
kendi README.md'sinde tarif edildiği gibi tek başına kopyalanabilir bir kit
olarak kalmalı.
"""

from __future__ import annotations

import html
import io
import logging
import re
import uuid
from typing import Any, Callable, Optional

import pymupdf as fitz  # `fitz` ismi pymupdf'te deprecated; gerçek modülü bu adla kullanıyoruz.
from ebooklib import epub
from PIL import Image

logger = logging.getLogger("worker.converter")


class ConversionError(Exception):
    """PDF açılamadığında veya dönüştürme tamamen başarısız olduğunda fırlatılır."""


# ---------------------------------------------------------------------------
# Metin temizleme / HTML üretimi
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """PDF'e özgü satır sonu / tireleme sorunlarını temizler."""
    text = re.sub(r"-\s*\n\s*", "", text)
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


def _extract_text_blocks(page) -> list[str]:
    """Sayfayı PyMuPDF'in blok bazlı çıkarımıyla okur; her blok görsel olarak ayrı bir
    paragrafa karşılık gelir. `get_text("text")`'in aksine (tüm sayfayı satır satır tek
    bir akışa düzleştirip paragraf sınırlarını kaybediyordu), blok sınırları burada
    paragraf sınırı olarak korunur."""
    try:
        raw_blocks = page.get_text("blocks", sort=True)
    except Exception:
        return []

    blocks: list[str] = []
    for block in raw_blocks:
        if len(block) < 7 or block[6] != 0:  # sadece metin blokları (1 = görsel)
            continue
        text = block[4].strip()
        if text:
            blocks.append(text)
    return blocks


def extract_page_text(page, min_chars: int = 40) -> str | None:
    """Sayfadan metin çıkarır (blok sınırları paragraf ayracı `\\n\\n` olarak korunur).
    Metin çok azsa (muhtemelen taranmış sayfa) None döner."""
    text = "\n\n".join(_extract_text_blocks(page))
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


def _ocr_with_retry(doc, page_index: int, ocr_fn: "Callable[[Image.Image], Any]", dpi: int = 300) -> Any | None:
    """`ocr_fn`'i sayfanın (alfa kanalsız, RGB) render'ı üzerinde çalıştırır.

    Tesseract bazı sayfalarda (ör. çok büyük/olağandışı render boyutu) iç
    hata verip sıfır olmayan bir çıkış koduyla çökebiliyor; bu durumda
    pytesseract stderr'i UTF-8 olarak decode etmeye çalışırken de hata
    fırlatabiliyor (`UnicodeDecodeError`), gerçek tesseract hatasını gizleyip
    yanıltıcı bir mesaj bırakıyor. Böyle bir çökmede aynı sayfayı daha düşük
    DPI ile bir kez daha denemek genelde yeterli oluyor; o da başarısız
    olursa sessizce None döner (çağıran taraf sayfayı/alanı görsel/boş
    bırakır). Hem gövde metni OCR'ı (`try_ocr_page`) hem kapak başlık/yazar
    OCR'ı (`_extract_cover_title_author_via_ocr`) bu yardımcıyı kullanır ki
    aynı dayanıklılık ikisinde de geçerli olsun."""
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


def try_ocr_page(doc, page_index: int, lang: str = "tur+eng", dpi: int = 300) -> str | None:
    """pytesseract kuruluysa OCR dener; kurulu değilse sessizce None döner."""
    try:
        import pytesseract
    except ImportError:
        return None

    return _ocr_with_retry(doc, page_index, lambda img: pytesseract.image_to_string(img, lang=lang), dpi=dpi)


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


# ---------------------------------------------------------------------------
# Otomatik tespit (bölümler / başlık / yazar)
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
        data = doc[page_index].get_text("dict")
    except Exception:
        data = {}

    lines: list[tuple[float, str]] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans).strip()
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
    """PDF'ten başlık/yazar/bölümleri otomatik tespit etmeye çalışır.

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
    finally:
        doc.close()

    warnings: list[str] = []
    if not title:
        warnings.append("title")
    if not author:
        warnings.append("author")
    if not chapters:
        warnings.append("chapters")

    return {"title": title, "author": author, "chapters": chapters, "warnings": warnings}


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


def get_target_size_settings(config: dict) -> tuple[int, int, int]:
    """Boyut hedefi varsa otomatik kalite ayarlaması için ayarlar döndürür."""
    max_mb = config.get("max_epub_size_mb")
    if not max_mb:
        return 0, 0, 0

    target_bytes = int(max_mb * 1024 * 1024)
    profile = config.get("image_profile", "balanced")
    base = IMAGE_PROFILES.get(profile, IMAGE_PROFILES["balanced"])
    return target_bytes, base["dpi"], base["quality"]


# ---------------------------------------------------------------------------
# Asıl dönüştürme
# ---------------------------------------------------------------------------

def _build_epub_book(
    doc,
    config: dict,
    force_ocr: bool = False,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> epub.EpubBook:
    total_pages = len(doc)

    start_page = config.get("start_page", 1)
    end_page = config.get("end_page", total_pages)
    skip_pages = set(config.get("skip_pages", []))
    diagram_pages = set(config.get("diagram_pages", []))
    ocr_lang = config.get("ocr_language", "tur+eng")
    visual_mode = bool(config.get("visual_mode", False))
    auto_visual_mode = bool(config.get("auto_visual_mode", False))
    image_dpi, image_quality = get_image_settings(config)

    chapters_cfg = config.get("chapters") or [
        {"start_page": start_page, "title": config.get("title", "Kitap")}
    ]
    chapters_cfg = sorted(chapters_cfg, key=lambda c: c["start_page"])

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(config.get("title", "Başlıksız Kitap"))
    book.set_language(config.get("language", "tr").split("-")[0])
    book.add_author(config.get("author", "Bilinmiyor"))

    cover_page = config.get("cover_page")
    if cover_page:
        book.set_cover(
            "cover.jpg",
            page_to_image_bytes(doc, cover_page - 1, dpi=image_dpi, quality=image_quality),
        )
        logger.info("Kapak eklendi (sayfa %s)", cover_page)

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

    # İlerleme bildirimi (on_progress) için payda: gerçek döngüyle aynı filtreyi
    # (skip_pages, sayfa aralığı sınırları) uygulayarak işlenecek toplam sayfa
    # sayısını önceden hesaplıyoruz.
    pages_to_process = 0
    for i, chap in enumerate(chapters_cfg):
        chap_start = chap["start_page"]
        chap_end = (
            chapters_cfg[i + 1]["start_page"] - 1 if i + 1 < len(chapters_cfg) else end_page
        )
        chap_end = min(chap_end, end_page)
        for page_num in range(chap_start, chap_end + 1):
            if page_num < 1 or page_num > total_pages or page_num in skip_pages:
                continue
            pages_to_process += 1

    chapter_items = []
    image_counter = 0
    processed_pages = 0

    for i, chap in enumerate(chapters_cfg):
        chap_start = chap["start_page"]
        chap_end = (
            chapters_cfg[i + 1]["start_page"] - 1 if i + 1 < len(chapters_cfg) else end_page
        )
        chap_end = min(chap_end, end_page)

        html_parts = [f"<h1>{html.escape(chap['title'])}</h1>"]

        for page_num in range(chap_start, chap_end + 1):
            if page_num < 1 or page_num > total_pages or page_num in skip_pages:
                continue

            page_index = page_num - 1
            processed_pages += 1
            if on_progress:
                on_progress(processed_pages, pages_to_process)

            if page_num in diagram_pages:
                image_counter += 1
                img_name = f"images/diagram_{image_counter}.jpg"
                img_item = epub.EpubItem(
                    uid=f"img_{image_counter}",
                    file_name=img_name,
                    media_type="image/jpeg",
                    content=page_to_image_bytes(doc, page_index, dpi=image_dpi, quality=image_quality),
                )
                book.add_item(img_item)
                html_parts.append(f'<img src="{img_name}" alt="Şema/tablo - sayfa {page_num}" />')

            text = extract_page_text(doc[page_index])
            if text is None:
                text = try_ocr_page(doc, page_index, ocr_lang)
                if not text or not text.strip():
                    # Ne gömülü metin ne de OCR sonucu var (taranmış sayfa, OCR
                    # kurulu değil vb.) — sayfayı atlarsak içerik tamamen kaybolur,
                    # bu yüzden visual_mode ayarından bağımsız olarak görsel ekliyoruz.
                    image_counter += 1
                    img_name = f"images/page_{image_counter}.jpg"
                    img_item = epub.EpubItem(
                        uid=f"img_{image_counter}",
                        file_name=img_name,
                        media_type="image/jpeg",
                        content=page_to_image_bytes(
                            doc, page_index, dpi=image_dpi, quality=image_quality
                        ),
                    )
                    book.add_item(img_item)
                    caption = config.get("page_captions", {}).get(str(page_num))
                    html_parts.append(build_visual_page_html(page_num, img_name, caption=caption))
                    logger.info(
                        "Sayfa %s için metin bulunamadı (taranmış olabilir), görsel olarak eklendi.",
                        page_num,
                    )
                    continue
            elif force_ocr:
                ocr_text = try_ocr_page(doc, page_index, ocr_lang)
                if ocr_text:
                    text = ocr_text

            use_visual = visual_mode or (auto_visual_mode and should_use_visual_page(config, text, page_num))
            if use_visual:
                image_counter += 1
                img_name = f"images/page_{image_counter}.jpg"
                img_item = epub.EpubItem(
                    uid=f"img_{image_counter}",
                    file_name=img_name,
                    media_type="image/jpeg",
                    content=page_to_image_bytes(doc, page_index, dpi=image_dpi, quality=image_quality),
                )
                book.add_item(img_item)
                caption = config.get("page_captions", {}).get(str(page_num))
                html_parts.append(build_visual_page_html(page_num, img_name, caption=caption))
                continue

            cleaned = clean_text(text)
            block_html = text_to_html_blocks(cleaned)
            if block_html:
                html_parts.append(block_html)

        chap_file = f"chap_{i + 1:02d}.xhtml"
        epub_chap = epub.EpubHtml(title=chap["title"], file_name=chap_file, lang=book.language)
        epub_chap.content = "\n".join(html_parts)
        epub_chap.add_item(css)
        book.add_item(epub_chap)
        chapter_items.append(epub_chap)
        logger.info("Bölüm eklendi: %s (sayfa %s-%s)", chap["title"], chap_start, chap_end)

    book.toc = tuple(chapter_items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapter_items

    return book


def _epub_book_to_bytes(book: epub.EpubBook) -> bytes:
    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    return buffer.getvalue()


def convert_pdf_to_epub(
    pdf_bytes: bytes,
    config: dict[str, Any],
    force_ocr: bool = False,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> bytes:
    """Bir PDF'i (bayt) EPUB'a (bayt) dönüştürür; tamamen bellek üzerinde çalışır, disk kullanmaz.

    `config` alanları `book_config.json` ile aynı şemayı izler (bkz. book_config.example.json).
    `max_epub_size_mb` verilirse, hedefe ulaşana kadar görsel kalitesi kademeli düşürülerek
    yeniden denenir; hiçbir deneme hedefi tutturamazsa en son (en düşük kaliteli) sonuç döner.
    `on_progress(islenen_sayfa, toplam_sayfa)` verilirse her sayfa işlendiğinde çağrılır
    (boyut hedefi için birden çok deneme yapılırsa her denemede sıfırlanır).
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ConversionError(f"PDF açılamadı: {exc}") from exc

    try:
        config = resolve_auto_language(doc, config)
        target_bytes, base_dpi, base_quality = get_target_size_settings(config)
        if not target_bytes:
            book = _build_epub_book(doc, config, force_ocr=force_ocr, on_progress=on_progress)
            return _epub_book_to_bytes(book)

        profiles = [
            (base_dpi, base_quality),
            (max(140, base_dpi - 20), max(70, base_quality - 8)),
            (max(120, base_dpi - 40), max(60, base_quality - 16)),
            (max(100, base_dpi - 60), max(50, base_quality - 24)),
        ]

        best_attempt: bytes | None = None
        for dpi, quality in profiles:
            attempt_config = dict(config, image_dpi=dpi, image_quality=quality, image_profile="custom")
            try:
                book = _build_epub_book(doc, attempt_config, force_ocr=force_ocr, on_progress=on_progress)
                data = _epub_book_to_bytes(book)
            except Exception as exc:
                logger.warning("Profil (dpi=%s, quality=%s) denemesi başarısız: %s", dpi, quality, exc)
                continue

            best_attempt = data
            if len(data) <= target_bytes:
                logger.info("Boyut hedefi sağlandı: %.2f MB", len(data) / (1024 * 1024))
                return data

        if best_attempt is None:
            raise ConversionError("EPUB üretilemedi (tüm görsel kalite denemeleri başarısız oldu).")

        logger.warning(
            "Boyut hedefi sağlanamadı, en düşük denenen kaliteyle döndürülüyor (%.2f MB).",
            len(best_attempt) / (1024 * 1024),
        )
        return best_attempt
    finally:
        doc.close()
