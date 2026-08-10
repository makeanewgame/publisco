import { authFetch } from './authFetch';
import { WORKER_URL } from './apiConfig';

export { WORKER_URL };

export type QuotaErrorCode = 'CONVERTER_QUOTA_EXCEEDED' | 'STORAGE_QUOTA_EXCEEDED';

interface QuotaErrorPayload {
  code: QuotaErrorCode;
  message: string;
  usedBytes: number;
  limitBytes: number;
  requestedBytes: number;
}

// POST /api/convert (apps/api/src/convert) kota aşımında bu şekli döner —
// bkz. apps/api/src/quota/quota.exceptions.ts.
export class QuotaExceededError extends Error {
  code: QuotaErrorCode;
  usedBytes: number;
  limitBytes: number;
  requestedBytes: number;

  constructor(payload: QuotaErrorPayload) {
    super(payload.message);
    this.code = payload.code;
    this.usedBytes = payload.usedBytes;
    this.limitBytes = payload.limitBytes;
    this.requestedBytes = payload.requestedBytes;
  }
}

function isQuotaErrorPayload(value: unknown): value is QuotaErrorPayload {
  return (
    !!value &&
    typeof value === 'object' &&
    ((value as { code?: unknown }).code === 'CONVERTER_QUOTA_EXCEEDED' ||
      (value as { code?: unknown }).code === 'STORAGE_QUOTA_EXCEEDED')
  );
}

export interface ConvertPdfParams {
  file: File;
  title?: string;
  author?: string;
  language: string;
  options?: Record<string, unknown>;
  forceOcr?: boolean;
}

export type ConvertJobStatus = 'queued' | 'processing' | 'done' | 'error';

export interface ConvertProgress {
  status: ConvertJobStatus;
  currentPage: number;
  totalPages: number;
  percent: number;
  queuePosition: number;
  error: string | null;
}

const CONVERT_POLL_INTERVAL_MS = 1200;

// Dosya, kota kontrolünün (converter -> storage) yapıldığı API'nin
// /convert endpoint'ine gönderilir; API arka planda worker'a proxy yapar ve
// worker dönüştürmeyi bir job olarak kuyruğa alıp hemen jobId döner (bkz.
// apps/worker/app/jobs.py) — bu yüzden burada sonucu değil jobId'yi bekleriz.
async function startConvertJob(params: ConvertPdfParams, signal?: AbortSignal): Promise<string> {
  const formData = new FormData();
  formData.append('file', params.file);
  if (params.title) formData.append('title', params.title);
  if (params.author) formData.append('author', params.author);
  formData.append('language', params.language);
  if (params.options) formData.append('options', JSON.stringify(params.options));
  if (params.forceOcr !== undefined) formData.append('force_ocr', String(params.forceOcr));

  const response = await authFetch('/convert', {
    method: 'POST',
    body: formData,
    signal,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    if (isQuotaErrorPayload(errorBody)) {
      throw new QuotaExceededError(errorBody);
    }
    throw new Error(errorBody?.message || 'conversion_failed');
  }

  const body: { jobId: string } = await response.json();
  return body.jobId;
}

async function getConvertJobStatus(jobId: string, signal?: AbortSignal): Promise<ConvertProgress> {
  const response = await authFetch(`/convert/${jobId}/status`, { signal });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(errorBody?.message || 'conversion_failed');
  }
  return response.json();
}

async function getConvertJobResult(jobId: string, signal?: AbortSignal): Promise<Blob> {
  const response = await authFetch(`/convert/${jobId}/result`, { signal });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(errorBody?.message || 'conversion_failed');
  }
  return response.blob();
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      },
      { once: true },
    );
  });
}

// Job'ı başlatır, tamamlanana kadar durumunu poll'lar (her adımda onProgress
// çağrılır — sıradaki konum, işlenen sayfa/toplam sayfa ve yüzde), bitince
// EPUB'ı indirir. İşlem uzun sürebildiği için (OCR ağırlıklı PDF'ler) kullanıcıya
// tek bir "dönüştürülüyor" spinner'ı yerine gerçek ilerleme göstermek için var.
// `signal` verilirse (Cancel butonu) polling'i hemen kesip AbortError fırlatır —
// bu yalnızca istemciyi sonucu beklemekten vazgeçirir, worker'daki job'u
// durdurmaz (bkz. apps/worker/app/jobs.py — iptal endpoint'i henüz yok).
export async function convertPdf(
  params: ConvertPdfParams,
  onProgress?: (progress: ConvertProgress) => void,
  signal?: AbortSignal,
): Promise<Blob> {
  const jobId = await startConvertJob(params, signal);

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const progress = await getConvertJobStatus(jobId, signal);
    onProgress?.(progress);

    if (progress.status === 'done') {
      return getConvertJobResult(jobId, signal);
    }
    if (progress.status === 'error') {
      throw new Error(progress.error || 'conversion_failed');
    }
    await wait(CONVERT_POLL_INTERVAL_MS, signal);
  }
}

export interface DetectedChapter {
  start_page: number;
  title: string;
}

export type AnalyzeWarning = 'title' | 'author' | 'chapters';

export interface AnalyzeResult {
  title: string | null;
  author: string | null;
  chapters: DetectedChapter[];
  warnings: AnalyzeWarning[];
}

export async function analyzePdf(file: File): Promise<AnalyzeResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${WORKER_URL}/analyze`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error('analyze_failed');
  }

  return response.json();
}
