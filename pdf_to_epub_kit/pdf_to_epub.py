#!/usr/bin/env python3
"""
PDF'den Kindle uyumlu (reflowable) EPUB'a dönüştürme betiği.

Kurulum:
    pip install pymupdf EbookLib

Kullanım:
    python3 pdf_to_epub.py kitap.pdf -c book_config.json -o kitap.epub

Opsiyonel OCR (taranmış/görüntü PDF'ler için):
    pip install pytesseract pillow
    (ve sisteminizde Tesseract OCR kurulu + Türkçe dil paketi olmalı)
"""

import argparse
import html
import io
import json
import re
import shlex
import sys
import uuid
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from ebooklib import epub
except ImportError:
    epub = None


# ---------------------------------------------------------------------------
# Metin temizleme
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """PDF'e özgü satır sonu / tireleme sorunlarını temizler.

    - Satır sonunda tire ile bölünmüş kelimeleri birleştirir.
    - Tekli satır atlamalarını boşlukla değiştirir.
    - Gerçek paragraf aralıklarını korur.
    """
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


def build_visual_page_html(page_num: int, image_path: str, caption=None) -> str:
    """Görsel odaklı bir sayfa için HTML oluşturur."""
    parts = [f'<div class="visual-page">', f'<h2>Sayfa {page_num}</h2>']
    parts.append(f'<img src="{image_path}" alt="Sayfa {page_num}" />')
    if caption:
        parts.append(f'<p class="caption">{html.escape(caption)}</p>')
    parts.append('</div>')
    return "\n".join(parts)


def extract_page_text(page, min_chars: int = 40):
    """Sayfadan metin çıkarır. Metin çok azsa (muhtemelen taranmış sayfa) None döner."""
    text = page.get_text("text")
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


