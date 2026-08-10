import { randomUUID } from 'crypto';
import { Readable } from 'stream';
import {
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { del, get, put } from '@vercel/blob';
import { PrismaService } from '../prisma/prisma.service';
import { QuotaService } from '../quota/quota.service';

export interface DownloadPayload {
  stream: Readable;
  contentType: string;
  size: number;
  fileName: string;
}

@Injectable()
export class FilesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
    private readonly quotaService: QuotaService,
  ) {}

  private get token(): string {
    return this.config.get<string>('BLOB_READ_WRITE_TOKEN')!;
  }

  private sanitizeFileName(name: string): string {
    return name.replace(/[\\/]+/g, "_").trim() || "dosya";
  }

  async upload(ownerId: string, file: Express.Multer.File) {
    const fileName = this.sanitizeFileName(file.originalname);
    const pathname = `users/${ownerId}/${randomUUID()}-${fileName}`;

    return this.quotaService.withStorageQuotaLock(ownerId, file.size, async (tx) => {
      const blob = await put(pathname, file.buffer, {
        access: 'private',
        contentType: file.mimetype || undefined,
        token: this.token,
      });

      return tx.fileAsset.create({
        data: {
          ownerId,
          fileName,
          pathname: blob.pathname,
          url: blob.url,
          contentType: file.mimetype || null,
          size: file.size,
        },
      });
    });
  }

  list(ownerId: string) {
    return this.prisma.fileAsset.findMany({
      where: { ownerId },
      orderBy: { createdAt: 'desc' },
    });
  }

  private async findOwned(ownerId: string, id: string) {
    const asset = await this.prisma.fileAsset.findUnique({ where: { id } });
    if (!asset) {
      throw new NotFoundException('Dosya bulunamadı.');
    }
    if (asset.ownerId !== ownerId) {
      throw new ForbiddenException('Bu dosyaya erişim yetkiniz yok.');
    }
    return asset;
  }

  async getDownloadPayload(ownerId: string, id: string): Promise<DownloadPayload> {
    const asset = await this.findOwned(ownerId, id);

    const result = await get(asset.pathname, {
      access: 'private',
      token: this.token,
    });

    if (!result || result.statusCode !== 200) {
      throw new NotFoundException('Dosya depoda bulunamadı.');
    }

    return {
      stream: Readable.fromWeb(result.stream as any),
      contentType: result.blob.contentType || asset.contentType || 'application/octet-stream',
      size: result.blob.size,
      fileName: asset.fileName,
    };
  }

  async remove(ownerId: string, id: string) {
    const asset = await this.findOwned(ownerId, id);
    await del(asset.pathname, { token: this.token });
    await this.prisma.fileAsset.delete({ where: { id: asset.id } });
    return { success: true };
  }

  async rename(ownerId: string, id: string, fileName: string) {
    await this.findOwned(ownerId, id);
    return this.prisma.fileAsset.update({
      where: { id },
      data: { fileName: this.sanitizeFileName(fileName) },
    });
  }
}
