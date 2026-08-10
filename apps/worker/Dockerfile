FROM python:3.12-slim AS base

# README.md "Sunucu Paketleri" ile senkron tutulmalı: Tesseract binary +
# LANGUAGE_MAP'teki (app/converter.py) her dil için dil paketi.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-tur \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    tesseract-ocr-fra \
    tesseract-ocr-spa \
    tesseract-ocr-ita \
    tesseract-ocr-por \
    tesseract-ocr-nld \
    tesseract-ocr-rus \
    tesseract-ocr-ara \
    tesseract-ocr-pol \
    tesseract-ocr-swe \
    tesseract-ocr-ell \
    tesseract-ocr-jpn \
    tesseract-ocr-kor \
    tesseract-ocr-chi-sim \
    tesseract-ocr-chi-tra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 1000 worker
USER worker

EXPOSE 3002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3002"]