def try_ocr_page(doc, page_index: int, lang: str = "tur+eng"):
    """pytesseract kuruluysa OCR dener; kurulu değilse sessizce None döner."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None
    page = doc[page_index]
    pix = page.get_pixmap(dpi=300)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    try:
        return pytesseract.image_to_string(img, lang=lang)
    except Exception as e:  # tesseract binary kurulu değilse vs.
        print(f"  ! OCR hatası (sayfa {page_index + 1}): {e}")
        return None


def page_to_image_bytes(doc, page_index: int, dpi: int = 200, quality: int = 90) -> bytes:
    if Image is None:
        raise ImportError("Pillow eksik. Kurulum: pip install pillow")

    pix = doc[page_index].get_pixmap(dpi=dpi)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Asıl dönüştürme
# ---------------------------------------------------------------------------

def get_image_settings(config: dict) -> tuple[int, int]:
    """Parametrik görsel ayarları döndürür."""
    profile = config.get("image_profile", "balanced")
    profiles = {
        "high": {"dpi": 240, "quality": 92},
        "balanced": {"dpi": 220, "quality": 85},
        "kindle": {"dpi": 200, "quality": 78},
        "small": {"dpi": 180, "quality": 70},
    }

    if profile in profiles:
        return profiles[profile]["dpi"], profiles[profile]["quality"]

    if isinstance(config.get("image_dpi"), int):
        dpi = config["image_dpi"]
    else:
        dpi = 220

    if isinstance(config.get("image_quality"), int):
        quality = config["image_quality"]
    else:
        quality = 85

    return dpi, quality


def get_target_size_settings(config: dict) -> tuple[int, int, int]:
    """Boyut hedefi varsa otomatik kalite ayarlaması için ayarlar döndürür."""
    max_bytes = config.get("max_epub_size_mb")
    if not max_bytes:
        return 0, 0, 0

    target_bytes = int(max_bytes) * 1024 * 1024
    profile = config.get("image_profile", "balanced")
    profiles = {
        "high": {"dpi": 240, "quality": 92},
        "balanced": {"dpi": 220, "quality": 85},
        "kindle": {"dpi": 200, "quality": 78},
        "small": {"dpi": 180, "quality": 70},
    }

    base = profiles.get(profile, profiles["balanced"])
    return target_bytes, base["dpi"], base["quality"]


def build_epub_with_image_settings(pdf_path: str, epub_path: str, config: dict, force_ocr: bool = False):
    """Hedef boyuta ulaşana kadar kademeli olarak görsel kalitesini düşürerek EPUB oluşturur."""
    target_bytes, base_dpi, base_quality = get_target_size_settings(config)
    if not target_bytes:
        return pdf_to_epub(pdf_path, epub_path, config, force_ocr=force_ocr)

    profiles = [
        (base_dpi, base_quality),
        (max(140, base_dpi - 20), max(70, base_quality - 8)),
        (max(120, base_dpi - 40), max(60, base_quality - 16)),
        (max(100, base_dpi - 60), max(50, base_quality - 24)),
    ]

    for dpi, quality in profiles:
        temp_config = dict(config)
        temp_config["image_dpi"] = dpi
        temp_config["image_quality"] = quality
        temp_config["image_profile"] = "custom"
        temp_epub_path = str(Path(epub_path).with_suffix(".tmp.epub"))
        try:
            pdf_to_epub(pdf_path, temp_epub_path, temp_config, force_ocr=force_ocr)
        except Exception:
            continue

        if Path(temp_epub_path).exists() and Path(temp_epub_path).stat().st_size <= target_bytes:
            if Path(epub_path).exists():
                Path(epub_path).unlink()
            Path(temp_epub_path).rename(epub_path)
            print(f"  Boyut hedefi sağlandı: {Path(epub_path).stat().st_size / (1024 * 1024):.2f} MB")
            return

        if Path(temp_epub_path).exists():
            Path(temp_epub_path).unlink()

    # Son çare: en düşük kaliteyle dene
    low_config = dict(config)
    low_config["image_dpi"] = 100
    low_config["image_quality"] = 50
    low_config["image_profile"] = "custom"
    low_epub_path = str(Path(epub_path).with_suffix(".tmp.epub"))
    pdf_to_epub(pdf_path, low_epub_path, low_config, force_ocr=force_ocr)
    if Path(low_epub_path).exists() and Path(low_epub_path).stat().st_size <= target_bytes:
        if Path(epub_path).exists():
            Path(epub_path).unlink()
        Path(low_epub_path).rename(epub_path)
        print(f"  Boyut hedefi sağlandı: {Path(epub_path).stat().st_size / (1024 * 1024):.2f} MB")
    else:
        if Path(epub_path).exists():
            Path(epub_path).unlink()
        Path(low_epub_path).rename(epub_path)
        print(f"  Boyut hedefi sağlanamadı, en düşük kaliteyle kaydedildi: {Path(epub_path).stat().st_size / (1024 * 1024):.2f} MB")


def pdf_to_epub(pdf_path: str, epub_path: str, config: dict, force_ocr: bool = False) -> None:
    if fitz is None:
        raise ImportError("PyMuPDF eksik. Kurulum: pip install pymupdf")
    if epub is None:
        raise ImportError("EbookLib eksik. Kurulum: pip install EbookLib")

    doc = fitz.open(pdf_path)
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
        book.set_cover("cover.jpg", page_to_image_bytes(doc, cover_page - 1, dpi=image_dpi, quality=image_quality))
        print(f"  Kapak eklendi (sayfa {cover_page})")

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
    image_counter = 0

    for i, chap in enumerate(chapters_cfg):
        chap_start = chap["start_page"]
        chap_end = (
            chapters_cfg[i + 1]["start_page"] - 1 if i + 1 < len(chapters_cfg) else end_page
        )
        chap_end = min(chap_end, end_page)

        html_parts = [f"<h1>{chap['title']}</h1>"]

        for page_num in range(chap_start, chap_end + 1):
            if page_num < 1 or page_num > total_pages or page_num in skip_pages:
                continue

            page_index = page_num - 1

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
                        content=page_to_image_bytes(doc, page_index, dpi=image_dpi, quality=image_quality),
                    )
                    book.add_item(img_item)
                    caption = config.get("page_captions", {}).get(str(page_num))
                    html_parts.append(build_visual_page_html(page_num, img_name, caption=caption))
                    print(
                        f"  Uyarı: sayfa {page_num} için metin bulunamadı (taranmış olabilir), "
                        f"görsel olarak eklendi."
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
        print(f"  Bölüm eklendi: {chap['title']} (sayfa {chap_start}-{chap_end})")

    book.toc = tuple(chapter_items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapter_items

    epub.write_epub(epub_path, book)
    print(f"\nTamamlandı: {epub_path}")


def normalize_cli_arguments(raw_args=None) -> list[str]:
    """Kullanıcı arayüzünden veya sürükle-bırak ile gelen argümanları daha esnek işler.

    - Çift tırnaklı/tek tırnaklı yolları temizler.
    - Boşluk içeren yolları tek argüman olarak korur.
    - Tek bir metin olarak gelen komut satırını shell benzeri biçimde parçalar.
    """
    if raw_args is None:
        raw_args = sys.argv[1:]

    if not raw_args:
        return []

    if len(raw_args) == 1:
        single_arg = raw_args[0]
        if any(token in single_arg for token in [" -c ", " --config ", " -o ", " --output ", " --force-ocr"]):
            try:
                return shlex.split(single_arg, posix=True)
            except ValueError:
                pass
        return [single_arg.strip().strip('"').strip("'")]

    normalized = []
    for arg in raw_args:
        if not isinstance(arg, str):
            normalized.append(arg)
            continue

        cleaned = arg.strip().strip('"').strip("'")
        cleaned = cleaned.replace("\\ ", " ")
        normalized.append(cleaned)

    return normalized


def load_config(config_path, pdf_path) -> dict:
    if config_path:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    print("! book_config.json verilmedi, minimal varsayılan ayarlarla devam ediliyor.")
    return {"title": Path(pdf_path).stem, "author": "Bilinmiyor", "language": "tr"}


def main():
    parser = argparse.ArgumentParser(description="PDF'yi Kindle uyumlu EPUB'a dönüştürür.")
    parser.add_argument("pdf", help="Kaynak PDF dosyası")
    parser.add_argument("-c", "--config", help="book_config.json yolu", default=None)
    parser.add_argument("-o", "--output", help="Çıktı EPUB dosya adı", default=None)
    parser.add_argument("--force-ocr", action="store_true", help="Metin olsa bile OCR uygula")
    args = parser.parse_args(normalize_cli_arguments())

    if not Path(args.pdf).exists():
        sys.exit(f"Hata: '{args.pdf}' bulunamadı.")

    config = load_config(args.config, args.pdf)
    output = args.output or (Path(args.pdf).stem + ".epub")

    build_epub_with_image_settings(args.pdf, output, config, force_ocr=args.force_ocr)


if __name__ == "__main__":
    main()
