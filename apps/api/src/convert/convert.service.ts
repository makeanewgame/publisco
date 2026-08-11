import { createHmac, randomUUID, timingSafeEqual } from 'crypto';
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
import { del, head } from '@vercel/blob';
import { PrismaService } from '../prisma/prisma.service';
import { QuotaService } from '../quota/quota.service';
import { ConverterQuotaExceededException } from '../quota/quota.exceptions';
import { ConvertPdfDto } from './dto/convert-pdf.dto';
import { ConvertJobStatus } from '../generated/prisma/client';

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

export interface ConvertStatus {
  status: ConvertJobStatus;
  error: string | null;
}

// Modal'daki job'ın hangi kullanıcıya ait olduğunu, durumunu ve kotasının
// serbest bırakılıp bırakılmadığını takip eder — Modal kendi job'larını
// bilmiyor, kimlik doğrulaması da yapmıyor (bkz. modal_worker/main.py), o
// yüzden bu eşleme API katmanında (DB'de, bkz. ConvertJob) tutuluyor.
type PendingJob = {
  userId: string;
  fileSizeBytes: number;
  released: boolean;
  status: ConvertJobStatus;
  epubUrl: string | null;
  errorMessage: string | null;
};

const PENDING_JOB_TTL_MS = 2 * 60 * 60 * 1000; // 2 saat: kullanıcı hiç poll etmeden vazgeçerse kota bu sürede serbest bırakılır

@Injectable()
export class ConvertService {
  constructor(
    private readonly quotaService: QuotaService,
    private readonly config: ConfigService,
    private readonly prisma: PrismaService,
  ) {}

  private get modalEndpointUrl(): string {
    return this.config.get<string>('MODAL_ENDPOINT_URL')!;
  }

