#!/usr/bin/env python3
"""Taranmış veya metin tabanlı PDF'yi reflowable Kindle EPUB'a dönüştürür."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    print("Çalışıyor:", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def pdf_page_count(pdf: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(pdf)], check=True, capture_output=True, text=True
    ).stdout
    match = re.search(r"^Pages:\s+(\d+)", result, re.MULTILINE)
    if not match:
        raise RuntimeError("PDF sayfa sayısı okunamadı.")
    return int(match.group(1))


def extract_text(pdf: Path, txt: Path) -> None:
    run(["pdftotext", "-layout", str(pdf), str(txt)])


def needs_ocr(txt: Path, page_count: int) -> bool:
    text = txt.read_text(encoding="utf-8", errors="ignore")
    letters = sum(ch.isalpha() for ch in text)
    return letters < page_count * 80


def ocr_pdf(source: Path, target: Path, sidecar: Path, language: str) -> None:
    run([
        "ocrmypdf", "--language", language, "--rotate-pages", "--deskew",
        "--optimize", "1", "--output-type", "pdf", "--jobs", "4",
        "--sidecar", str(sidecar), str(source), str(target)
    ])


def make_cover(pdf: Path, output_stem: Path) -> Path:
    run([
        "pdftoppm", "-f", "1", "-singlefile", "-jpeg", "-r", "150",
        "-jpegopt", "quality=90", str(pdf), str(output_stem)
    ])
    return output_stem.with_suffix(".jpg")


def clean_page(raw: str, header_patterns: list[str]) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
    cleaned: list[str] = []
    for line in lines:
        if re.fullmatch(r"\d{1,4}", line):
            continue
        if any(re.fullmatch(pattern, line, re.IGNORECASE) for pattern in header_patterns):
            continue
        cleaned.append(line)

    blocks: list[list[str]] = []
    current: list[str] = []
    for line in cleaned:
        if not line:
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)

    paragraphs: list[str] = []
    for block in blocks:
        paragraph = ""
        for line in block:
            # Satır sonunda bölünen kelimeleri birleştirir.
            if paragraph.endswith("-") and line and line[0].islower():
                paragraph = paragraph[:-1] + line
            else:
                paragraph += (" " if paragraph else "") + line
        paragraph = re.sub(r"\s+([,.;:!?])", r"\1", paragraph)
        if paragraph:
            paragraphs.append(paragraph)
    return paragraphs


def detect_chapter_pages(pages: list[str]) -> list[int]:
    """İlk satırlardaki 'Bölüm 12' veya tek başına 12 kalıplarını arar."""
    starts: list[int] = []
    for page_no, page in enumerate(pages, 1):
        first_lines = [x.strip() for x in page.splitlines() if x.strip()][:5]
        head = "\n".join(first_lines)
        if re.search(r"(?im)^\s*bölüm\s+\d{1,3}\s*$", head):
            starts.append(page_no)
        elif first_lines and re.fullmatch(r"\d{1,3}", first_lines[0]):
            starts.append(page_no)
    # Yanlış pozitifleri azalt: bölüm başlangıçları artan ve benzersiz olmalı.
    return sorted(set(starts))


def xhtml(title: str, body: str, css_path: str = "../styles/book.css") -> str:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="tr" lang="tr">
<head><meta charset="utf-8"/><title>{html.escape(title)}</title>
<link rel="stylesheet" href="{css_path}" type="text/css"/></head>
<body>{body}</body></html>'''


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_epub(
    pages: list[str], cover: Path, output: Path, title: str, author: str,
    chapter_pages: list[int], header_patterns: list[str]
) -> None:
    with tempfile.TemporaryDirectory(prefix="epub-build-") as temp_name:
        root = Path(temp_name)
        (root / "META-INF").mkdir()
        (root / "OEBPS/text").mkdir(parents=True)
        (root / "OEBPS/styles").mkdir()
        (root / "OEBPS/images").mkdir()
        write(root / "mimetype", "application/epub+zip")
        write(root / "META-INF/container.xml", '''<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''')
        shutil.copy2(cover, root / "OEBPS/images/cover.jpg")
        write(root / "OEBPS/styles/book.css", '''body { margin: 5%; line-height: 1.45; text-align: justify; hyphens: auto; }
p { margin: 0 0 .55em; text-indent: 1.15em; }
h1 { text-align: center; margin: 2.5em 0 1.5em; page-break-before: always; }
.cover { margin: 0; padding: 0; text-align: center; }
.cover img { max-width: 100%; max-height: 100%; }
nav ol { list-style-type: none; padding-left: 0; } nav li { margin: .55em 0; }''')
        write(root / "OEBPS/text/cover.xhtml", xhtml(
            "Kapak", '<div class="cover"><img src="../images/cover.jpg" alt="Kapak"/></div>'
        ))

        if not chapter_pages:
            chapter_pages = [1]
        has_front_matter = chapter_pages[0] > 1
        if has_front_matter:
            chapter_pages.insert(0, 1)
        section_items: list[tuple[str, str]] = []
        for index, start in enumerate(chapter_pages):
            end = chapter_pages[index + 1] - 1 if index + 1 < len(chapter_pages) else len(pages)
            name = f"chapter-{index + 1:03}.xhtml"
            if has_front_matter and index == 0:
                section_title = "Ön Sayfalar"
            else:
                chapter_number = index if has_front_matter else index + 1
                section_title = f"Bölüm {chapter_number}"
            paragraphs: list[str] = []
            for page_no in range(start, end + 1):
                paragraphs.extend(clean_page(pages[page_no - 1], header_patterns))
            body = f"<section><h1>{html.escape(section_title)}</h1>" + "".join(
                f"<p>{html.escape(p)}</p>" for p in paragraphs
            ) + "</section>"
            write(root / "OEBPS/text" / name, xhtml(section_title, body))
            section_items.append((section_title, name))

        links = "".join(
            f'<li><a href="text/{name}">{html.escape(label)}</a></li>'
            for label, name in section_items
        )
        write(root / "OEBPS/nav.xhtml", xhtml(
            "İçindekiler",
            f'<nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><h1>İçindekiler</h1><ol>{links}</ol></nav>',
            "styles/book.css"
        ))

        manifest = [
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="css" href="styles/book.css" media-type="text/css"/>',
            '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>',
            '<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>'
        ]
        spine = ['<itemref idref="cover"/>']
        for index, (_, name) in enumerate(section_items):
            manifest.append(f'<item id="c{index}" href="text/{name}" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="c{index}"/>')
        book_id = uuid.uuid4()
        package = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="tr">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">urn:uuid:{book_id}</dc:identifier><dc:title>{html.escape(title)}</dc:title><dc:creator>{html.escape(author)}</dc:creator><dc:language>tr</dc:language><meta property="dcterms:modified">2026-01-01T00:00:00Z</meta></metadata>
<manifest>{''.join(manifest)}</manifest><spine>{''.join(spine)}</spine></package>'''
        write(root / "OEBPS/package.opf", package)

        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w") as archive:
            archive.write(root / "mimetype", "mimetype", compress_type=ZIP_STORED)
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.name != "mimetype":
                    archive.write(path, path.relative_to(root).as_posix(), compress_type=ZIP_DEFLATED)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PDF'den Kindle uyumlu EPUB üretir.")
    parser.add_argument("pdf", type=Path, help="Kaynak PDF")
    parser.add_argument("--output", "-o", type=Path, help="Çıktı EPUB yolu")
    parser.add_argument("--title", default=None, help="Kitap adı")
    parser.add_argument("--author", default="Bilinmiyor", help="Yazar")
    parser.add_argument("--language", default="tur", help="Tesseract dili (varsayılan: tur)")
    parser.add_argument("--chapter-pages", help="Kesin bölüm başlangıç sayfaları: 6,10,14")
    parser.add_argument("--header", action="append", default=[], help="Silinecek üstbilgi regex'i; birden fazla kullanılabilir")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.pdf.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    missing = [name for name in ("pdfinfo", "pdftotext", "pdftoppm", "ocrmypdf", "tesseract") if not command_exists(name)]
    if missing:
        raise RuntimeError("Eksik programlar: " + ", ".join(missing))

    output = (args.output or source.with_suffix(".epub")).expanduser().resolve()
    title = args.title or source.stem.replace("-", " ").replace("_", " ").title()
    with tempfile.TemporaryDirectory(prefix="pdf-epub-") as temp_name:
        temp = Path(temp_name)
        extracted = temp / "text.txt"
        page_count = pdf_page_count(source)
        extract_text(source, extracted)
        if needs_ocr(extracted, page_count):
            print("PDF taranmış görünüyor; Türkçe OCR uygulanıyor...")
            searchable = temp / "ocr.pdf"
            ocr_pdf(source, searchable, extracted, args.language)
        else:
            print("PDF'de seçilebilir metin bulundu; OCR gerekmiyor.")
        pages = extracted.read_text(encoding="utf-8", errors="replace").split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        cover = make_cover(source, temp / "cover")
        if args.chapter_pages:
            starts = sorted({int(x) for x in args.chapter_pages.split(",") if x.strip()})
        else:
            starts = detect_chapter_pages(pages)
            print("Otomatik bulunan bölüm başlangıçları:", starts or "bulunamadı")
        build_epub(pages, cover, output, title, args.author, starts, args.header)
    print(f"\nHazır: {output}")
    print("Kindle'a Send to Kindle ile gönderebilirsin.")


if __name__ == "__main__":
    main()
