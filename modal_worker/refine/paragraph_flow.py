"""Yanlışlıkla ikiye bölünmüş paragrafları bulur ve birleştirir.

İki desen (ikisi de hem sayfa içinde hem sayfa sınırında görülüyor):
  - "hyphen": paragraf tireli bir kelime parçasıyla bitiyor ("ma-", "ka\\xad"),
    sonraki paragraf küçük harfle başlıyor -> tire atılıp bitişik yazılır.
  - "split": paragraf cümle sonu noktalaması olmadan bitiyor, sonraki paragraf
    küçük harfle başlıyor -> araya boşluk konup birleştirilir.

Sayfa HTML'i `converter.py`'nin ürettiği biçimdedir: her satır bir üst düzey
blok (`<p>...</p>`, `<h2>...</h2>`, `<img ... />`, `visual-page` div'i). Yalnızca
sınıfsız düz `<p>` blokları paragraf sayılır; başlık, altyazı ve görsel-sayfa
blokları birleştirmeye engeldir. Sayfa sınırında araya giren `<img>` satırları
(ör. her sayfası arka plan görseliyle başlayan kitaplar) engel sayılmaz --
devam metni önceki paragrafa taşınır, görsel yerinde kalır.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

_PLAIN_PARAGRAPH_RE = re.compile(r"^<p>(.*)</p>$", re.DOTALL)
_IMG_RE = re.compile(r"^<img\b[^>]*/>$")
_HYPHENS = "-­‐"
_DANGLING_HYPHEN_RE = re.compile(rf"[^\W\d_]{{2,}}[{_HYPHENS}]$", re.UNICODE)
_FIRST_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_SENTENCE_END_CHARS = ".!?:;…\"'”’)»›」]"

# Bundan kısa bloklar çoğunlukla başlık/altyazı/etiket -- noktalamasız bitmeleri
# olağan, "split" adayı sayılmazlar ("hyphen" için uzunluk şartı yok).
SPLIT_MIN_PREV_CHARS = 40
CONTEXT_CHARS = 200


@dataclass
class JoinCandidate:
    id: int
    kind: str  # "hyphen" | "split"
    prev_page: int
    next_page: int
    prev_end: str  # önceki paragrafın sonu (en fazla CONTEXT_CHARS), ham metin
    next_start: str  # sonraki paragrafın başı
    # page_results içindeki konumlar: (sayfa indeksi, o sayfanın HTML'indeki satır indeksi)
    prev_pos: tuple[int, int]
    next_pos: tuple[int, int]


@dataclass
class RefineReport:
    mode: str = "off"
    candidate_count: int = 0
    joined_count: int = 0
    vetoed_count: int = 0
    model: str | None = None
    model_error_count: int = 0
    input_tokens: int = 0
    cache_hits: int = 0


def _starts_lowercase(text: str) -> bool:
    match = _FIRST_LETTER_RE.search(text)
    if match is None or match.start() > 2:  # baştaki tırnak/tire gibi 1-2 işarete izin ver
        return False
    ch = match.group()
    return ch.islower() and ch.upper() != ch


def classify_boundary(prev_text: str, next_text: str) -> str | None:
    """İki ardışık paragraf metni birleştirme adayıysa türünü, değilse None döner."""
    prev_text, next_text = prev_text.rstrip(), next_text.lstrip()
    if not prev_text or not next_text or not _starts_lowercase(next_text):
        return None
    if _DANGLING_HYPHEN_RE.search(prev_text):
        return "hyphen"
    if len(prev_text) >= SPLIT_MIN_PREV_CHARS and prev_text[-1] not in _SENTENCE_END_CHARS:
        return "split"
    return None


def join_texts(kind: str, prev_text: str, next_text: str) -> str:
    prev_text, next_text = prev_text.rstrip(), next_text.lstrip()
    if kind == "hyphen":
        return prev_text[:-1] + next_text
    return f"{prev_text} {next_text}"


def _paragraph_text(line: str) -> str | None:
    match = _PLAIN_PARAGRAPH_RE.match(line)
    return html.unescape(match.group(1)) if match else None


def find_join_candidates(page_results: list[Any], chapter_start_pages: set[int] | None = None) -> list[JoinCandidate]:
    """`page_results` sayfa numarasına göre sıralı gezilir; `chapter_start_pages`'teki
    bir sayfanın ilk paragrafı önceki sayfaya birleştirilmez (bölüm sınırı)."""
    chapter_start_pages = chapter_start_pages or set()
    order = sorted(range(len(page_results)), key=lambda i: page_results[i].page_num)

    candidates: list[JoinCandidate] = []
    prev: tuple[int, int, str] | None = None  # (sayfa indeksi, satır indeksi, metin)

    for page_index in order:
        page = page_results[page_index]
        lines = page.html.split("\n") if page.html else []
        if page.page_num in chapter_start_pages:
            prev = None
        at_page_start = True  # henüz bu sayfada `<img>` dışında blok görülmedi

        for line_index, line in enumerate(lines):
            text = _paragraph_text(line)
            if text is None:
                # Sayfa başındaki görseller sayfa sınırını aşan paragrafı kesmez;
                # diğer her blok (başlık, sayfa içi görsel, görsel-sayfa) keser.
                if not (at_page_start and _IMG_RE.match(line)):
                    prev = None
                    at_page_start = False
                continue
            at_page_start = False

            if prev is not None:
                kind = classify_boundary(prev[2], text)
                if kind is not None:
                    candidates.append(
                        JoinCandidate(
                            id=len(candidates),
                            kind=kind,
                            prev_page=page_results[prev[0]].page_num,
                            next_page=page.page_num,
                            prev_end=prev[2].rstrip()[-CONTEXT_CHARS:],
                            next_start=text.lstrip()[:CONTEXT_CHARS],
                            prev_pos=(prev[0], prev[1]),
                            next_pos=(page_index, line_index),
                        )
                    )
            prev = (page_index, line_index, text)

    return candidates


def apply_joins(page_results: list[Any], candidates: list[JoinCandidate], vetoed_ids: set[int] | None = None) -> int:
    """Veto edilmeyen adayları uygular: sonraki paragrafın metni öncekine eklenir,
    sonraki paragrafın satırı silinir. Zincirler (A+B, sonra +C) desteklenir.
    Birleştirilen sayı döner."""
    vetoed_ids = vetoed_ids or set()
    lines_by_page: dict[int, list[str | None]] = {}

    def lines_of(page_index: int) -> list[str | None]:
        if page_index not in lines_by_page:
            lines_by_page[page_index] = list(page_results[page_index].html.split("\n"))
        return lines_by_page[page_index]

    # Bir paragraf başka bir paragrafa taşındıysa, onun "önceki" olduğu sonraki
    # birleştirme taşındığı yere yapılmalı.
    moved_to: dict[tuple[int, int], tuple[int, int]] = {}
    joined = 0
    for candidate in candidates:
        if candidate.id in vetoed_ids:
            continue
        target_pos = moved_to.get(candidate.prev_pos, candidate.prev_pos)
        target_lines, source_lines = lines_of(target_pos[0]), lines_of(candidate.next_pos[0])
        target_text = _paragraph_text(target_lines[target_pos[1]] or "")
        source_text = _paragraph_text(source_lines[candidate.next_pos[1]] or "")
        if target_text is None or source_text is None:
            continue
        merged = join_texts(candidate.kind, target_text, source_text)
        target_lines[target_pos[1]] = f"<p>{html.escape(merged)}</p>"
        source_lines[candidate.next_pos[1]] = None
        moved_to[candidate.next_pos] = target_pos
        joined += 1

    for page_index, lines in lines_by_page.items():
        page_results[page_index].html = "\n".join(line for line in lines if line is not None)
    return joined
