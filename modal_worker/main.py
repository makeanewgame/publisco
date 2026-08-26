"""Modal orkestrasyonu: PDF -> EPUB dönüştürmeyi plan -> map -> reduce
fazlarına bölüp dağıtık (paralel container) olarak çalıştırır.

Hostinger'daki eski `apps/worker` (tek process, `ThreadPoolExecutor`) tamamen
bu modüle taşındı. Asıl dönüştürme mantığı `converter.py`'de yaşıyor
(değişmedi); burada sadece PDF indirme/Blob yükleme ve fazlar arası
orkestrasyon var.

Deploy: `modal deploy modal_worker/main.py`
Lokal geliştirme: `modal serve modal_worker/main.py`

Gerekli Modal secret'ı (`publisco-secrets` adıyla, `modal secret create` ile
oluşturulur):
  - BLOB_READ_WRITE_TOKEN  (Vercel Blob — indirme/yükleme/silme için)
  - MODAL_WEBHOOK_SECRET   (Vercel <-> Modal arası paylaşılan sır: Vercel'den
                             gelen isteklerde bearer doğrulama, Vercel'e giden
                             webhook'ta HMAC imzalama — aynı sır, tek yönlü
                             değil çift yönlü kullanılıyor)
  - VERCEL_WEBHOOK_URL     (Vercel'in `/api/webhooks/modal-result` tam URL'i)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any

import modal
from fastapi import FastAPI, Header, HTTPException

from converter import (
    ConversionError,
    PageResult,
    PlanResult,
    analyze_pdf,
    assemble_epub,
    plan_conversion,
    process_page_range,
    slice_pdf_pages,
)
from schemas import AnalyzeRequest, ConvertRequest

logger = logging.getLogger("modal_worker.main")

# --- Vercel Blob REST API sabitleri -----------------------------------------
# NOT: Bu değerler `@vercel/blob` JS SDK'sının kullandığı HTTP sözleşmesine
# göre yazıldı (Python'da resmi bir SDK yok). Gerçek deploy öncesi güncel
# Vercel Blob dokümantasyonuna karşı doğrulanmalı — bu görev sırasında canlı
# doğrulama yapılamadı (bkz. sohbet geçmişi).
BLOB_API_BASE = "https://blob.vercel-storage.com"
BLOB_API_VERSION = "7"

DOWNLOAD_RETRIES = 3
DOWNLOAD_BACKOFF_SECONDS = 2.0

image = (
    modal.Image.debian_slim(python_version="3.12")
    # apps/worker/README.md "Sunucu Paketleri" ile senkron tutulmalı: bu, o
    # dosyadaki Tesseract + LANGUAGE_MAP dil paketleri listesinin aynısı.
    .apt_install(
        "tesseract-ocr",
        "tesseract-ocr-tur",
        "tesseract-ocr-eng",
        "tesseract-ocr-deu",
        "tesseract-ocr-fra",
        "tesseract-ocr-spa",
        "tesseract-ocr-ita",
        "tesseract-ocr-por",
        "tesseract-ocr-nld",
        "tesseract-ocr-rus",
        "tesseract-ocr-ara",
        "tesseract-ocr-pol",
        "tesseract-ocr-swe",
        "tesseract-ocr-ell",
        "tesseract-ocr-jpn",
        "tesseract-ocr-kor",
        "tesseract-ocr-chi-sim",
        "tesseract-ocr-chi-tra",
    )
    .pip_install(
        "fastapi[standard]==0.141.1",
        "python-multipart==0.0.32",
        "pymupdf==1.28.2",
        "EbookLib==0.20",
        "pillow==12.3.0",
        "langdetect==1.0.9",
        "pytesseract==0.3.13",
        "requests==2.32.3",
    )
    # Modal artık entrypoint'in yerel dizinini otomatik mount etmiyor — `converter.py`/
    # `schemas.py` gibi sibling modülleri container'a açıkça eklemek gerekiyor, yoksa
    # `from converter import (...)` runtime'da `ModuleNotFoundError` ile patlıyor.
    # En son eklenmeli (Modal'ın önerisi): pip/apt katmanlarının cache'ini bozmadan
    # sadece bu dosyalar değiştiğinde yeniden mount edilir.
    .add_local_python_source("converter", "schemas")
)

app = modal.App("publisco-modal-worker", image=image)
secrets = [modal.Secret.from_name("publisco-secrets")]


# ---------------------------------------------------------------------------
# Blob / webhook yardımcıları
# ---------------------------------------------------------------------------

def _blob_token() -> str:
    return os.environ["BLOB_READ_WRITE_TOKEN"]


def download_pdf(pdf_url: str) -> bytes:
    """Blob URL'inden PDF'i indirir; 25 sayfalık chunk'lara bölündüğünde
    onlarca container aynı anda aynı URL'e GET atacağı için ara sıra
    429/bağlantı reddi bekleniyor — bu yüzden basit bir üstel backoff'la
    yeniden dener."""
    import requests

    last_exc: Exception | None = None
    for attempt in range(DOWNLOAD_RETRIES):
        try:
            response = requests.get(
                pdf_url,
                headers={"Authorization": f"Bearer {_blob_token()}"},
                timeout=120,
            )
            response.raise_for_status()
            return response.content
        except Exception as exc:  # noqa: BLE001 — retry döngüsünde her hatayı yakalıyoruz
            last_exc = exc
            if attempt < DOWNLOAD_RETRIES - 1:
                time.sleep(DOWNLOAD_BACKOFF_SECONDS * (2**attempt))
    raise ConversionError(f"PDF indirilemedi: {last_exc}") from last_exc


def upload_epub_to_blob(pathname: str, epub_bytes: bytes) -> str:
    """EPUB baytlarını Vercel Blob'a yükler, ortaya çıkan (indirilebilir) URL'i döner."""
    import requests

    response = requests.put(
        f"{BLOB_API_BASE}/{pathname}",
        data=epub_bytes,
        headers={
            "Authorization": f"Bearer {_blob_token()}",
            "x-api-version": BLOB_API_VERSION,
            "x-content-type": "application/epub+zip",
            "x-add-random-suffix": "0",
            "x-vercel-blob-access": "private",
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["url"]


def delete_blob(url: str) -> None:
    """Kaynak PDF'i indirdikten sonra en iyi çaba ile siler (Modal artık ona
    ihtiyaç duymuyor) — silme başarısız olsa da pipeline'ı bozmaz."""
    import requests

    try:
        response = requests.post(
            f"{BLOB_API_BASE}/delete",
            json={"urls": [url]},
            headers={
                "Authorization": f"Bearer {_blob_token()}",
                "x-api-version": BLOB_API_VERSION,
            },
            timeout=30,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Kaynak PDF blob'u silinemedi (best-effort): %s", exc)


def _sign_webhook_body(body: bytes) -> str:
    secret = os.environ["MODAL_WEBHOOK_SECRET"]
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def post_vercel_webhook(payload: dict[str, Any]) -> None:
    """Vercel'in `/api/webhooks/modal-result`'ına sonucu (ya da hatayı) bildirir.
    Lemon Squeezy webhook deseniyle aynı: ham gövde üzerinden HMAC-SHA256 imzası,
    `X-Signature` header'ında. Vercel bu isteği idempotent işler (bkz.
    `modal-webhook.controller.ts`), o yüzden burada retry basit tutulabilir."""
    import json

    import requests

    body = json.dumps(payload).encode("utf-8")
    signature = _sign_webhook_body(body)
    webhook_url = os.environ["VERCEL_WEBHOOK_URL"]

    for attempt in range(3):
        try:
            response = requests.post(
                webhook_url,
                data=body,
                headers={"Content-Type": "application/json", "X-Signature": signature},
                timeout=30,
            )
            if response.status_code < 500:
                if not response.ok:
                    # 4xx sessizce "başarılı" sayılırsa (retry döngüsü sadece 5xx'te tekrar dener)
                    # DB'deki ConvertJob.status hiç güncellenmez ve frontend sonsuza dek
                    # polling yapar — bu yüzden 4xx'i de yüksek sesle logluyoruz.
                    logger.error(
                        "Vercel webhook %d döndü (kalıcı hata, tekrar denenmeyecek): %s",
                        response.status_code,
                        response.text[:500],
                    )
                return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vercel webhook denemesi %d başarısız: %s", attempt + 1, exc)
        time.sleep(2.0 * (2**attempt))
    logger.error("Vercel webhook'u %d denemeden sonra da gönderilemedi (job devam ediyor sayılacak).", 3)


def _require_bearer(authorization: str | None) -> None:
    expected = os.environ["MODAL_WEBHOOK_SECRET"]
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid bearer token.")


# ---------------------------------------------------------------------------
# Plan / map / reduce Modal fonksiyonları
# ---------------------------------------------------------------------------

@app.function(secrets=secrets, timeout=300)
def plan(pdf_url: str, config: dict[str, Any]) -> tuple[PlanResult, list[bytes]]:
    """PDF'i indirip planı çıkarır, AYRICA her chunk için yalnızca o sayfa
    aralığını içeren küçük bir PDF dilimi üretir (`slice_pdf_pages`) — bu
    dilimler `process_chunk`'a Blob üzerinden değil doğrudan Modal RPC'siyle
    geçiriliyor, her map container'ının orijinal PDF'in TAMAMINI ayrıca
    indirmesini önlüyor (bkz. NOTES.md: `process_chunk` egress israfı)."""
    pdf_bytes = download_pdf(pdf_url)
    plan_result = plan_conversion(pdf_bytes, config)
    chunk_pdf_bytes = [slice_pdf_pages(pdf_bytes, start_page, end_page) for start_page, end_page in plan_result.chunks]
    return plan_result, chunk_pdf_bytes


@app.function(secrets=secrets, timeout=600)
def process_chunk(
    chunk_pdf_bytes: bytes, start_page: int, end_page: int, config: dict[str, Any], force_ocr: bool
) -> list[PageResult]:
    """`chunk_pdf_bytes`, `plan()`'ın bu `(start_page, end_page)` aralığı için
    önceden dilimlediği küçük bir PDF (bkz. `slice_pdf_pages`) — Blob'dan ayrıca
    bir şey indirmez, `.map()` ile paralel çağrılır."""
    return process_page_range(chunk_pdf_bytes, start_page, end_page, config, force_ocr=force_ocr, sliced=True)


@app.function(secrets=secrets, memory=2048, timeout=300)
def reduce_and_build_epub(plan_result: PlanResult, page_results_per_chunk: list[list[PageResult]]) -> bytes:
    """Bellek açıkça yükseltilir (2048MB): bu faz tüm chunk'lardan gelen
    HTML/görsel byte'larını tek container'da toplayıp `ebooklib`'le
    paketliyor, Modal'ın varsayılan limiti çok sayfalı/görsel ağırlıklı
    kitaplarda yetersiz kalabiliyor."""
    all_page_results = [pr for chunk_results in page_results_per_chunk for pr in chunk_results]
    return assemble_epub(plan_result, all_page_results)


@app.function(secrets=secrets, timeout=1800)
def run_pipeline(
    job_id: str,
    pdf_url: str,
    title: str | None,
    author: str | None,
    language: str,
    options: dict[str, Any],
    force_ocr: bool,
) -> None:
    """`.spawn()` ile arka planda çalışır: indir -> plan -> map -> reduce ->
    Blob'a yükle -> Vercel webhook'una POST. Her aşamada hata `status: FAILED`
    webhook'una çevrilir ki Vercel kotayı serbest bırakabilsin."""
    try:
        config = dict(options)
        if title:
            config["title"] = title
        if author:
            config["author"] = author
        if language:
            config["language"] = language

        plan_result, chunk_pdf_bytes = plan.remote(pdf_url, config)

        if not plan_result.chunks:
            raise ConversionError("PDF'te işlenecek sayfa bulunamadı.")

        # Kaynak PDF'e artık yalnızca plan fazı ihtiyaç duydu (chunk'lar kendi
        # dilimlerini RPC'yle aldı, Blob'a hiç dokunmuyor) — map fazını beklemeden
        # hemen silinebilir.
        delete_blob(pdf_url)

        page_results_per_chunk = list(
            process_chunk.starmap(
                [
                    (chunk_bytes, start_page, end_page, plan_result.resolved_config, force_ocr)
                    for (start_page, end_page), chunk_bytes in zip(plan_result.chunks, chunk_pdf_bytes)
                ]
            )
        )

        epub_bytes = reduce_and_build_epub.remote(plan_result, page_results_per_chunk)

        epub_pathname = f"convert-results/{job_id}.epub"
        epub_url = upload_epub_to_blob(epub_pathname, epub_bytes)

        post_vercel_webhook({"job_id": job_id, "status": "COMPLETED", "epub_url": epub_url})
    except Exception as exc:  # noqa: BLE001 — pipeline'ın her hatası webhook'a çevrilmeli
        logger.exception("Dönüştürme başarısız (job %s)", job_id)
        post_vercel_webhook({"job_id": job_id, "status": "FAILED", "error": str(exc)})


# ---------------------------------------------------------------------------
# Web endpoint'ler — Vercel API bunları çağırır
#
# `/convert` ve `/analyze` bilinçli olarak TEK bir Modal fonksiyonu
# (`fastapi_app`, `@modal.asgi_app()`) altında, ortak bir FastAPI app'in iki
# route'u olarak tanımlanıyor — Modal'ın varsayılan davranışı her
# `@modal.fastapi_endpoint` fonksiyonuna KENDİ ayrı URL'ini vermek (ortak bir
# base + path değil); Vercel tarafı (`apps/api/src/convert/convert.service.ts`)
# ise tek bir `MODAL_ENDPOINT_URL` + `/convert`/`/analyze` path'i varsayıyor.
# Tek ASGI app bu varsayımı doğru kılıyor: `modal deploy` sonunda tek bir URL
# çıkar, o URL `MODAL_ENDPOINT_URL` olarak Vercel'e verilir.
# ---------------------------------------------------------------------------

web_app = FastAPI()


@web_app.post("/convert")
def convert_endpoint(request: ConvertRequest, authorization: str = Header(None)) -> dict[str, Any]:
    """Senkron işlemek Modal'ın kendi timeout'una takılabilir ve Vercel'i
    gereksiz bekletir — bu yüzden ağır pipeline `.spawn()` ile arka plana
    devredilip anında 202 dönülür."""
    _require_bearer(authorization)

    run_pipeline.spawn(
        request.job_id,
        request.pdf_url,
        request.title,
        request.author,
        request.language,
        request.options.to_engine_config(),
        request.force_ocr,
    )
    return {"job_id": request.job_id, "status": "accepted"}


@web_app.post("/analyze")
def analyze_endpoint(request: AnalyzeRequest, authorization: str = Header(None)) -> dict[str, Any]:
    """Eski `/analyze`'ın taşınmış hali — senkron, `/convert` ile aynı şekilde
    PDF'i multipart bayt olarak değil Blob URL'i olarak alır ve kendisi indirir
    (bkz. schemas.AnalyzeRequest — önceki multipart hali, PDF'in client'tan bu
    endpoint'e Vercel API üzerinden bayt olarak geçmesini gerektiriyordu, bu da
    Vercel Function'ın ~4.5MB inbound body limitine takılıp 503 veriyordu)."""
    _require_bearer(authorization)

    pdf_bytes = download_pdf(request.pdf_url)
    try:
        return analyze_pdf(pdf_bytes)
    except ConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.function(secrets=secrets, min_containers=1, timeout=120)
@modal.asgi_app()
def fastapi_app() -> FastAPI:
    """`min_containers=1` ile en az bir container sıcak tutulur: `/analyze`
    kullanıcı dosya seçer seçmez UI'da tetikleniyor, soğuk başlangıç (5-8sn)
    `run_pipeline`'dan çok daha fazla hissedilir; `/convert` zaten `.spawn()`
    ile arka plana geçtiği için aynı sıcak container'ı paylaşması zararsız."""
    return web_app
