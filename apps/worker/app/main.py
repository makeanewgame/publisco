import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import ValidationError

from .converter import ConversionError, analyze_pdf
from .jobs import job_manager
from .schemas import ConversionOptions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

app = FastAPI(title="publisco Worker", description="PDF -> EPUB dönüştürme servisi")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', " ", name).strip()
    return name or "kitap"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/convert", status_code=202)
async def convert_pdf(
    file: UploadFile = File(..., description="Kaynak PDF dosyası"),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    language: str = Form("tr"),
    options: Optional[str] = Form(
        None, description="book_config.json ile aynı şemada opsiyonel JSON ayarları"
    ),
    force_ocr: bool = Form(False),
):
    """Dönüştürmeyi hemen başlatmak yerine bir iş (job) kuyruğa alır ve `job_id`
    döner; sonuç `GET /convert/{job_id}/status` ile takip edilip
    `GET /convert/{job_id}/result` ile alınır. Böylece uzun süren (OCR ağırlıklı)
    dönüştürmelerde istemci ilerleme yüzdesi gösterebilir ve aynı anda gelen
    istekler `CONVERT_CONCURRENCY` sınırıyla kuyruklanır, worker tek bir büyük
    dosyayla event loop'u bloklamaz."""
    if file.filename is None or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Sadece .pdf uzantılı dosyalar kabul edilir.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Boş dosya yüklendi.")

    try:
        parsed_options = ConversionOptions.model_validate_json(options) if options else ConversionOptions()
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Geçersiz 'options' JSON: {exc}") from exc

    config = parsed_options.to_engine_config()
    if title:
        config["title"] = title
    if author:
        config["author"] = author
    if language:
        config["language"] = language

    output_name = _safe_filename(config.get("title") or Path(file.filename).stem)
    job_id = job_manager.submit(pdf_bytes, config, force_ocr, output_name)
    return {"job_id": job_id}


@app.get("/convert/{job_id}/status")
def convert_status(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="İş bulunamadı.")

    if job.status == "done":
        percent = 100.0
    elif job.total_pages:
        percent = round(min(100.0, (job.current_page / job.total_pages) * 100), 1)
    else:
        percent = 0.0

    return {
        "status": job.status,
        "current_page": job.current_page,
        "total_pages": job.total_pages,
        "percent": percent,
        "queue_position": job_manager.queue_position(job_id),
        "error": job.error,
    }


@app.get("/convert/{job_id}/result")
def convert_result(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="İş bulunamadı.")
    if job.status == "error":
        raise HTTPException(status_code=400, detail=job.error or "Dönüştürme sırasında bir hata oluştu.")
    if job.status != "done" or job.result is None:
        raise HTTPException(status_code=409, detail="Dönüştürme henüz tamamlanmadı.")

    return Response(
        content=job.result,
        media_type="application/epub+zip",
        headers={"Content-Disposition": f'attachment; filename="{job.output_name}.epub"'},
    )


@app.post("/analyze")
async def analyze_pdf_endpoint(file: UploadFile = File(..., description="Analiz edilecek PDF dosyası")):
    if file.filename is None or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Sadece .pdf uzantılı dosyalar kabul edilir.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Boş dosya yüklendi.")

    try:
        return analyze_pdf(pdf_bytes)
    except ConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Beklenmeyen analiz hatası")
        raise HTTPException(status_code=500, detail="PDF analiz edilirken beklenmeyen bir hata oluştu.")
