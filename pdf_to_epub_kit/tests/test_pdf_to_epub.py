import tempfile
import unittest
import zipfile
from pathlib import Path

import pymupdf

from pdf_to_epub import (
    build_visual_page_html,
    normalize_cli_arguments,
    pdf_to_epub,
    should_use_visual_page,
    text_to_html_blocks,
)


class CliArgumentNormalizationTests(unittest.TestCase):
    def test_normalizes_quoted_paths_and_escaped_spaces(self):
        raw_args = ['"Attack On Titan - Chapter 063.pdf"', '-c', 'book_config.json']
        normalized = normalize_cli_arguments(raw_args)

        self.assertEqual(normalized[0], "Attack On Titan - Chapter 063.pdf")
        self.assertEqual(normalized[1:], ["-c", "book_config.json"])


class VisualModeDetectionTests(unittest.TestCase):
    def test_uses_visual_mode_for_sparse_text_pages(self):
        config = {"auto_visual_mode": True}
        self.assertTrue(should_use_visual_page(config, "", page_num=5))

    def test_keeps_text_mode_for_pages_with_enough_text(self):
        config = {"auto_visual_mode": True}
        long_text = (
            "Bu sayfada oldukça uzun ve düzenli bir metin parçası yer alıyor. "
            "Normal bir kitap sayfasında metin akışı korunmalı, görsel mod yerine "
            "standart paragraf düzeni kullanılmalıdır çünkü bu tür sayfalar manga "
            "veya artbook gibi görsel odaklı içerikler değildir."
        )
        self.assertFalse(should_use_visual_page(config, long_text, page_num=5))

    def test_honors_explicit_visual_mode(self):
        config = {"visual_mode": True, "auto_visual_mode": True}
        self.assertTrue(should_use_visual_page(config, "Herhangi bir metin", page_num=5))


class TextToHtmlBlocksTests(unittest.TestCase):
    def test_preserves_paragraphs_and_heading_like_blocks(self):
        text = "Başlık\n\nİlk paragraf metni.\n\nİkinci paragraf metni."

        html = text_to_html_blocks(text)

        self.assertIn("<h2>Başlık</h2>", html)
        self.assertIn("<p>İlk paragraf metni.</p>", html)
        self.assertIn("<p>İkinci paragraf metni.</p>", html)

    def test_builds_visual_page_html_with_image_and_caption(self):
        html = build_visual_page_html(12, "images/page_12.png", caption="Sayfa 12 açıklaması")

        self.assertIn('<img src="images/page_12.png"', html)
        self.assertIn("Sayfa 12 açıklaması", html)


class NoTextPageFallbackTests(unittest.TestCase):
    """Regresyon: taranmış/görsel bir sayfada ne metin ne OCR sonucu varsa,
    eskiden `visual_mode`/`auto_visual_mode` kapalıyken sayfa sessizce
    (bir uyarı `print`'iyle) tamamen atlanıyordu, içerik kayboluyordu.
    `apps/worker/app/converter.py`'de zaten düzeltilmiş olan bu davranış
    (koşulsuz görsel fallback) buraya da taşındı."""

    def test_falls_back_to_page_image_when_no_text_found(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.draw_rect(page.rect, color=(0, 0, 0), fill=(0.5, 0.5, 0.5))

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "in.pdf"
            epub_path = Path(tmp) / "out.epub"
            doc.save(str(pdf_path))
            doc.close()

            pdf_to_epub(str(pdf_path), str(epub_path), {"title": "Taranmis Kitap"})

            with zipfile.ZipFile(epub_path) as archive:
                image_entries = [name for name in archive.namelist() if name.endswith(".jpg")]
                self.assertTrue(
                    image_entries,
                    "Metni çıkarılamayan sayfa görsel olarak eklenmeli, atlanmamalı",
                )


if __name__ == "__main__":
    unittest.main()
