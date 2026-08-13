"""Golden dataset'e gerçek bir kitap eklemek için yardımcı CLI.

Bir PDF'i `books/<id>/input.pdf`'e kopyalar, `sha256`'sını hesaplayıp
`manifest.json`'a bir girdi ekler ve doldurulacak alanları işaretleyen bir
`metadata.json` iskeleti oluşturur -- gerçek referans değerleri (dil,
expected_chapters, must_include_phrases vb.) elle doldurulmalı.

Kullanım:
    python -m eval.golden.add_book <pdf_path> <book_id> <category>

Örnek:
    python -m eval.golden.add_book ~/Downloads/pride-and-prejudice.pdf \\
        book-001-pride-and-prejudice normal-text-novel
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.golden.loader import BOOKS_DIR, MANIFEST_PATH  # noqa: E402

CATEGORIES = [
    "normal-text-novel",
    "scanned-novel",
    "poor-quality-scan",
    "bad-ocr-layer",
    "two-column-academic",
    "book-with-images",
    "book-with-tables",
    "book-with-footnotes",
    "technical-with-code",
    "turkish",
    "english",
    "multilingual",
    "complex-headings",
    "lists-and-quotes",
    "unusual-fonts",
    "mathematical",  # unsupported=true ile işaretlenmeli
]

METADATA_TEMPLATE = """{{
  "category": "{category}",
  "language": "TODO: tr/en/... (langdetect ISO 639-1 kodu)",
  "is_scanned": false,
  "config": {{
    "title": "TODO",
    "author": "TODO"
  }},
  "expected_chapters": null,
  "expected_image_count": null,
  "must_include_phrases": [],
  "must_exclude_phrases": [],
  "expected_paragraph_range": null,
  "unsupported": false,
  "notes": "TODO: kaynak, sayfa aralığı, bilinen özellikler"
}}
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden dataset'e kitap ekle")
    parser.add_argument("pdf_path", help="Eklenecek PDF'in yolu")
    parser.add_argument("book_id", help="Kitap id'si (ör. book-001-pride-and-prejudice)")
    parser.add_argument("category", choices=CATEGORIES, help="15 kategoriden biri")
    args = parser.parse_args()

    source_pdf = Path(args.pdf_path).expanduser().resolve()
    if not source_pdf.exists():
        print(f"PDF bulunamadı: {source_pdf}")
        sys.exit(1)

    book_dir = BOOKS_DIR / args.book_id
    book_dir.mkdir(parents=True, exist_ok=True)
    dest_pdf = book_dir / "input.pdf"
    shutil.copy2(source_pdf, dest_pdf)
    sha = _sha256(dest_pdf)

    metadata_path = book_dir / "metadata.json"
    if not metadata_path.exists():
        metadata_path.write_text(METADATA_TEMPLATE.format(category=args.category), encoding="utf-8")
        print(f"Oluşturuldu: {metadata_path} -- alanları doldurmayı unutma.")
    else:
        print(f"metadata.json zaten var, dokunulmadı: {metadata_path}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["books"] = [b for b in manifest["books"] if b["id"] != args.book_id]
    manifest["books"].append({"id": args.book_id, "category": args.category, "sha256": sha})
    manifest["books"].sort(key=lambda b: b["id"])
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"manifest.json güncellendi: {args.book_id} ({args.category})")
    print(f"Sıradaki adım: {metadata_path} içindeki TODO alanlarını doldur.")


if __name__ == "__main__":
    main()
