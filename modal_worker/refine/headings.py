"""Başlık olmayan `<h2>`'leri paragrafa indirir (yalnızca `refine_mode="model"`).

Dönüştürücü kısa, noktalamasız, büyük/kalın puntolu satırları `<h2>` yapıyor; bunların
bir kısmı epigraf yazarı ("Plato"), alıntı kaynağı, tablo sütun başlığı ya da romanlarda
mesaj/tabela metni. Her `<h2>` önceki ve sonraki blokla birlikte bir karar modeline
sorulur; model "başlık değil" ihtimalini çok yüksek görürse satır `<p>` olur.

Eşik bilerek çok düşük: pilotta (bkz. ROADMAP.md) Jev 0.1 altında iki kitapta 37 sahte
başlığın 13'ünü yakaladı ve 82 gerçek başlığın hiçbirini indirmedi; eşik yükseldikçe
romanlardaki anlatıcı adı / zaman atlaması başlıkları da indirilmeye başlıyor.
"""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .decision_client import DecisionClient, NoulQuestion

DEFAULT_HEADING_MODEL = "typesafe-ai/jev"
DEMOTE_BELOW = 0.1
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
_GENERATED_HEADING_RE = re.compile(r"^Sayfa \d+$")  # görsel sayfalar için dönüştürücünün ürettiği başlık


@dataclass
class HeadingUsage:
    candidate_count: int = 0
    demoted_count: int = 0
    error_count: int = 0
    input_tokens: int = 0


def demote_false_headings(page_results: list[Any], client: DecisionClient) -> HeadingUsage:
    order = sorted(range(len(page_results)), key=lambda i: page_results[i].page_num)
    lines_by_page = {i: page_results[i].html.split("\n") if page_results[i].html else [] for i in order}

    # (sayfa indeksi, satır indeksi, etiket, metin) -- okuma sırasıyla tüm metin blokları
    blocks: list[tuple[int, int, str, str]] = []
    for page_index in order:
        for line_index, line in enumerate(lines_by_page[page_index]):
            match = _BLOCK_RE.match(line)
            if match:
                blocks.append((page_index, line_index, match.group(1), html.unescape(match.group(2))))

    candidates = []
    for i, (page_index, line_index, tag, text) in enumerate(blocks):
        if tag != "h2" or _GENERATED_HEADING_RE.match(text):
            continue
        state = {
            "line": text,
            "previous_text": blocks[i - 1][3][-CONTEXT_CHARS:] if i > 0 else "",
            "next_text": blocks[i + 1][3][:CONTEXT_CHARS] if i + 1 < len(blocks) else "",
        }
        candidates.append((page_index, line_index, text, state))

    usage = HeadingUsage(candidate_count=len(candidates))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        responses = list(pool.map(lambda c: client.ask(c[3], {"is_heading": IS_HEADING}), candidates))

    for (page_index, line_index, text, _), (response, from_cache) in zip(candidates, responses):
        if response is None:
            usage.error_count += 1
            continue
        if not from_cache:
            usage.input_tokens += response.usage.input_tokens
        if response.answers["is_heading"].noul < DEMOTE_BELOW:
            lines_by_page[page_index][line_index] = f"<p>{html.escape(text)}</p>"
            usage.demoted_count += 1

    if usage.demoted_count:
        for page_index, lines in lines_by_page.items():
            page_results[page_index].html = "\n".join(lines)
    return usage
