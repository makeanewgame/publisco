"""`doc_types/<kategori>/*.pdf` altındaki örnekleri toplu olarak golden dataset'e ekler.

`add_book.py` tek bir PDF için çalışır; burada kaynak klasördeki her kategori
alt klasörünü tarayıp içindeki her PDF için `add_book.main()`'i çağırıyoruz --
mantığı (sha256, manifest güncelleme, metadata.json iskeleti) tekrarlamadan.

Kullanım:
    .venv/bin/python -m eval.golden.bulk_add_books [kaynak_dizin]

`kaynak_dizin` verilmezse `~/Documents/doc_types` kullanılır. Klasör adı 15
kategoriden biriyle eşleşmeyen alt klasörler atlanır (uyarı basılır). Zaten
eklenmiş bir kitap (aynı book_id) yeniden çalıştırıldığında add_book.py onu
sessizce üzerine yazar (PDF/sha256 güncellenir, metadata.json'a dokunulmaz).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.golden.add_book import CATEGORIES, main as add_book_main  # noqa: E402

DEFAULT_SOURCE_DIR = Path("~/Documents/doc_types").expanduser()


def _slugify(stem: str) -> str:
    slug = stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def main() -> None:
    source_dir = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else DEFAULT_SOURCE_DIR
    if not source_dir.is_dir():
        print(f"Kaynak dizin bulunamadı: {source_dir}")
        sys.exit(1)

    added: list[str] = []
    skipped: list[str] = []

    for category_dir in sorted(p for p in source_dir.iterdir() if p.is_dir()):
        category = category_dir.name
        if category not in CATEGORIES:
            print(f"Atlandı (bilinmeyen kategori): {category_dir}")
            continue

        pdfs = sorted(p for p in category_dir.iterdir() if p.suffix.lower() == ".pdf")
        if not pdfs:
            continue

        for pdf_path in pdfs:
            book_id = f"{category}_{_slugify(pdf_path.stem)}"
            print(f"\n== {book_id} ({category}) <- {pdf_path.name} ==")
            original_argv = sys.argv
            sys.argv = ["add_book.py", str(pdf_path), book_id, category]
            try:
                add_book_main()
                added.append(book_id)
            except SystemExit as e:
                if e.code not in (0, None):
                    skipped.append(book_id)
            finally:
                sys.argv = original_argv

    print("\n" + "=" * 60)
    print(f"Eklendi/güncellendi: {len(added)} kitap")
    if skipped:
        print(f"Başarısız: {len(skipped)} -> {', '.join(skipped)}")
    print("\nSıradaki adım: her books/<id>/metadata.json içindeki TODO alanlarını doldur")
    print("(language, must_include_phrases, expected_chapters vb.) -- bkz. eval/README.md.")


if __name__ == "__main__":
    main()
