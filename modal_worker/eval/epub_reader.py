"""Üretilen EPUB'ı (bytes) metriklerin tüketebileceği düz bir yapıya çözer:
paragraf listesi, başlık listesi, TOC (bölüm başlıkları) ve görsel sayımları.

`ebooklib` ile paketi açar, her bölüm XHTML'ini stdlib `html.parser` ile
(ek bağımlılık istemeden) p/h1/h2/img etiketlerine ayrıştırır. Bu ayrıştırma
yalnızca `converter.assemble_epub`'ın ürettiği sınırlı HTML alt kümesini
(bkz. `text_to_html_blocks`, `build_visual_page_html`) hedefler — genel amaçlı
bir HTML parser değildir.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from html.parser import HTMLParser

from ebooklib import epub, ITEM_DOCUMENT, ITEM_IMAGE

_HEADING_TAGS = {"h1": 1, "h2": 2}


class _ChapterHTMLParser(HTMLParser):
    """Bir bölüm XHTML'inin body'sindeki p/h1/h2/img'leri sırayla toplar."""

    def __init__(self) -> None:
        super().__init__()
        self.paragraphs: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self.ordered_blocks: list[str] = []  # p + h1/h2 metni, belge sırasıyla (full_text için)
        self.image_count = 0
        self._capture_tag: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("p",) or tag in _HEADING_TAGS:
            self._capture_tag = tag
            self._buffer = []
        elif tag == "img":
            self.image_count += 1

    def handle_data(self, data: str) -> None:
        if self._capture_tag is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._capture_tag:
            text = "".join(self._buffer).strip()
            if text:
                if tag == "p":
                    self.paragraphs.append(text)
                else:
                    self.headings.append((_HEADING_TAGS[tag], text))
                self.ordered_blocks.append(text)
            self._capture_tag = None
            self._buffer = []


@dataclass
class EpubContent:
    full_text: str
    paragraphs: list[str] = field(default_factory=list)
    headings: list[tuple[int, str]] = field(default_factory=list)
    chapter_titles: list[str] = field(default_factory=list)
    content_image_count: int = 0
    total_image_items: int = 0
    chapter_count: int = 0


def read_epub(epub_bytes: bytes) -> EpubContent:
    book = epub.read_epub(io.BytesIO(epub_bytes), options={"ignore_ncx": False})

    paragraphs: list[str] = []
    headings: list[tuple[int, str]] = []
    ordered_blocks: list[str] = []
    content_image_count = 0
    chapter_count = 0

    for item in book.get_items_of_type(ITEM_DOCUMENT):
        if item.get_id() in ("nav", "ncx"):
            continue
        chapter_count += 1
        parser = _ChapterHTMLParser()
        parser.feed(item.get_content().decode("utf-8", errors="replace"))
        paragraphs.extend(parser.paragraphs)
        headings.extend(parser.headings)
        ordered_blocks.extend(parser.ordered_blocks)
        content_image_count += parser.image_count

    total_image_items = sum(1 for _ in book.get_items_of_type(ITEM_IMAGE))

    chapter_titles = _extract_toc_titles(book)

    # `full_text`, başlıkları da içerir: bazı sayfalarda (ör. kısa OCR metni)
    # `text_to_html_blocks` içeriği <h2>'ye sınıflandırabiliyor (bkz.
    # converter.text_to_html_blocks kısa-satır heuristiği) -- metin
    # bütünlüğü metrikleri bu içeriği kaçırmamalı.
    full_text = "\n\n".join(ordered_blocks)

    return EpubContent(
        full_text=full_text,
        paragraphs=paragraphs,
        headings=headings,
        chapter_titles=chapter_titles,
        content_image_count=content_image_count,
        total_image_items=total_image_items,
        chapter_count=chapter_count,
    )


def _extract_toc_titles(book: epub.EpubBook) -> list[str]:
    """`book.toc`'tan (NCX/nav'dan ayrıştırılmış, düz bölüm listesi) başlıkları
    çıkarır. `assemble_epub` toc'u hep düz (nested olmayan) bir bölüm listesi
    olarak kurduğu için (bkz. converter.py `book.toc = tuple(chapter_items)`),
    burada da yalnızca düz `Link` girdileri bekleniyor."""
    titles: list[str] = []
    for entry in book.toc:
        if isinstance(entry, epub.Link):
            if entry.title:
                titles.append(entry.title)
        elif isinstance(entry, tuple) and entry:
            section = entry[0]
            title = getattr(section, "title", None)
            if title:
                titles.append(title)
    return titles
