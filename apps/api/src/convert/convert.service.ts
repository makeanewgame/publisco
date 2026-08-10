import {
  BadGatewayException,
  BadRequestException,
  ConflictException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { QuotaService } from '../quota/quota.service';
import { ConvertPdfDto } from './dto/convert-pdf.dto';

export interface ConvertResult {
  buffer: Buffer;
  fileName: string;
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

  // Worker'a gönderilmeden önce dönüşüm kotasını rezerve eder (önce converter,
  // sonra depolama kotası kontrol edilir — QuotaService.reserveConversionQuota).
  // Worker artık dönüştürmeyi arka planda bir job olarak kuyruklayıp hemen
  // job_id döner; asıl sonuç GET :jobId/status ile takip edilip GET :jobId/result
  // ile alınır. Job kuyruğa alınamazsa (worker'a ulaşılamadı vb.) kota geri verilir;
  // job daha sonra hata ile biterse bu, getStatus içinde tespit edilip kota
  // orada geri verilir (bkz. releaseIfErrored).
  async convert(userId: string, file: Express.Multer.File, dto: ConvertPdfDto): Promise<{ jobId: string }> {
    if (!file) {
      throw new BadRequestException('Dönüştürülecek dosya bulunamadı.');
    }
    if (!file.originalname.toLowerCase().endsWith('.pdf')) {
      throw new BadRequestException('Sadece .pdf uzantılı dosyalar kabul edilir.');
    }

    this.cleanupExpiredJobs();
    await this.quotaService.reserveConversionQuota(userId, file.size);

    try {
      const jobId = await this.startWorkerJob(file, dto);
      this.pendingJobs.set(jobId, {
        userId,
        fileSizeBytes: file.size,
        released: false,
        createdAt: Date.now(),
      });
      return { jobId };
    } catch (error) {
      await this.quotaService.releaseConversionQuota(userId, file.size);
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

  private async startWorkerJob(file: Express.Multer.File, dto: ConvertPdfDto): Promise<string> {
    const formData = new FormData();
    formData.append(
      'file',
      new Blob([Uint8Array.from(file.buffer)], { type: file.mimetype || 'application/pdf' }),
      file.originalname,
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
