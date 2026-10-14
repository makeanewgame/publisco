"""Faz 3 pilotu: `<h2>` olarak işaretlenen kısa satırlar gerçekten bölüm içi başlık mı?

Dönüştürücü kısa, noktalamasız, büyük/kalın puntolu satırları `<h2>` yapıyor; bunların
bir kısmı epigraf yazarı, tablo sütun başlığı ya da kısa diyalog satırı. Bu betik her
`<h2>`'yi önceki ve sonraki blokla birlikte karar modellerine sorar.

    python -m eval.pilots.heading_pilot extract turkish_bilimsel-makale-nasil-yazilir
    # -> eval/.cache/pilot/<kitap>.headings.json ; `label` elle doldurulur (true/false)
    python -m eval.pilots.heading_pilot run <kitap> --model microsoft/microsoft-decision-1
    python -m eval.pilots.heading_pilot compare <kitap>
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from converter import analyze_pdf, plan_conversion, process_page_range  # noqa: E402
from eval import ocr_cache  # noqa: E402
from eval.golden.loader import load_real_books  # noqa: E402
from eval.pilots.jev_pilot import _api_key, _auc  # noqa: E402
from refine.decision_client import DecisionClient, NoulQuestion  # noqa: E402

PILOT_DIR = Path(__file__).resolve().parents[1] / ".cache" / "pilot"
DECISION_CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "decisions"
CONTEXT_CHARS = 160
MAX_WORKERS = 4

IS_HEADING = NoulQuestion(
    instructions=(
        "line was extracted from a book page; previous_text and next_text are the blocks around it. "
        "Is line a section heading or subheading that introduces the text that follows it, rather than "
        "a person's name or source under a quotation, a table or figure label, a page header, or a short "
        "line of ordinary prose or dialogue?"
    )
)

_BLOCK_RE = re.compile(r"^<(p|h2)(?: [^>]*)?>(.*)</\1>$", re.DOTALL)


def _text(line: str) -> tuple[str, str] | None:
    match = _BLOCK_RE.match(line)
    return (match.group(1), html.unescape(match.group(2))) if match else None


def extract(book_id: str) -> None:
    book = next((b for b in load_real_books() if b.id == book_id), None)
    if book is None:
        sys.exit(f"Kitap bulunamadı: {book_id}")
    ocr_cache.install()
    pdf_bytes = book.pdf_loader()
    config = dict(book.config)
    config["chapters"] = config.get("chapters") or analyze_pdf(pdf_bytes).get("chapters")
    plan = plan_conversion(pdf_bytes, config)
    pages = [p for s, e in plan.chunks for p in process_page_range(pdf_bytes, s, e, plan.resolved_config)]

    blocks = [(p.page_num, t) for p in sorted(pages, key=lambda p: p.page_num) for t in map(_text, p.html.split("\n")) if t]
    candidates = []
    for i, (page_num, (tag, text)) in enumerate(blocks):
        if tag != "h2" or re.fullmatch(r"Sayfa \d+", text):  # görsel sayfa başlığını dönüştürücü üretiyor
            continue
        candidates.append(
            {
                "id": f"h-{len(candidates)}",
                "page": page_num,
                "line": text,
                "previous_text": blocks[i - 1][1][1][-CONTEXT_CHARS:] if i > 0 else "",
                "next_text": blocks[i + 1][1][1][:CONTEXT_CHARS] if i + 1 < len(blocks) else "",
                "label": None,
            }
        )
    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    path = PILOT_DIR / f"{book_id}.headings.json"
    if path.exists():
        old = {c["id"]: c for c in json.loads(path.read_text(encoding="utf-8"))}
        for c in candidates:
            if c["id"] in old and old[c["id"]]["line"] == c["line"]:
                c["label"] = old[c["id"]]["label"]
    path.write_text(json.dumps(candidates, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(candidates)} aday -> {path}")


def _results_path(book_id: str, model: str) -> Path:
    return PILOT_DIR / f"{book_id}.headings.results.{model.replace('/', '_')}.json"


def run(book_id: str, model: str) -> None:
    candidates = [c for c in json.loads((PILOT_DIR / f"{book_id}.headings.json").read_text(encoding="utf-8")) if c["label"] is not None]
    client = DecisionClient(_api_key(), model, cache_dir=DECISION_CACHE_DIR)

    def ask(c: dict) -> dict:
        response, _ = client.ask(
            {"line": c["line"], "previous_text": c["previous_text"], "next_text": c["next_text"]}, {"is_heading": IS_HEADING}
        )
        return {"id": c["id"], "p": None if response is None else response.answers["is_heading"].noul,
                "tokens": 0 if response is None else response.usage.input_tokens}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(ask, candidates))
    _results_path(book_id, model).write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"{model}: {sum(r['p'] is not None for r in results)}/{len(results)} yanıt")


def compare(book_id: str) -> None:
    labels = {c["id"]: c["label"] for c in json.loads((PILOT_DIR / f"{book_id}.headings.json").read_text(encoding="utf-8"))}
    print(f"  {'model':<34}{'n':>4}{'poz/neg':>9}{'AUC':>7}{'0.5 doğru':>11}{'yanlış ret':>12}{'kaçan':>7}")
    for path in sorted(PILOT_DIR.glob(f"{book_id}.headings.results.*.json")):
        rows = [(r["p"], labels[r["id"]]) for r in json.loads(path.read_text(encoding="utf-8")) if r["p"] is not None and labels.get(r["id"]) is not None]
        pos = sum(1 for _, y in rows if y)
        auc = _auc(rows)
        model = path.name.split(".headings.results.")[1][:-5]
        print(
            f"  {model:<34}{len(rows):>4}{f'{pos}/{len(rows) - pos}':>9}{'  n/a' if auc is None else f'{auc:7.3f}'}"
            f"{sum(1 for p, y in rows if (p >= 0.5) == y):>8}/{len(rows):<3}"
            f"{sum(1 for p, y in rows if y and p < 0.5):>10}{sum(1 for p, y in rows if not y and p >= 0.5):>8}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["extract", "run", "compare"])
    parser.add_argument("book_id")
    parser.add_argument("--model", default="microsoft/microsoft-decision-1")
    args = parser.parse_args()
    if args.command == "extract":
        extract(args.book_id)
    elif args.command == "run":
        run(args.book_id, args.model)
    else:
        compare(args.book_id)


if __name__ == "__main__":
    main()
