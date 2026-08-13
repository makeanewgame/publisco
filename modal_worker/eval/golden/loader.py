"""Golden dataset'i (sentetik smoke kitaplar + gerçek `books/` altındaki
kitaplar) tek bir `GoldenBook` listesine yükler.

Gerçek kitaplar `manifest.json`'da tanımlanır; PDF'ler git'e girmez (bkz.
`books/.gitignore`) -- yerelde yoksa o kitap sessizce atlanır (uyarı basılır),
tüm dataset eksik kitap yüzünden başarısız olmaz.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from .synthetic import load_synthetic_books
from .types import GoldenBook

logger = logging.getLogger("eval.golden")

GOLDEN_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = GOLDEN_DIR / "manifest.json"
BOOKS_DIR = GOLDEN_DIR / "books"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_real_book(entry: dict) -> GoldenBook | None:
    book_dir = BOOKS_DIR / entry["id"]
    pdf_path = book_dir / "input.pdf"
    metadata_path = book_dir / "metadata.json"

    if not pdf_path.exists():
        logger.warning("Golden kitap atlandi (PDF yok): %s (%s)", entry["id"], pdf_path)
        return None

    expected_sha = entry.get("sha256")
    if expected_sha:
        actual_sha = _sha256(pdf_path)
        if actual_sha != expected_sha:
            logger.warning(
                "Golden kitap atlandi (sha256 uyusmuyor, manifest guncel olmayabilir): %s", entry["id"]
            )
            return None

    metadata: dict = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    reference_text = None
    reference_path = book_dir / "reference.txt"
    if reference_path.exists():
        reference_text = reference_path.read_text(encoding="utf-8")

    expected_chapters = metadata.get("expected_chapters")
    paragraph_range = metadata.get("expected_paragraph_range")

    return GoldenBook(
        id=entry["id"],
        category=entry.get("category", metadata.get("category", "unknown")),
        language=metadata.get("language", entry.get("language", "unknown")),
        is_scanned=metadata.get("is_scanned", False),
        pdf_loader=lambda p=pdf_path: p.read_bytes(),
        config=metadata.get("config", {}),
        expected_chapters=expected_chapters,
        expected_image_count=metadata.get("expected_image_count"),
        must_include_phrases=metadata.get("must_include_phrases", []),
        must_exclude_phrases=metadata.get("must_exclude_phrases", []),
        expected_paragraph_range=tuple(paragraph_range) if paragraph_range else None,
        reference_text=reference_text,
        unsupported=metadata.get("unsupported", False),
        notes=metadata.get("notes", ""),
    )


def load_real_books() -> list[GoldenBook]:
    if not MANIFEST_PATH.exists():
        return []

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    books: list[GoldenBook] = []
    for entry in manifest.get("books", []):
        book = _load_real_book(entry)
        if book is not None:
            books.append(book)
    return books


def load_golden_books(smoke_only: bool = False) -> list[GoldenBook]:
    if smoke_only:
        return load_synthetic_books()
    return load_synthetic_books() + load_real_books()
