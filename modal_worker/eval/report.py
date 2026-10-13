"""Bir eval koşusunun sonuçlarını JSON'a kaydeder, terminalde okunabilir bir
özet basar ve önceki baseline ile karşılaştırır."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.runner import BookResult

METRIC_LABELS = {
    "text_completeness": "Text completeness",
    "structure": "Structure",
    "cleanliness": "Text cleanliness",
    "ocr_quality": "OCR quality",
    "images": "Images",
    "reading_order": "Reading order",
}


def build_run_summary(book_results: list[BookResult], variant: str) -> dict[str, Any]:
    books_payload = [asdict(r) for r in book_results]

    # `eval/README.md`: unsupported=true kitaplar (ör. mathematical) skora/gate'e
    # dahil edilmez, yalnızca raporlanır (per-kitap satırı hâlâ basılıyor,
    # `books_payload`'da hâlâ var) -- bkz. NOTES.md/ROADMAP.md.
    supported_results = [r for r in book_results if not r.unsupported]

    scored = [r for r in supported_results if r.score is not None]
    overall_score = round(sum(r.score for r in scored) / len(scored), 1) if scored else 0.0

    metric_averages: dict[str, float | None] = {}
    for metric_name in METRIC_LABELS:
        values = [r.metric_scores.get(metric_name) for r in supported_results if r.metric_scores.get(metric_name) is not None]
        metric_averages[metric_name] = round(sum(values) / len(values), 3) if values else None

    failed_books = [
        {"book_id": r.book_id, "category": r.category, "score": r.score, "gates": r.gates_triggered, "error": r.error}
        for r in supported_results
        if r.category_label in ("Failed", "Poor") or r.error
    ]

    tool_warnings = []
    if any(r.metric_details.get("epub_validity", {}).get("execution_failed") for r in book_results):
        tool_warnings.append(
            "epubcheck çalıştırılamadı (yerel kurulum sorunu olabilir) -- EPUB validity metriği/gate bu koşuda devre dışı kaldı."
        )

    tier_scores: dict[str, dict[str, Any]] = {}
    for r in scored:
        tier_scores.setdefault(r.tier, {"book_count": 0, "_sum": 0.0})
        tier_scores[r.tier]["book_count"] += 1
        tier_scores[r.tier]["_sum"] += r.score
    for entry in tier_scores.values():
        entry["score"] = round(entry.pop("_sum") / entry["book_count"], 1)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "variant": variant,
        "book_count": len(book_results),
        "overall_score": overall_score,
        "metric_averages": metric_averages,
        "tier_scores": tier_scores,
        "books": books_payload,
        "failed_books": failed_books,
        "tool_warnings": tool_warnings,
    }


def save_results(summary: dict[str, Any], results_dir: Path) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = results_dir / f"{ts}-{summary['variant']}.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_baseline(baselines_dir: Path, name: str = "baseline") -> dict[str, Any] | None:
    path = baselines_dir / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_baseline(summary: dict[str, Any], baselines_dir: Path, name: str = "baseline") -> Path:
    baselines_dir.mkdir(parents=True, exist_ok=True)
    path = baselines_dir / f"{name}.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def compare_to_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    overall_delta = round(current["overall_score"] - baseline["overall_score"], 1)

    baseline_books = {b["book_id"]: b for b in baseline["books"]}
    per_book_delta = []
    for book in current["books"]:
        base_book = baseline_books.get(book["book_id"])
        if base_book is None or base_book.get("score") is None or book.get("score") is None:
            continue
        delta = round(book["score"] - base_book["score"], 1)
        if abs(delta) >= 0.05:
            per_book_delta.append({"book_id": book["book_id"], "delta": delta, "before": base_book["score"], "after": book["score"]})

    per_book_delta.sort(key=lambda d: d["delta"])

    return {
        "baseline_timestamp": baseline.get("timestamp"),
        "overall_delta": overall_delta,
        "per_book_delta": per_book_delta,
    }


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "  n/a"
    return f"{value * 100:5.1f}%"


def print_terminal_summary(summary: dict[str, Any], comparison: dict[str, Any] | None) -> None:
    for warning in summary.get("tool_warnings", []):
        print(f"[uyari] {warning}")
    print()
    print("Publisco Conversion Evaluation")
    print(f"Variant: {summary['variant']}  |  Books: {summary['book_count']}")
    print(f"Overall Score: {summary['overall_score']}")
    print()
    for name, label in METRIC_LABELS.items():
        print(f"  {label:<20} {_fmt_pct(summary['metric_averages'].get(name))}")
    print()

    tier_scores = summary.get("tier_scores") or {}
    if tier_scores:
        print("Seviye bazında skor:")
        for tier in ("easy", "medium", "hard"):
            if tier in tier_scores:
                print(f"  {tier:<8} {tier_scores[tier]['score']:>5.1f}  ({tier_scores[tier]['book_count']} kitap)")
        print()

    _print_flow_defects(summary["books"])
    _print_refine(summary["books"])

    if comparison is not None:
        sign = "+" if comparison["overall_delta"] >= 0 else ""
        print(f"Regression vs baseline ({comparison['baseline_timestamp']}):")
        print(f"  {sign}{comparison['overall_delta']} overall")
        for entry in comparison["per_book_delta"]:
            sign = "+" if entry["delta"] >= 0 else ""
            print(f"    {entry['book_id']:<28} {entry['before']:>5.1f} -> {entry['after']:>5.1f}  ({sign}{entry['delta']})")
        print()
    else:
        print("(Baseline yok -- --save-baseline ile bu koşuyu baseline yapabilirsin)")
        print()

    if summary["failed_books"]:
        print("Dikkat gerektiren kitaplar:")
        for entry in summary["failed_books"]:
            reason = entry["error"] or ", ".join(entry["gates"]) or "düşük skor"
            score_str = "N/A" if entry["score"] is None else entry["score"]
            print(f"  {entry['book_id']:<28} score={score_str}  ({reason})")
        print()


def _flow_defect_counts(metric_details: dict[str, Any]) -> dict[str, int]:
    """Soruna özel dört sayaç -- skora girmez, tek tek kuralların etkisini izlemek için."""
    flow = metric_details.get("flow_defects", {})
    return {
        "broken_words": metric_details.get("broken_words", {}).get("confirmed_count", 0) or 0,
        "dangling_hyphens": flow.get("dangling_hyphen_count", 0) or 0,
        "split_paragraphs": flow.get("split_paragraph_count", 0) or 0,
        "leaked_headers": metric_details.get("duplicates", {}).get("leaked_short_block_total_occurrences", 0) or 0,
    }


def _print_flow_defects(books: list[dict[str, Any]]) -> None:
    rows = [
        (b["book_id"], _flow_defect_counts(b.get("metric_details") or {}))
        for b in books
        if not b.get("unsupported") and not b.get("error")
    ]
    rows = [(book_id, counts) for book_id, counts in rows if any(counts.values())]
    if not rows:
        return
    print("Akış kusurları (skora girmez):")
    print(f"  {'kitap':<44} {'kırık kelime':>12} {'tireli son':>10} {'bölünmüş ¶':>10} {'sızan başlık':>12}")
    for book_id, c in rows:
        print(
            f"  {book_id[:44]:<44} {c['broken_words']:>12} {c['dangling_hyphens']:>10} "
            f"{c['split_paragraphs']:>10} {c['leaked_headers']:>12}"
        )
    print()


def _print_refine(books: list[dict[str, Any]]) -> None:
    rows = [(b["book_id"], (b.get("metric_details") or {}).get("refine")) for b in books]
    rows = [(book_id, r) for book_id, r in rows if r and r.get("mode") != "off"]
    if not rows:
        return
    mode, model = rows[0][1]["mode"], rows[0][1].get("model")
    print(f"Refine ({mode}{', ' + model if model else ''}):")
    print(f"  {'kitap':<44} {'aday':>6} {'birleşti':>9} {'veto':>6} {'hata':>6} {'token':>8}")
    for book_id, r in rows:
        print(
            f"  {book_id[:44]:<44} {r['candidate_count']:>6} {r['joined_count']:>9} {r['vetoed_count']:>6} "
            f"{r['model_error_count']:>6} {r['input_tokens']:>8}"
        )
    print()


def print_book_diagnostics(book: BookResult) -> None:
    print()
    print(f"=== {book.book_id} ({book.category}) ===")
    print(f"Score: {book.score}  [{book.category_label}]")
    if book.error:
        print(f"Conversion error: {book.error}")
        return
    if book.gates_triggered:
        print(f"Gates triggered: {', '.join(book.gates_triggered)}")
    print()
    print("Component scores:")
    for name, label in METRIC_LABELS.items():
        print(f"  {label:<20} {_fmt_pct(book.metric_scores.get(name))}")
    print()
    details = book.metric_details
    if details:
        oq = details.get("ocr_quality", {})
        if oq.get("scanned_page_count"):
            print(f"  OCR confidence: {oq.get('avg_confidence', 0):.1f}%")
            print(f"  Low confidence pages: {(oq.get('low_confidence_page_pct') or 0) * 100:.1f}%")
        dup = details.get("duplicates", {})
        if dup.get("leaked_short_blocks"):
            print(f"  Repeated header/footer-like blocks: {dup.get('leaked_short_block_total_occurrences', 0)}")
        elif dup.get("repeated_short_blocks"):
            print(
                "  Repeated short blocks (not page-leak-like, no score penalty): "
                f"{dup.get('repeated_short_block_total_occurrences', 0)}"
            )
        bw = details.get("broken_words", {})
        if bw.get("confirmed_count"):
            print(f"  Broken words: {bw.get('confirmed_count', 0)}")
        flow = details.get("flow_defects", {})
        if flow.get("dangling_hyphen_count"):
            print(f"  Paragraphs ending in a hyphenated fragment: {flow['dangling_hyphen_count']}")
            for sample in flow.get("dangling_hyphen_samples", []):
                print(f"      {sample}")
        if flow.get("split_paragraph_count"):
            print(f"  Split paragraphs: {flow['split_paragraph_count']}")
            for sample in flow.get("split_paragraph_samples", []):
                print(f"      {sample}")
        img = details.get("images", {})
        missing = img.get("missing_vs_expected") if img.get("missing_vs_expected") is not None else img.get("missing_vs_pdf")
        if missing:
            print(f"  Missing images: {missing}")
        struct = details.get("structure", {})
        if struct.get("chapter_recall") is not None:
            print(f"  TOC recall: {struct['chapter_recall'] * 100:.1f}%")
        tc = details.get("text_completeness", {})
        if tc.get("phrase_include_misses"):
            print(f"  Missing phrases: {tc['phrase_include_misses']}")
        if tc.get("phrase_exclude_violations"):
            print(f"  Leaked excluded phrases: {tc['phrase_exclude_violations']}")
        if tc.get("phrase_exclude_sparse"):
            occurrences = tc.get("phrase_exclude_occurrences", {})
            sparse = {p: occurrences.get(p) for p in tc["phrase_exclude_sparse"]}
            print(f"  Sparse excluded phrases (not penalized, phrase -> count): {sparse}")
    print()
