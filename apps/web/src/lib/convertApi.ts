import { put } from '@vercel/blob/client';
import { authFetch } from './authFetch';

export type QuotaErrorCode = 'CONVERTER_QUOTA_EXCEEDED' | 'STORAGE_QUOTA_EXCEEDED';

interface QuotaErrorPayload {
  code: QuotaErrorCode;
  message: string;
  unit: 'bytes' | 'pages';
  used: number;
  limit: number;
  requested: number;
}

// POST /api/convert (apps/api/src/convert) kota aşımında bu şekli döner —
// bkz. apps/api/src/quota/quota.exceptions.ts. Converter kotası sayfa,
// storage kotası bayt bazlı olduğu için `unit` alanı hangisi olduğunu belirtir.
export class QuotaExceededError extends Error {
  code: QuotaErrorCode;
  unit: 'bytes' | 'pages';
  used: number;
  limit: number;
  requested: number;

  constructor(payload: QuotaErrorPayload) {
    super(payload.message);
    this.code = payload.code;
    this.unit = payload.unit;
    this.used = payload.used;
    this.limit = payload.limit;
    this.requested = payload.requested;
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

export type ConvertJobStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export interface ConvertProgress {
  status: ConvertJobStatus;
  error: string | null;
}

const CONVERT_POLL_INTERVAL_MS = 1200;

interface UploadTokenResponse {
  clientToken: string;
  pathname: string;
}

// Dosyayı API üzerinden değil doğrudan Vercel Blob'a yükleyebilmek için
// önce buradan tek kullanımlık, süreli bir client token alınır (bkz.
// apps/api/src/convert/convert.service.ts — createUploadToken). Vercel
// Function'ların ~4.5MB'lik inbound request-body limiti yüzünden dosya
// artık hiç bu API isteğinin gövdesine girmiyor.
async function requestUploadToken(fileName: string, signal?: AbortSignal): Promise<UploadTokenResponse> {
  const response = await authFetch('/convert/upload-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fileName }),
    signal,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    if (isQuotaErrorPayload(errorBody)) {
      throw new QuotaExceededError(errorBody);
    }
    throw new Error(errorBody?.message || 'conversion_failed');
  }

  return response.json();
}

// Dosya önce doğrudan Blob'a yüklenir, sonra API'ye sadece pathname + metadata
// gönderilir; kota kontrolü (converter -> storage) API tarafında gerçek dosya
// boyutu blob'dan okunduktan sonra yapılır. API, Modal'ın dönüştürme
// pipeline'ını (bkz. modal_worker/main.py) arka planda tetikleyip hemen jobId
// döner — bu yüzden burada sonucu değil jobId'yi bekleriz.
async function startConvertJob(params: ConvertPdfParams, signal?: AbortSignal): Promise<string> {
  const { clientToken, pathname } = await requestUploadToken(params.file.name, signal);

  await put(pathname, params.file, {
    access: 'private',
    token: clientToken,
    abortSignal: signal,
  });

  const response = await authFetch('/convert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pathname,
      fileName: params.file.name,
      title: params.title,
      author: params.author,
      language: params.language,
      options: params.options ? JSON.stringify(params.options) : undefined,
      force_ocr: params.forceOcr,
    }),
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
// çağrılır — sayfa bazlı ilerleme artık takip edilmiyor, sadece PENDING/
// PROCESSING/COMPLETED/FAILED durumu; bkz. ConvertPage.tsx — belirsiz
// (indeterminate) bir "dönüştürülüyor" göstergesi olarak render edilir),
// bitince EPUB'ı indirir. `signal` verilirse (Cancel butonu) polling'i hemen
// kesip AbortError fırlatır — bu yalnızca istemciyi sonucu beklemekten
// vazgeçirir, Modal'daki pipeline'ı durdurmaz (iptal endpoint'i henüz yok).
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

    if (progress.status === 'COMPLETED') {
      return getConvertJobResult(jobId, signal);
    }
    if (progress.status === 'FAILED') {
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
  page_count: number;
}

// Dönüşümden önce, dosya seçilir seçilmez tetiklenir. `startConvertJob`daki gibi
// dosya önce doğrudan Blob'a yüklenir, API'ye sadece pathname gider — eskiden
// dosya bu isteğin gövdesine multipart olarak giriyordu, bu da Vercel
// Function'ın ~4.5MB inbound body limitine takılıp büyük PDF'lerde 503
// (ve dolayısıyla tarayıcıda yanıltıcı bir CORS hatası) üretiyordu.
export async function analyzePdf(file: File, signal?: AbortSignal): Promise<AnalyzeResult> {
  const tokenResponse = await authFetch('/convert/analyze/upload-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fileName: file.name }),
    signal,
  });
  if (!tokenResponse.ok) {
    throw new Error('analyze_failed');
  }
  const { clientToken, pathname }: UploadTokenResponse = await tokenResponse.json();

  await put(pathname, file, {
    access: 'private',
    token: clientToken,
    abortSignal: signal,
  });

  const response = await authFetch('/convert/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pathname }),
    signal,
  });

  if (!response.ok) {
    throw new Error('analyze_failed');
  }

  return response.json();
}
