"""Referanssız metrik: kırık kelimeleri (ör. "extraordi- nary") tespit eder.

`clean_text` (converter.py) yalnızca TEK bir sayfa içindeki "-\\n" satır
sonu tirelemesini birleştirir -- sayfa sınırını aşan bir kelime bölünmesi
(bir sayfanın son kelimesi tire ile biter, devamı bir sonraki sayfada başlar)
`process_page` sayfa bazlı çalıştığı için birleştirilmez. Bu metrik, EPUB'ın
tam metnini (blok sınırlarından bağımsız, sürekli akış olarak) tarayıp bu
deseni yakalar; `wordfreq` ile birleşimin gerçek bir kelime olup olmadığını
(yanlış pozitifleri elemek için -- ör. "well-known" gibi meşru kısa tire
bileşiklerini yakalamamak) doğrular.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from eval.text_utils import tokenize_words

try:
    from wordfreq import zipf_frequency
except ImportError:  # eval-only bağımlılık; kurulu değilse metrik devre dışı kalır
    zipf_frequency = None

_HYPHEN_BREAK_RE = re.compile(r"([^\W\d_]+)-\s+([^\W\d_]+)", re.UNICODE)

_LANG_ALIASES = {"zh-cn": "zh", "zh-tw": "zh"}


@dataclass
class BrokenWordsResult:
    available: bool = True
    candidate_count: int = 0
    confirmed_count: int = 0
    confirmed_samples: list[str] = field(default_factory=list)
    per_1000_words: float = 0.0


def evaluate_broken_words(full_text: str, language: str) -> BrokenWordsResult:
    if zipf_frequency is None:
        return BrokenWordsResult(available=False)

    lang = _LANG_ALIASES.get(language, language)

    candidates = _HYPHEN_BREAK_RE.findall(full_text)
    confirmed_samples: list[str] = []
    confirmed_count = 0

    for part1, part2 in candidates:
        combined = (part1 + part2).casefold()
        try:
            combined_freq = zipf_frequency(combined, lang)
            part1_freq = zipf_frequency(part1.casefold(), lang)
            part2_freq = zipf_frequency(part2.casefold(), lang)
        except Exception:
            continue

        if combined_freq > 0 and combined_freq >= max(part1_freq, part2_freq):
            confirmed_count += 1
            if len(confirmed_samples) < 10:
                confirmed_samples.append(f"{part1}-{part2} -> {combined}")

    total_words = max(1, len(tokenize_words(full_text)))
    per_1000 = confirmed_count / (total_words / 1000)

    return BrokenWordsResult(
        candidate_count=len(candidates),
        confirmed_count=confirmed_count,
        confirmed_samples=confirmed_samples,
        per_1000_words=per_1000,
    )
