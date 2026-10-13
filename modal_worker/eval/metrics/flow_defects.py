"""Referanssız teşhis sayaçları: metin akışını bozan, hemen her kitapta görülen
iki genel kusur.

  - Tireyle biten paragraf: bir paragraf "ma-" gibi tireli bir kelime
    parçasıyla bitiyor; devamı ("hallesine ...") sonraki paragrafta. Sayfa
    sonunda bölünen kelimenin birleştirilmediğini gösterir.
  - Bölünmüş paragraf: bir paragraf cümle sonu noktalaması olmadan bitiyor ve
    sonraki paragraf küçük harfle başlıyor -- tek bir paragraf yanlışlıkla
    ikiye ayrılmış (satır sonu/sayfa sonu yeni paragraf sanılmış).

Paragraf İÇİNDE kalan kırık kelimeler ("extraordi- nary") `broken_words`,
sızan koşu başlıkları `duplicates` metriğinde; bu modül onların yakalamadığı,
paragraf SINIRINDAKİ kusurları sayar.

Bilerek skora girmez (bkz. `scoring.py`): genel skor bu kusurları ayırt edecek
kadar hassas değil, bu sayaçlar tek tek kuralların etkisini ölçmek için var.
Büyük/küçük harf ayrımı olmayan yazılarda (ör. Arapça) bölünmüş paragraf
sayacı sıfır kalır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HYPHENS = "-­‐"
_DANGLING_HYPHEN_RE = re.compile(rf"[^\W\d_]{{2,}}[{_HYPHENS}]$", re.UNICODE)
_FIRST_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_SENTENCE_END_CHARS = ".!?:;…\"'”’)»›」]"

# Bundan kısa bloklar çoğunlukla başlık/altyazı/etiket -- noktalamasız bitmeleri
# olağan, bölünmüş paragraf adayı sayılmazlar.
SPLIT_MIN_PREV_CHARS = 40
MAX_SAMPLES = 5


@dataclass
class FlowDefectsResult:
    paragraph_count: int = 0
    dangling_hyphen_count: int = 0
    dangling_hyphen_samples: list[str] = field(default_factory=list)
    split_paragraph_count: int = 0
    split_paragraph_samples: list[str] = field(default_factory=list)


def _starts_lowercase(text: str) -> bool:
    match = _FIRST_LETTER_RE.search(text)
    if match is None or match.start() > 2:  # baştaki tırnak/tire gibi 1-2 işarete izin ver
        return False
    ch = match.group()
    return ch.islower() and ch.upper() != ch


def _sample(prev: str, nxt: str) -> str:
    return f"...{prev[-40:]} ¶ {nxt[:40]}..."


def evaluate_flow_defects(paragraphs: list[str]) -> FlowDefectsResult:
    cleaned = [p.strip() for p in paragraphs if p and p.strip()]
    result = FlowDefectsResult(paragraph_count=len(cleaned))

    for prev, nxt in zip(cleaned, cleaned[1:]):
        if _DANGLING_HYPHEN_RE.search(prev):
            result.dangling_hyphen_count += 1
            if len(result.dangling_hyphen_samples) < MAX_SAMPLES:
                result.dangling_hyphen_samples.append(_sample(prev, nxt))
            continue

        if (
            len(prev) >= SPLIT_MIN_PREV_CHARS
            and prev[-1] not in _SENTENCE_END_CHARS
            and _starts_lowercase(nxt)
        ):
            result.split_paragraph_count += 1
            if len(result.split_paragraph_samples) < MAX_SAMPLES:
                result.split_paragraph_samples.append(_sample(prev, nxt))

    return result
