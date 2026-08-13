"""PDF -> EPUB dönüştürmeyi lokalde (Modal'sız, Blob'suz, webhook'suz) çalıştırıp
plan/map/reduce fazlarının ara çıktılarını saklar.

`converter.convert_pdf_to_epub` ile aynı sırayı izler (plan -> map -> reduce,
bkz. converter.py) ama tek fark: ara sonuçları (PlanResult, PageResult listesi)
atmak yerine `ConversionArtifact` içinde saklar, çünkü metriklerin çoğu nihai
EPUB'dan değil bu ara sonuçlardan besleniyor (ör. OCR confidence, sayfa bazlı
görsel/metin fallback oranı).

Pipeline kodunun kendisine (converter.py/main.py) hiçbir değişiklik yapmaz.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from converter import (  # noqa: E402
    ConversionError,
    PageResult,
    PlanResult,
    assemble_epub,
    plan_conversion,
    process_page_range,
)


@dataclass
class ConversionArtifact:
    book_id: str
    plan: PlanResult
    page_results: list[PageResult]
    epub_bytes: bytes
    duration_seconds: float
    error: str | None = None


@dataclass
class BookResult:
    """Bir kitap için eval çalıştırmasının nihai sonucu: skor + tüm ham metrikler."""

    book_id: str
    category: str
    score: float | None = None
    category_label: str | None = None
    metric_scores: dict[str, float] = field(default_factory=dict)
    metric_details: dict[str, Any] = field(default_factory=dict)
    gates_triggered: list[str] = field(default_factory=list)
    error: str | None = None
    duration_seconds: float = 0.0


def run_conversion(pdf_bytes: bytes, config: dict[str, Any], book_id: str, force_ocr: bool = False) -> ConversionArtifact:
    """`convert_pdf_to_epub` ile davranışça eşdeğer, ama plan/page_results'ı
    metrikler için saklar. Dönüştürme başarısız olursa `error` doldurulur,
    `epub_bytes` boş kalır — çağıran taraf bunu skor gate'ine çevirir."""
    start = time.monotonic()
    try:
        plan = plan_conversion(pdf_bytes, dict(config))
        page_results: list[PageResult] = []
        for start_page, end_page in plan.chunks:
            page_results.extend(
                process_page_range(pdf_bytes, start_page, end_page, plan.resolved_config, force_ocr=force_ocr)
            )
        epub_bytes = assemble_epub(plan, page_results)
        return ConversionArtifact(
            book_id=book_id,
            plan=plan,
            page_results=page_results,
            epub_bytes=epub_bytes,
            duration_seconds=time.monotonic() - start,
        )
    except ConversionError as exc:
        return ConversionArtifact(
            book_id=book_id,
            plan=PlanResult(total_pages=0, resolved_config=dict(config), chapters=[], chunks=[]),
            page_results=[],
            epub_bytes=b"",
            duration_seconds=time.monotonic() - start,
            error=str(exc),
        )