  private get modalWebhookSecret(): string {
    return this.config.get<string>('MODAL_WEBHOOK_SECRET')!;
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

  // Blob'un bayt içeriğini indirmek yerine sadece metadata'sını (url, size) okur —
  // dosyanın kendisi artık bu API'ye hiç girmiyor, Modal tarafından doğrudan
  // Blob'dan indiriliyor (bkz. modal_worker/main.py — download_pdf).
  private async resolveUploadedBlob(pathname: string): Promise<{ url: string; size: number }> {
    let result;
    try {
      result = await head(pathname, { token: this.blobToken });
    } catch {
      throw new BadRequestException('Yüklenen dosya bulunamadı.');
    }
    return { url: result.url, size: result.size };
  }

  // Modal kotayı rezerve ettikten sonra çağrılır; asıl ağır işi `.spawn()` ile
  // arka plana devredip anında 202 döner (bkz. modal_worker/main.py — convert
  // web_endpoint'i). Job daha sonra webhook ile (bkz. handleModalWebhook)
  // COMPLETED/FAILED'e geçer.
  private async startModalPipeline(jobId: string, pdfUrl: string, dto: ConvertPdfDto): Promise<void> {
    let options: unknown;
    if (dto.options) {
      try {
        options = JSON.parse(dto.options);
      } catch {
        throw new BadRequestException("Geçersiz 'options' JSON.");
      }
    }

    let response: Response;
    try {
      response = await fetch(`${this.modalEndpointUrl}/convert`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.modalWebhookSecret}`,
        },
        body: JSON.stringify({
          job_id: jobId,
          pdf_url: pdfUrl,
          title: dto.title,
          author: dto.author,
          language: dto.language ?? 'tr',
          options,
          force_ocr: dto.force_ocr,
        }),
      });
    } catch {
      throw new BadGatewayException('Dönüştürme servisine ulaşılamadı.');
    }

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      throw new BadRequestException(errorBody?.detail || 'Dönüştürme başlatılamadı.');
    }
  }

  async convert(userId: string, dto: ConvertPdfDto): Promise<{ jobId: string }> {
    if (!dto.fileName.toLowerCase().endsWith('.pdf')) {
      throw new BadRequestException('Sadece .pdf uzantılı dosyalar kabul edilir.');
    }
    this.assertOwnedUploadPath(userId, dto.pathname);
    await this.cleanupExpiredJobs();

    const uploaded = await this.resolveUploadedBlob(dto.pathname);
    await this.quotaService.reserveConversionQuota(userId, uploaded.size);

    const jobId = randomUUID();
    try {
      await this.startModalPipeline(jobId, uploaded.url, dto);
      await this.prisma.convertJob.create({
        data: { id: jobId, userId, fileSizeBytes: uploaded.size },
      });
      return { jobId };
    } catch (error) {
      await this.quotaService.releaseConversionQuota(userId, uploaded.size);
      throw error;
    }
  }

  async getStatus(userId: string, jobId: string): Promise<ConvertStatus> {
    const job = await this.requireOwnedJob(userId, jobId);
    return { status: job.status, error: job.errorMessage };
  }

  async getResult(userId: string, jobId: string): Promise<ConvertResult> {
    const job = await this.requireOwnedJob(userId, jobId);

    if (job.status === 'FAILED') {
      await this.deleteJob(jobId);
      throw new BadRequestException(job.errorMessage || 'Dönüştürme sırasında bir hata oluştu.');
    }
    if (job.status !== 'COMPLETED' || !job.epubUrl) {
      throw new ConflictException('Dönüştürme henüz tamamlanmadı.');
    }

    let response: Response;
    try {
      response = await fetch(job.epubUrl, { headers: { Authorization: `Bearer ${this.blobToken}` } });
    } catch {
      throw new BadGatewayException('Sonuç dosyasına ulaşılamadı.');
    }
    if (!response.ok) {
      throw new BadGatewayException('Sonuç dosyasına ulaşılamadı.');
    }

    const arrayBuffer = await response.arrayBuffer();

    await del(job.epubUrl, { token: this.blobToken }).catch(() => {
      // best-effort — silme başarısız olsa da kullanıcı sonucu almış olur
    });
    await this.deleteJob(jobId);

    return { buffer: Buffer.from(arrayBuffer), fileName: 'book.epub' };
  }

  private async requireOwnedJob(userId: string, jobId: string): Promise<PendingJob> {
    const job = await this.prisma.convertJob.findUnique({ where: { id: jobId } });
    if (!job) {
      throw new NotFoundException('İş bulunamadı.');
    }
    if (job.userId !== userId) {
      throw new ForbiddenException('Bu işe erişim izniniz yok.');
    }
    return job;
  }

  private async deleteJob(jobId: string): Promise<void> {
    await this.prisma.convertJob.deleteMany({ where: { id: jobId } });
  }

  // `released` bayrağını DB'de koşullu olarak (yalnızca hâlâ false ise) true'ya
  // çeker; `updateMany`'ın etkilediği satır sayısı, kotayı bu çağrının gerçekten
  // serbest bırakması gerekip gerekmediğini söyler — aynı job için eşzamanlı iki
  // webhook/status isteği kotayı iki kez serbest bırakmasın diye.
  private async releaseIfNeeded(jobId: string, userId: string, fileSizeBytes: number): Promise<void> {
    const { count } = await this.prisma.convertJob.updateMany({
      where: { id: jobId, released: false },
      data: { released: true },
    });
    if (count > 0) {
      await this.quotaService.releaseConversionQuota(userId, fileSizeBytes);
    }
  }

  verifyModalWebhookSignature(rawBody: Buffer, signatureHeader: string | undefined): boolean {
    const secret = this.modalWebhookSecret;
    if (!secret || !signatureHeader) {
      return false;
    }
    const digest = createHmac('sha256', secret).update(rawBody).digest('hex');
    const expected = Buffer.from(digest, 'utf8');
    const actual = Buffer.from(signatureHeader, 'utf8');
    return expected.length === actual.length && timingSafeEqual(expected, actual);
  }

  // Modal, Vercel'in webhook yanıtı geç/hatalı dönerse (503, timeout) isteği
  // tekrar dener — `updateMany`'ın etkilediği satır sayısı 0 ise (satır zaten
  // COMPLETED/FAILED'e geçmiş) ikinci çağrı sessizce no-op olur (kotayı iki kez
  // serbest bırakmama mantığı zaten `released` bayrağıyla var, aynı
  // updateMany-count deseni status geçişine de uygulanıyor).
  async handleModalWebhook(payload: {
    job_id: string;
    status: 'COMPLETED' | 'FAILED';
    epub_url?: string;
    error?: string;
  }): Promise<void> {
    const job = await this.prisma.convertJob.findUnique({ where: { id: payload.job_id } });
    if (!job) {
      return;
    }

    const { count } = await this.prisma.convertJob.updateMany({
      where: { id: payload.job_id, status: { in: ['PENDING', 'PROCESSING'] } },
      data:
        payload.status === 'COMPLETED'
          ? { status: ConvertJobStatus.COMPLETED, epubUrl: payload.epub_url }
          : { status: ConvertJobStatus.FAILED, errorMessage: payload.error ?? 'Dönüştürme sırasında bir hata oluştu.' },
    });

    if (count > 0 && payload.status === 'FAILED') {
      await this.releaseIfNeeded(payload.job_id, job.userId, job.fileSizeBytes);
    }
  }

  // Kullanıcı sonucu hiç almadan (sekmeyi kapatma vb.) vazgeçerse job kalıcı
  // olarak DB'de kalmasın ve rezerve edilen kota sonsuza dek kilitli kalmasın diye.
  // `epubUrl` set edilmiş ama hiç alınmamış (kullanıcı hiç getResult çağırmamış)
  // süresi geçmiş job'larda Blob'daki EPUB'ı da siler — yoksa Modal'ın yüklediği
  // EPUB'lar kimse indirmezse Blob'da sonsuza dek kalır.
  private async cleanupExpiredJobs(): Promise<void> {
    const cutoff = new Date(Date.now() - PENDING_JOB_TTL_MS);
    const expired = await this.prisma.convertJob.findMany({
      where: { createdAt: { lt: cutoff } },
      select: { userId: true, fileSizeBytes: true, released: true, epubUrl: true },
    });
    for (const job of expired) {
      if (!job.released) {
        await this.quotaService.releaseConversionQuota(job.userId, job.fileSizeBytes).catch(() => {
          // best-effort — bir sonraki cleanup denemesinde tekrar denenir
        });
      }
      if (job.epubUrl) {
        await del(job.epubUrl, { token: this.blobToken }).catch(() => {
          // best-effort
        });
      }
    }
    await this.prisma.convertJob.deleteMany({ where: { createdAt: { lt: cutoff } } });
  }

  // `/analyze` — Modal'ın `/analyze` web_endpoint'ine multipart proxy (bkz.
  // modal_worker/main.py). Analiz dönüşümden önce, dosya henüz Blob'a
  // yüklenmeden çağrıldığı için burada da doğrudan bayt aktarılıyor.
  async analyze(file: Express.Multer.File): Promise<unknown> {
    const formData = new FormData();
    formData.append('file', new Blob([Uint8Array.from(file.buffer)], { type: file.mimetype }), file.originalname);

    let response: Response;
    try {
      response = await fetch(`${this.modalEndpointUrl}/analyze`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${this.modalWebhookSecret}` },
        body: formData,
      });
    } catch {
      throw new BadGatewayException('Analiz servisine ulaşılamadı.');
    }

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      throw new BadRequestException(errorBody?.detail || 'PDF analiz edilirken bir hata oluştu.');
    }

    return response.json();
  }
}
