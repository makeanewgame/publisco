"""Bellek içi dönüştürme iş kuyruğu.

`/convert` isteği artık dönüştürme bitene kadar beklemek yerine bir iş (job)
oluşturup hemen `job_id` döner; asıl dönüştürme sınırlı sayıda arka plan
thread'inde (`CONVERT_CONCURRENCY`) yürütülür, fazlası `ThreadPoolExecutor`'ın
kendi kuyruğunda bekler. İlerleme ve durum bu modüldeki `job_manager` içinde
tutulur — worker tek proses olarak çalıştığı için kalıcılık ya da proses arası
paylaşım gerekmiyor (bkz. CLAUDE.md, "Worker: FastAPI ... Port: 3002").
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional

from .converter import ConversionError, convert_pdf_to_epub

logger = logging.getLogger("worker.jobs")

CONVERT_CONCURRENCY = max(1, int(os.environ.get("CONVERT_CONCURRENCY", "2")))
JOB_TTL_SECONDS = 30 * 60  # bitmiş (done/error) job'lar bu süreden sonra bellekten temizlenir

JobStatus = str  # "queued" | "processing" | "done" | "error"


@dataclass
class ConvertJob:
    id: str
    output_name: str
    status: JobStatus = "queued"
    total_pages: int = 0
    current_page: int = 0
    result: Optional[bytes] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.monotonic)
    finished_at: Optional[float] = None


class JobManager:
    def __init__(self, max_workers: int = CONVERT_CONCURRENCY):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="convert")
        self._jobs: dict[str, ConvertJob] = {}
        self._lock = threading.Lock()

    def submit(self, pdf_bytes: bytes, config: dict[str, Any], force_ocr: bool, output_name: str) -> str:
        self._cleanup_expired()
        job = ConvertJob(id=uuid.uuid4().hex, output_name=output_name)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job.id, pdf_bytes, config, force_ocr)
        return job.id

    def get(self, job_id: str) -> Optional[ConvertJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def queue_position(self, job_id: str) -> int:
        """Job hâlâ 'queued' ise ondan önce sıraya girmiş job sayısını döner
        (0 = en yakın zamanda işlenecek olan)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                return 0
            return sum(
                1
                for other in self._jobs.values()
                if other.status == "queued" and other.created_at < job.created_at
            )

    def _run(self, job_id: str, pdf_bytes: bytes, config: dict[str, Any], force_ocr: bool) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "processing"

        def on_progress(current: int, total: int) -> None:
            with self._lock:
                j = self._jobs.get(job_id)
                if j is not None:
                    j.current_page = current
                    j.total_pages = total

        try:
            result = convert_pdf_to_epub(pdf_bytes, config, force_ocr=force_ocr, on_progress=on_progress)
        except ConversionError as exc:
            self._finish(job_id, error=str(exc))
        except Exception:
            logger.exception("Beklenmeyen dönüştürme hatası (job %s)", job_id)
            self._finish(job_id, error="Dönüştürme sırasında beklenmeyen bir hata oluştu.")
        else:
            self._finish(job_id, result=result)

    def _finish(self, job_id: str, result: Optional[bytes] = None, error: Optional[str] = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "error" if error else "done"
            job.result = result
            job.error = error
            job.finished_at = time.monotonic()

    def _cleanup_expired(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.finished_at is not None and now - job.finished_at > JOB_TTL_SECONDS
            ]
            for job_id in expired:
                del self._jobs[job_id]


job_manager = JobManager()
