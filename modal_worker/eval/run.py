"""Publisco conversion evaluation CLI.

Kullanım:
    python -m eval.run                        # tüm golden set, baseline ile karşılaştır
    python -m eval.run --smoke                 # yalnız sentetik smoke kitaplar
    python -m eval.run --fast                  # her kategoriden hızlı bir temsilci (~1.5dk, regresyon garantisi değil)
    python -m eval.run --book book-007         # tek kitap + tam diagnostic dökümü
    python -m eval.run --save-baseline         # bu koşuyu yeni baseline yap
    python -m eval.run --variant llm-v1        # sonuçları bir variant etiketiyle kaydet
    python -m eval.run --compare a.json b.json # iki kayıtlı sonucu karşılaştır

Kök monorepo'dan: `pnpm test:conversion -- <args>`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.evaluate import evaluate_book  # noqa: E402
from eval.golden.loader import load_golden_books  # noqa: E402
from eval.report import (  # noqa: E402
    build_run_summary,
    compare_to_baseline,
    load_baseline,
    print_book_diagnostics,
    print_terminal_summary,
    save_baseline,
    save_results,
)

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
BASELINES_DIR = EVAL_DIR / "baselines"


def _check_optional_tools() -> None:
    warnings = []
    if shutil.which("epubcheck") is None:
        warnings.append("epubcheck bulunamadi (brew install epubcheck) -- EPUB validity metriği ve gate devre dışı.")
    try:
        import wordfreq  # noqa: F401
    except ImportError:
        warnings.append("wordfreq kurulu değil (.venv/bin/pip install wordfreq) -- broken-words metriği devre dışı.")

    for w in warnings:
        print(f"[uyari] {w}")
    if warnings:
        print()


def _run_compare(path_a: str, path_b: str) -> None:
    summary_a = json.loads(Path(path_a).read_text(encoding="utf-8"))
    summary_b = json.loads(Path(path_b).read_text(encoding="utf-8"))
    comparison = compare_to_baseline(summary_b, summary_a)
    print_terminal_summary(summary_b, comparison)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publisco conversion evaluation")
    parser.add_argument("--smoke", action="store_true", help="Yalnız sentetik smoke kitapları çalıştır")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Her kategoriden hızlı bir temsilci + smoke kitaplar (~1.5dk) -- hızlı doğrulama için, regresyon garantisi değil",
    )
    parser.add_argument("--book", metavar="BOOK_ID", help="Yalnız tek bir kitabı çalıştır, tam diagnostic bas")
    parser.add_argument("--variant", default="local", help="Sonucu bu etiketle kaydet (ör. llm-v1)")
    parser.add_argument("--save-baseline", action="store_true", help="Bu koşuyu yeni baseline yap")
    parser.add_argument("--baseline-name", default="baseline", help="Karşılaştırılacak/kaydedilecek baseline adı")
    parser.add_argument("--no-baseline-compare", action="store_true", help="Baseline ile karşılaştırma yapma")
    parser.add_argument("--force-ocr", action="store_true", help="Gömülü metin olsa da OCR'ı zorla")
    parser.add_argument("--compare", nargs=2, metavar=("BASELINE_JSON", "CURRENT_JSON"), help="İki kayıtlı sonucu karşılaştır, çalıştırma yapma")
    args = parser.parse_args()

    if args.compare:
        _run_compare(*args.compare)
        return

    _check_optional_tools()

    books = load_golden_books(smoke_only=args.smoke, fast_only=args.fast)
    if args.book:
        books = [b for b in books if b.id == args.book]
        if not books:
            print(f"Kitap bulunamadı: {args.book}")
            sys.exit(1)

    if not books:
        print("Değerlendirilecek kitap yok. Golden dataset boş mu? (bkz. eval/golden/manifest.json)")
        sys.exit(1)

    print(f"{len(books)} kitap çalıştırılıyor...")
    results = []
    for book in books:
        print(f"  - {book.id} ({book.category})...", end=" ", flush=True)
        result = evaluate_book(book, force_ocr=args.force_ocr)
        print(f"{result.score}  [{result.category_label}]" if result.score is not None else "FAILED")
        results.append(result)

    if args.book:
        print_book_diagnostics(results[0])
        return

    summary = build_run_summary(results, variant=args.variant)
    result_path = save_results(summary, RESULTS_DIR)

    comparison = None
    if not args.no_baseline_compare:
        baseline = load_baseline(BASELINES_DIR, args.baseline_name)
        if baseline is not None:
            comparison = compare_to_baseline(summary, baseline)

    print_terminal_summary(summary, comparison)
    print(f"Sonuçlar kaydedildi: {result_path}")

    if args.save_baseline:
        baseline_path = save_baseline(summary, BASELINES_DIR, args.baseline_name)
        print(f"Baseline güncellendi: {baseline_path}")


if __name__ == "__main__":
    main()
