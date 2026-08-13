"""Golden dataset'teki tek bir kitabı ve onun referans verisini tanımlar.

Bir `GoldenBook`, iki katmanlı referans stratejisini yansıtır (bkz. eval planı):
  - Tier-0 (her zaman): kategori/dil/scanned bilgisi, referanssız metrikler için.
  - Tier-1 (çoğu kitap): `must_include_phrases`/`must_exclude_phrases`/
    `expected_chapters`/`expected_image_count`/`expected_paragraph_range` —
    tam metin yazmadan ucuz, hedefli kontroller.
  - Tier-2 (birkaç kitap): `reference_text` — bağımsız kaynaklı (ör. Project
    Gutenberg) tam referans metin; word recall/precision'ı tam güçle çalıştırır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class GoldenBook:
    id: str
    category: str
    language: str
    is_scanned: bool
    pdf_loader: Callable[[], bytes]
    config: dict[str, Any] = field(default_factory=dict)

    expected_chapters: list[str] | None = None
    expected_image_count: int | None = None
    must_include_phrases: list[str] = field(default_factory=list)
    must_exclude_phrases: list[str] = field(default_factory=list)
    expected_paragraph_range: tuple[int, int] | None = None
    reference_text: str | None = None

    unsupported: bool = False
    notes: str = ""
