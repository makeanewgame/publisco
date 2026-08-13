"""`epubcheck` sarmalayıcısı: her dönüştürmenin sonunda EPUB'ın gerçekten
geçerli/açılabilir olduğunu doğrular. Kritik bir gate metriği (bkz.
scoring.py) -- epubcheck hata veriyorsa diğer metrikler ne kadar iyi olursa
olsun genel skor belirli bir tavanın üzerine çıkamaz.

`epubcheck` yerel makinede kurulu değilse (`brew install epubcheck`) metrik
sessizce devre dışı kalır (`available=False`) -- eval'in geri kalanını
bloklamaz, ama terminalde uyarı gösterilir (bkz. report.py)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

EPUBCHECK_TIMEOUT_SECONDS = 120


@dataclass
class EpubValidityResult:
    available: bool = True
    error_count: int = 0
    warning_count: int = 0
    fatal_count: int = 0
    messages_sample: list[str] = field(default_factory=list)
    execution_failed: bool = False


def _find_epubcheck() -> str | None:
    return shutil.which("epubcheck")


def evaluate_epub_validity(epub_bytes: bytes) -> EpubValidityResult:
    epubcheck_bin = _find_epubcheck()
    if epubcheck_bin is None:
        return EpubValidityResult(available=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        epub_path = Path(tmpdir) / "book.epub"
        report_path = Path(tmpdir) / "report.json"
        epub_path.write_bytes(epub_bytes)

        try:
            proc = subprocess.run(
                [epubcheck_bin, str(epub_path), "--json", str(report_path)],
                capture_output=True,
                timeout=EPUBCHECK_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return EpubValidityResult(available=False, execution_failed=True, messages_sample=["epubcheck timeout"])

        if not report_path.exists():
            # epubcheck ikili dosyası bulundu ama çalıştırılamadı (ör. bozuk Java
            # sembolik bağlantısı) -- bu bir EPUB doğrulama hatası DEĞİL, yerel
            # kurulum sorunu. Skoru etkilememesi için `available=False` dönülür.
            stderr_tail = proc.stderr.decode("utf-8", errors="replace")[-300:] if proc.stderr else ""
            return EpubValidityResult(
                available=False, execution_failed=True, messages_sample=[f"epubcheck çalıştırılamadı: {stderr_tail}".strip()]
            )

        report = json.loads(report_path.read_text(encoding="utf-8"))

    checker = report.get("checker", {})
    messages = report.get("messages", [])
    messages_sample = [
        f"{m.get('severity')}: {m.get('message')}" for m in messages if m.get("severity") in ("ERROR", "FATAL")
    ][:10]

    return EpubValidityResult(
        available=True,
        error_count=checker.get("nError", 0),
        warning_count=checker.get("nWarning", 0),
        fatal_count=checker.get("nFatal", 0),
        messages_sample=messages_sample,
    )
