"""Eval koşularında Tesseract çağrılarını diskte önbelleğe alır.

Tam koşunun süresinin büyük kısmı taranmış kitapların OCR'ına gidiyor (bkz.
`golden/loader.py`'deki `FAST_SUBSET_BOOK_IDS` notu) ve bu çıktı, converter'ın
OCR'dan SONRAKİ mantığı (paragraf birleştirme, başlık tespiti, kenar payı
filtresi, reduce) değiştiğinde aynı kalıyor. Bu modül `pytesseract.image_to_data`'yı
sarar: aynı piksel + aynı parametrelerle yapılan çağrı ikinci kez Tesseract'ı
çalıştırmaz.

Yalnızca eval içindir -- `converter.py`'ye dokunmaz, prod pipeline'ı etkilemez.
Anahtar görselin piksellerinden türediği için render'ı etkileyen bir değişiklik
(DPI, ön işleme) kendiliğinden yeni bir anahtar üretir; elle geçersiz kılmak
gerekmez. Tesseract sürümü de anahtara dahildir.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import pickle
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "ocr"


@dataclass
class OcrCacheStats:
    hits: int = 0
    misses: int = 0


def _cache_key(image: Any, params: dict[str, Any], engine_version: str) -> str:
    digest = hashlib.sha256()
    digest.update(engine_version.encode())
    digest.update(f"{image.mode}|{image.size}".encode())
    digest.update(image.tobytes())
    digest.update(repr(sorted(params.items())).encode())
    return digest.hexdigest()


def install(cache_dir: Path = CACHE_DIR) -> OcrCacheStats | None:
    """`pytesseract.image_to_data`'yı önbellekli sürümle değiştirir. pytesseract
    kurulu değilse (ya da zaten sarılmışsa) hiçbir şey yapmaz, None döner."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None

    original = pytesseract.image_to_data
    if getattr(original, "_eval_ocr_cache", False):
        return None

    try:
        engine_version = str(pytesseract.get_tesseract_version())
    except Exception:  # tesseract binary yok -- önbelleğe alınacak bir şey de yok
        return None

    signature = inspect.signature(original)
    stats = OcrCacheStats()

    def cached_image_to_data(image, *args, **kwargs):
        if not isinstance(image, Image.Image):
            return original(image, *args, **kwargs)

        bound = signature.bind(image, *args, **kwargs)
        bound.apply_defaults()
        params = {name: value for name, value in bound.arguments.items() if name != "image"}
        key = _cache_key(image, params, engine_version)
        path = cache_dir / key[:2] / f"{key}.pkl"

        if path.exists():
            try:
                with path.open("rb") as f:
                    result = pickle.load(f)
                stats.hits += 1
                return result
            except Exception:  # yarım yazılmış/bozuk kayıt -- yeniden üret
                pass

        result = original(image, *args, **kwargs)
        stats.misses += 1

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            pickle.dump(result, f)
        os.replace(tmp_name, path)
        return result

    cached_image_to_data._eval_ocr_cache = True  # type: ignore[attr-defined]
    cached_image_to_data._original = original  # type: ignore[attr-defined]
    pytesseract.image_to_data = cached_image_to_data
    return stats


def uninstall() -> None:
    try:
        import pytesseract
    except ImportError:
        return
    original = getattr(pytesseract.image_to_data, "_original", None)
    if original is not None:
        pytesseract.image_to_data = original
