import { randomUUID } from 'crypto';
import {
  BadGatewayException,
  BadRequestException,
  ConflictException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { generateClientTokenFromReadWriteToken } from '@vercel/blob/client';
import { del, get } from '@vercel/blob';
import { QuotaService } from '../quota/quota.service';
import { ConverterQuotaExceededException } from '../quota/quota.exceptions';
import { ConvertPdfDto } from './dto/convert-pdf.dto';

const MAX_UPLOAD_BYTES = 100 * 1024 * 1024; // 100 MB
const UPLOAD_TOKEN_TTL_MS = 15 * 60 * 1000; // client'ın upload'ı bu süre içinde tamamlaması bekleniyor

export interface ConvertResult {
  buffer: Buffer;
  fileName: string;
}

export interface UploadTokenResult {
  clientToken: string;
  pathname: string;
}

interface UploadedBlob {
  buffer: Buffer;
  size: number;
  contentType: string | null;
}

export interface ConvertStatus {
  status: 'queued' | 'processing' | 'done' | 'error';
  currentPage: number;
  totalPages: number;
  percent: number;
  queuePosition: number;
  error: string | null;
}

interface WorkerStatusPayload {
  status: 'queued' | 'processing' | 'done' | 'error';
  current_page: number;
  total_pages: number;
  percent: number;
  queue_position: number;
  error: string | null;
}

// Worker'daki job'ın hangi kullanıcıya ait olduğunu ve kotasının serbest
// bırakılıp bırakılmadığını takip eder — worker kendi job'larını bilmiyor,
// kimlik doğrulaması da yapmıyor (bkz. apps/worker/app/jobs.py), o yüzden bu
// eşleme API katmanında (bellek içi, worker'daki job store gibi) tutuluyor.
interface PendingJob {
  userId: string;
  fileSizeBytes: number;
  released: boolean;
  createdAt: number;
}

const PENDING_JOB_TTL_MS = 2 * 60 * 60 * 1000; // 2 saat: kullanıcı hiç poll etmeden vazgeçerse kota bu sürede serbest bırakılır

@Injectable()
export class ConvertService {
  private readonly pendingJobs = new Map<string, PendingJob>();

  constructor(
    private readonly quotaService: QuotaService,
    private readonly config: ConfigService,
  ) {}

  private get workerUrl(): string {
    return this.config.get<string>('WORKER_URL') ?? 'http://127.0.0.1:3002';
  }

  private get blobToken(): string {
    return this.config.get<string>('BLOB_READ_WRITE_TOKEN')!;
  }

  private sanitizeFileName(name: string): string {
    return name.replace(/[\\/]+/g, '_').trim() || 'dosya.pdf';
  }

  // Client dosyayı bu API'nin request body'sine değil doğrudan Vercel Blob'a
  // yükleyecek (bkz. NOTES.md — Vercel Function'ların ~4.5MB inbound body
  // limiti /convert'i 10MB+ PDF'lerde 503 ile kırıyordu). Bu yüzden burada
  // dosya boyutu henüz bilinmiyor; kesin kota kontrolü (reserveConversionQuota)
  // upload tamamlanıp gerçek boyut convert() içinde öğrenildiğinde yapılır.
  // Burada sadece hızlı-başarısız olması için kullanıcının converter kotası
  // zaten tamamen dolu mu diye kaba bir ön kontrol yapılıyor.
  async createUploadToken(userId: string, fileName: string): Promise<UploadTokenResult> {
    if (!fileName.toLowerCase().endsWith('.pdf')) {
      throw new BadRequestException('Sadece .pdf uzantılı dosyalar kabul edilir.');
    }

    const usage = await this.quotaService.getUsageSummary(userId);
    if (usage.converter.limitBytes !== null && usage.converter.usedBytes >= usage.converter.limitBytes) {
      throw new ConverterQuotaExceededException(usage.converter.usedBytes, usage.converter.limitBytes, 0);
    }

    const pathname = `convert-uploads/${userId}/${randomUUID()}-${this.sanitizeFileName(fileName)}`;
    const clientToken = await generateClientTokenFromReadWriteToken({
      token: this.blobToken,
      pathname,
      allowedContentTypes: ['application/pdf'],
      maximumSizeInBytes: MAX_UPLOAD_BYTES,
      validUntil: Date.now() + UPLOAD_TOKEN_TTL_MS,
    });

    return { clientToken, pathname };
  }

  // Kullanıcının kendi upload token'ıyla yalnızca kendi `convert-uploads/{userId}/`
  // öneki altına yazabilmesi (bkz. createUploadToken) bunu tek başına garanti
  // eder, ama burada da doğrulanıyor ki bir kullanıcı başka birinin pathname'ini
  // (tahmin ederek ya da elde ederek) bu endpoint'e vermeye çalışırsa reddedilsin.
  private assertOwnedUploadPath(userId: string, pathname: string): void {
    if (!pathname.startsWith(`convert-uploads/${userId}/`)) {
      throw new ForbiddenException('Bu dosyaya erişim izniniz yok.');
    }
  }

  // Client'ın Blob'a yüklediği PDF'i okur. Bu, function'ın kendi çıkış
  // isteği (Blob storage'a) olduğu için Vercel Function'ların inbound
  // request-body limitine tabi değil — sadece function'ın kendi bellek/süre
  // sınırlarına tabi, ki bu zaten önceki multipart-upload akışında da vardı.
  // Bayt worker'a iletildikten sonra tekrar gerekmediği için geçici blob
  // en iyi çaba ile hemen siliniyor.
  private async consumeUploadedBlob(pathname: string): Promise<UploadedBlob> {
    let result;
    try {
      result = await get(pathname, { access: 'private', token: this.blobToken });
    } catch {
      throw new BadRequestException('Yüklenen dosya bulunamadı.');
    }
    if (!result || result.statusCode !== 200) {
      throw new BadRequestException('Yüklenen dosya bulunamadı.');
    }

    const arrayBuffer = await new Response(result.stream as unknown as ReadableStream).arrayBuffer();

    del(pathname, { token: this.blobToken }).catch(() => {
      // best-effort — geçici upload'ın silinmesi başarısız olsa da dönüşüm akışını bozmasın
    });

    return {
      buffer: Buffer.from(arrayBuffer),
      size: result.blob.size,
      contentType: result.blob.contentType,
    };
  }

  // Worker'a gönderilmeden önce dönüşüm kotasını rezerve eder (önce converter,
  // sonra depolama kotası kontrol edilir — QuotaService.reserveConversionQuota).
  // Worker artık dönüştürmeyi arka planda bir job olarak kuyruklayıp hemen
  // job_id döner; asıl sonuç GET :jobId/status ile takip edilip GET :jobId/result
  // ile alınır. Job kuyruğa alınamazsa (worker'a ulaşılamadı vb.) kota geri verilir;
  // job daha sonra hata ile biterse bu, getStatus içinde tespit edilip kota
  // orada geri verilir (bkz. releaseIfErrored).
  async convert(userId: string, dto: ConvertPdfDto): Promise<{ jobId: string }> {
    if (!dto.fileName.toLowerCase().endsWith('.pdf')) {
      throw new BadRequestException('Sadece .pdf uzantılı dosyalar kabul edilir.');
    }
    this.assertOwnedUploadPath(userId, dto.pathname);
    this.cleanupExpiredJobs();

    const uploaded = await this.consumeUploadedBlob(dto.pathname);
    await this.quotaService.reserveConversionQuota(userId, uploaded.size);

    try {
      const jobId = await this.startWorkerJob(uploaded, dto);
      this.pendingJobs.set(jobId, {
        userId,
        fileSizeBytes: uploaded.size,
        released: false,
        createdAt: Date.now(),
      });
      return { jobId };
    } catch (error) {
      await this.quotaService.releaseConversionQuota(userId, uploaded.size);
      throw error;
    }
  }

  async getStatus(userId: string, jobId: string): Promise<ConvertStatus> {
    const pending = this.requireOwnedJob(userId, jobId);

    let response: Response;
    try {
      response = await fetch(`${this.workerUrl}/convert/${jobId}/status`);
    } catch {
      throw new BadGatewayException('Dönüştürme servisine ulaşılamadı.');
    }

    if (response.status === 404) {
      this.pendingJobs.delete(jobId);
      throw new NotFoundException('İş bulunamadı.');
    }
    if (!response.ok) {
      throw new BadGatewayException('Dönüştürme servisinden durum alınamadı.');
    }

    const payload = (await response.json()) as WorkerStatusPayload;

    if (payload.status === 'error') {
      await this.releaseIfNeeded(jobId, pending);
    }

    return {
      status: payload.status,
      currentPage: payload.current_page,
      totalPages: payload.total_pages,
      percent: payload.percent,
      queuePosition: payload.queue_position,
      error: payload.error,
    };
  }

  async getResult(userId: string, jobId: string): Promise<ConvertResult> {
    const pending = this.requireOwnedJob(userId, jobId);

    let response: Response;
    try {
      response = await fetch(`${this.workerUrl}/convert/${jobId}/result`);
    } catch {
      throw new BadGatewayException('Dönüştürme servisine ulaşılamadı.');
    }

    if (response.status === 404) {
      this.pendingJobs.delete(jobId);
      throw new NotFoundException('İş bulunamadı.');
    }
    if (response.status === 409) {
      throw new ConflictException('Dönüştürme henüz tamamlanmadı.');
    }
    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      await this.releaseIfNeeded(jobId, pending);
      this.pendingJobs.delete(jobId);
      throw new BadRequestException(errorBody?.detail || 'Dönüştürme sırasında bir hata oluştu.');
    }

    const arrayBuffer = await response.arrayBuffer();
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const fileName = match?.[1] || 'book.epub';

    this.pendingJobs.delete(jobId);
    return { buffer: Buffer.from(arrayBuffer), fileName };
  }

  private requireOwnedJob(userId: string, jobId: string): PendingJob {
    const pending = this.pendingJobs.get(jobId);
    if (!pending) {
      throw new NotFoundException('İş bulunamadı.');
    }
    if (pending.userId !== userId) {
      throw new ForbiddenException('Bu işe erişim izniniz yok.');
    }
    return pending;
  }

  private async releaseIfNeeded(jobId: string, pending: PendingJob): Promise<void> {
    if (pending.released) {
      return;
    }
    pending.released = true;
    await this.quotaService.releaseConversionQuota(pending.userId, pending.fileSizeBytes);
  }

  // Kullanıcı sonucu hiç almadan (sekmeyi kapatma vb.) vazgeçerse job kalıcı
  // olarak bellekte kalmasın ve rezerve edilen kota sonsuza dek kilitli kalmasın diye.
  private cleanupExpiredJobs(): void {
    const now = Date.now();
    for (const [jobId, pending] of this.pendingJobs) {
      if (now - pending.createdAt > PENDING_JOB_TTL_MS) {
        if (!pending.released) {
          this.quotaService
            .releaseConversionQuota(pending.userId, pending.fileSizeBytes)
            .catch(() => {
              // best-effort — bir sonraki cleanup denemesinde tekrar denenir
            });
        }
        this.pendingJobs.delete(jobId);
      }
    }
  }

  private async startWorkerJob(uploaded: UploadedBlob, dto: ConvertPdfDto): Promise<string> {
    const formData = new FormData();
    formData.append(
      'file',
      new Blob([Uint8Array.from(uploaded.buffer)], { type: uploaded.contentType || 'application/pdf' }),
      dto.fileName,
    );
    if (dto.title) formData.append('title', dto.title);
    if (dto.author) formData.append('author', dto.author);
    formData.append('language', dto.language ?? 'tr');
    if (dto.options) formData.append('options', dto.options);
    if (dto.force_ocr !== undefined) formData.append('force_ocr', String(dto.force_ocr));

    let response: Response;
    try {
      response = await fetch(`${this.workerUrl}/convert`, {
        method: 'POST',
        body: formData,
      });
    } catch {
      throw new BadGatewayException('Dönüştürme servisine ulaşılamadı.');
    }

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      throw new BadRequestException(errorBody?.detail || 'Dönüştürme sırasında bir hata oluştu.');
    }

    const body = (await response.json()) as { job_id: string };
    return body.job_id;
  }
}
