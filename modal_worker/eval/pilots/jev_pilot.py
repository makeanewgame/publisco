"""Faz 1 pilotu (bkz. ROADMAP.md "Yeni yön"): `typesafe-ai/jev`, paragraf
sınırındaki iki kararı Türkçe metinde ne kadar doğru veriyor?

  - same_word: tireyle biten paragrafın devamı sonraki paragrafın ilk kelimesi mi
    (tireyi atıp birleştir) yoksa tire gerçek mi?
  - same_paragraph: sonraki paragraf öncekinin devamı mı (birleştir) yoksa gerçekten
    yeni bir paragraf mı?

Kullanım (modal_worker/ içinden):
    python -m eval.pilots.jev_pilot extract normal-text-novel_son-sans
    # -> eval/.cache/pilot/<kitap>.candidates.json ; `label` alanları elle doldurulur
    python -m eval.pilots.jev_pilot run normal-text-novel_son-sans

Aday dosyaları kitap metni içerdiği için `eval/.cache/` altında kalır (git'e girmez).
`AI_GATEWAY_API_KEY` ortamdan ya da `modal_worker/.env`'den okunur.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval import ocr_cache  # noqa: E402
from eval.epub_reader import read_epub  # noqa: E402
from eval.golden.loader import load_real_books  # noqa: E402
from eval.metrics.flow_defects import (  # noqa: E402
    _DANGLING_HYPHEN_RE,
    _SENTENCE_END_CHARS,
    SPLIT_MIN_PREV_CHARS,
    _starts_lowercase,
)
from eval.runner import run_conversion  # noqa: E402

PILOT_DIR = Path(__file__).resolve().parents[1] / ".cache" / "pilot"
GATEWAY_URL = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
MODEL = "typesafe-ai/jev"
CONTEXT_CHARS = 200
CONTROL_SAMPLE_SIZE = 60
MAX_WORKERS = 4  # uç nokta hız sınırı uyguluyor; küçük tut
ACT_ABOVE, ACT_BELOW = 0.85, 0.15  # başlangıç eşikleri; pilotun amacı bunları ölçmek

QUESTIONS = {
    "same_word": {
        "type": "noul",
        "instructions": (
            "prev_end is the end of one text block and ends with a hyphen. next_start is the "
            "beginning of the following block. Is the hyphen only a line-break hyphen, i.e. the "
            "fragment before it and the first word of next_start are two halves of ONE word that "
            "should be written together without the hyphen?"
        ),
    },
    "same_paragraph": {
        "type": "noul",
        "instructions": (
            "prev_end is the end of one text block and next_start is the beginning of the following "
            "block, extracted from a book PDF. Does next_start continue the same sentence or "
            "paragraph as prev_end (the two were split only by a line or page break), rather than "
            "starting a new paragraph, heading or caption?"
        ),
    },
}


def _api_key() -> str:
    key = os.environ.get("AI_GATEWAY_API_KEY")
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not key and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("AI_GATEWAY_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        sys.exit("AI_GATEWAY_API_KEY bulunamadı (ortam değişkeni ya da modal_worker/.env).")
    return key


def extract(book_id: str) -> Path:
    book = next((b for b in load_real_books() if b.id == book_id), None)
    if book is None:
        sys.exit(f"Kitap bulunamadı: {book_id}")
    ocr_cache.install()
    artifact = run_conversion(book.pdf_loader(), book.config, book.id)
    if artifact.error:
        sys.exit(f"Dönüşüm hatası: {artifact.error}")
    paragraphs = [p.strip() for p in read_epub(artifact.epub_bytes).paragraphs if p and p.strip()]

    by_kind: dict[str, list[tuple[str, str]]] = {"hyphen": [], "split": [], "control": []}
    for prev, nxt in zip(paragraphs, paragraphs[1:]):
        if _DANGLING_HYPHEN_RE.search(prev):
            by_kind["hyphen"].append((prev, nxt))
        elif len(prev) >= SPLIT_MIN_PREV_CHARS and prev[-1] not in _SENTENCE_END_CHARS and _starts_lowercase(nxt):
            by_kind["split"].append((prev, nxt))
        elif len(prev) >= SPLIT_MIN_PREV_CHARS:
            by_kind["control"].append((prev, nxt))
    rng = random.Random(0)
    by_kind["control"] = rng.sample(by_kind["control"], min(CONTROL_SAMPLE_SIZE, len(by_kind["control"])))

    candidates = [
        {
            "id": f"{kind}-{i}",
            "kind": kind,
            "prev_end": prev[-CONTEXT_CHARS:],
            "next_start": nxt[:CONTEXT_CHARS],
            # Elle doldurulur: same_word / same_paragraph için true|false (bilinmiyorsa null).
            "label": {"same_word": None, "same_paragraph": None},
        }
        for kind, pairs in by_kind.items()
        for i, (prev, nxt) in enumerate(pairs)
    ]
    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    path = PILOT_DIR / f"{book_id}.candidates.json"
    if path.exists():  # daha önce girilmiş etiketleri koru
        old = {c["id"]: c for c in json.loads(path.read_text(encoding="utf-8"))}
        for c in candidates:
            prior = old.get(c["id"])
            if prior and (prior["prev_end"], prior["next_start"]) == (c["prev_end"], c["next_start"]):
                c["label"] = prior["label"]
    path.write_text(json.dumps(candidates, indent=1, ensure_ascii=False), encoding="utf-8")
    print({kind: len(pairs) for kind, pairs in by_kind.items()}, "->", path)
    return path


def _ask(key: str, candidate: dict) -> dict:
    questions = QUESTIONS if candidate["kind"] == "hyphen" else {"same_paragraph": QUESTIONS["same_paragraph"]}
    started = time.monotonic()
    response = requests.post(
        GATEWAY_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": MODEL,
            "state": {"prev_end": candidate["prev_end"], "next_start": candidate["next_start"]},
            "questions": questions,
        },
        timeout=30,
    )
    if response.status_code != 200:
        return {"id": candidate["id"], "error": f"{response.status_code}: {response.text[:200]}"}
    body = response.json()
    return {
        "id": candidate["id"],
        "nouls": {name: answer["noul"] for name, answer in body["answers"].items()},
        "input_tokens": body.get("usage", {}).get("input_tokens", 0),
        "seconds": round(time.monotonic() - started, 2),
    }


def run(book_id: str) -> None:
    path = PILOT_DIR / f"{book_id}.candidates.json"
    if not path.exists():
        sys.exit(f"Önce: python -m eval.pilots.jev_pilot extract {book_id}")
    candidates = json.loads(path.read_text(encoding="utf-8"))
    key = _api_key()

    first = _ask(key, candidates[0])  # yetki/bakiye hatasında yüzlerce istek atma
    if "error" in first:
        sys.exit(f"Jev çağrısı başarısız: {first['error']}")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = [first] + list(pool.map(lambda c: _ask(key, c), candidates[1:]))
    (PILOT_DIR / f"{book_id}.results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    ok = [r for r in results if "nouls" in r]
    by_id = {c["id"]: c for c in candidates}
    print(f"{len(ok)}/{len(results)} yanıt, {sum(r['input_tokens'] for r in ok)} giriş token, "
          f"ortalama {sum(r['seconds'] for r in ok) / max(len(ok), 1):.2f} sn/istek")
    for question in QUESTIONS:
        rows = [(r["nouls"][question], by_id[r["id"]]["label"].get(question)) for r in ok if question in r["nouls"]]
        labeled = [(p, y) for p, y in rows if y is not None]
        sure = [(p, y) for p, y in labeled if p >= ACT_ABOVE or p <= ACT_BELOW]
        correct = sum(1 for p, y in sure if (p >= ACT_ABOVE) == y)
        print(f"  {question}: {len(rows)} aday, {len(labeled)} etiketli | emin bölgede {len(sure)} "
              f"(doğru {correct}), kararsız {len(labeled) - len(sure)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["extract", "run"])
    parser.add_argument("book_id")
    args = parser.parse_args()
    {"extract": extract, "run": run}[args.command](args.book_id)


if __name__ == "__main__":
    main()
