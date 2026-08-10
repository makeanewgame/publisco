import json
import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _poll_until_finished(job_id: str, timeout: float = 10.0) -> dict:
    """`/convert` artık senkron sonuç yerine bir job kuyruklayıp 202 döner
    (bkz. app/jobs.py); dönüştürme ayrı bir arka plan thread'inde yürütülür.
    Testler gerçek istemcinin yaptığı gibi durumu poll'layıp bitmesini bekler."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/convert/{job_id}/status")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} {timeout} saniye içinde bitmedi")


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_convert_returns_epub_file(sample_pdf_bytes):
    response = client.post(
        "/convert",
        files={"file": ("kitap.pdf", sample_pdf_bytes, "application/pdf")},
        data={"title": "Test Kitap", "author": "Test Yazar"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status = _poll_until_finished(job_id)
    assert status["status"] == "done"

    result = client.get(f"/convert/{job_id}/result")
    assert result.status_code == 200
    assert result.headers["content-type"] == "application/epub+zip"
    assert "Test Kitap.epub" in result.headers["content-disposition"]
    assert result.content[:4] == b"PK\x03\x04"


def test_convert_accepts_options_json(sample_pdf_bytes):
    options = json.dumps({"chapters": [{"start_page": 1, "title": "Bolum 1"}]})
    response = client.post(
        "/convert",
        files={"file": ("kitap.pdf", sample_pdf_bytes, "application/pdf")},
        data={"title": "Test", "options": options},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status = _poll_until_finished(job_id)
    assert status["status"] == "done"


def test_convert_rejects_non_pdf_filename(sample_pdf_bytes):
    response = client.post(
        "/convert",
        files={"file": ("kitap.txt", sample_pdf_bytes, "text/plain")},
        data={"title": "Test"},
    )
    assert response.status_code == 400


def test_convert_rejects_empty_file():
    response = client.post(
        "/convert",
        files={"file": ("kitap.pdf", b"", "application/pdf")},
        data={"title": "Test"},
    )
    assert response.status_code == 400


def test_convert_rejects_corrupt_pdf(corrupt_pdf_bytes):
    response = client.post(
        "/convert",
        files={"file": ("kitap.pdf", corrupt_pdf_bytes, "application/pdf")},
        data={"title": "Test"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status = _poll_until_finished(job_id)
    assert status["status"] == "error"

    result = client.get(f"/convert/{job_id}/result")
    assert result.status_code == 400


def test_convert_rejects_invalid_options_json(sample_pdf_bytes):
    response = client.post(
        "/convert",
        files={"file": ("kitap.pdf", sample_pdf_bytes, "application/pdf")},
        data={"title": "Test", "options": "{not valid json"},
    )
    assert response.status_code == 400


def test_analyze_returns_detected_fields(pdf_with_metadata_bytes):
    response = client.post(
        "/analyze",
        files={"file": ("kitap.pdf", pdf_with_metadata_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Metadata Basligi"
    assert body["author"] == "Metadata Yazari"
    assert body["chapters"] == []
    assert body["warnings"] == ["chapters"]


def test_analyze_rejects_non_pdf_filename(sample_pdf_bytes):
    response = client.post(
        "/analyze",
        files={"file": ("kitap.txt", sample_pdf_bytes, "text/plain")},
    )
    assert response.status_code == 400


def test_analyze_rejects_empty_file():
    response = client.post(
        "/analyze",
        files={"file": ("kitap.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400


def test_analyze_rejects_corrupt_pdf(corrupt_pdf_bytes):
    response = client.post(
        "/analyze",
        files={"file": ("kitap.pdf", corrupt_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 400
