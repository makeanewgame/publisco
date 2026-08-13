"""Referanssız metrik: OCR güven skorları.

Pipeline'ın kendisi (`converter.try_ocr_page`) `image_to_string` kullanıyor --
confidence bilgisi taşımıyor ve bunu değiştirmek eval kapsamının dışında
(pipeline'a dokunmama kuralı, bkz. plan). Bunun yerine bu metrik, plan
fazının zaten hesapladığı sayfa aralığını/kenar payı kalibrasyonunu
kullanarak METİN KATMANI OLMAYAN sayfaları kendisi tespit edip
`pytesseract.image_to_data` ile (koordinat + confidence döner) bağımsızca
yeniden OCR'lar. Pipeline'ın ürettiği nihai metni DEĞİŞTİRMEZ, yalnızca
ek bir tanı sinyali üretir -- bu yüzden ~2x OCR maliyeti kabul edilebilir
(bkz. eval planı, madde 'OCR confidence eval tarafında ölçülür')."""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from converter import (  # noqa: E402
    DEFAULT_OCR_LANGUAGE,
    HEADER_FOOTER_DEFAULT_MARGIN_RATIO,
    build_header_blacklist,
    extract_page_text,
)

LOW_CONFIDENCE_THRESHOLD = 60.0
OCR_DPI = 300


@dataclass
class OcrQualityResult:
    available: bool = True
    scanned_page_count: int = 0
    avg_confidence: float | None = None
    low_confidence_page_pct: float | None = None
    low_confidence_block_pct: float | None = None


def _page_ocr_confidences(doc, page_index: int, lang: str, dpi: int = OCR_DPI) -> list[float]:
    import pytesseract
    from PIL import Image
    from pytesseract import Output

    pix = doc[page_index].get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    data = pytesseract.image_to_data(img, lang=lang, output_type=Output.DICT)

    confidences: list[float] = []
    for i, text in enumerate(data.get("text", [])):
        if not text.strip():
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf >= 0:  # pytesseract, metin olmayan elemanlar için -1 döner
            confidences.append(conf)
    return confidences


def evaluate_ocr_quality(pdf_bytes: bytes, resolved_config: dict[str, Any], start_page: int, end_page: int) -> OcrQualityResult:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return OcrQualityResult(available=False)

    import pymupdf as fitz

    top_ratio = resolved_config.get("header_margin_ratio", HEADER_FOOTER_DEFAULT_MARGIN_RATIO)
    bottom_ratio = resolved_config.get("footer_margin_ratio", HEADER_FOOTER_DEFAULT_MARGIN_RATIO)
    ocr_lang = resolved_config.get("ocr_language", DEFAULT_OCR_LANGUAGE)
    header_blacklist = build_header_blacklist(resolved_config)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        total_pages = len(doc)
        page_avg_confidences: list[float] = []
        all_block_confidences: list[float] = []

        for page_num in range(start_page, end_page + 1):
            page_index = page_num - 1
            if not (0 <= page_index < total_pages):
                continue
            text = extract_page_text(
                doc[page_index],
                blacklist=header_blacklist,
                top_margin_ratio=top_ratio,
                bottom_margin_ratio=bottom_ratio,
            )
            if text is not None:
                continue  # gömülü metin katmanı var, taranmış sayfa değil

            try:
                confidences = _page_ocr_confidences(doc, page_index, ocr_lang)
            except Exception:
                continue
            if not confidences:
                continue

            page_avg_confidences.append(sum(confidences) / len(confidences))
            all_block_confidences.extend(confidences)

        if not page_avg_confidences:
            return OcrQualityResult(available=True, scanned_page_count=0)

        avg_confidence = sum(page_avg_confidences) / len(page_avg_confidences)
        low_conf_pages = sum(1 for c in page_avg_confidences if c < LOW_CONFIDENCE_THRESHOLD)
        low_conf_blocks = sum(1 for c in all_block_confidences if c < LOW_CONFIDENCE_THRESHOLD)

        return OcrQualityResult(
            available=True,
            scanned_page_count=len(page_avg_confidences),
            avg_confidence=avg_confidence,
            low_confidence_page_pct=low_conf_pages / len(page_avg_confidences),
            low_confidence_block_pct=low_conf_blocks / len(all_block_confidences) if all_block_confidences else 0.0,
        )
    finally:
        doc.close()
