import { Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { MembershipTier, Prisma } from '../generated/prisma/client';
import { CONVERTER_QUOTA_PAGES, STORAGE_QUOTA_BYTES } from './quota.constants';
import {
  ConverterQuotaExceededException,
  StorageQuotaExceededException,
} from './quota.exceptions';

export interface QuotaBucketUsage {
  usedBytes: number;
  limitBytes: number | null;
}

export interface QuotaPageUsage {
  usedPages: number;
  limitPages: number;
}

export interface QuotaUsageSummary {
  membershipTier: MembershipTier;
  storage: QuotaBucketUsage;
  converter: QuotaPageUsage;
}

@Injectable()
export class QuotaService {
  constructor(private readonly prisma: PrismaService) {}

  private async getStorageUsedBytes(
    ownerId: string,
    client: Pick<PrismaService, 'fileAsset'> = this.prisma,
  ): Promise<number> {
    const agg = await client.fileAsset.aggregate({
      where: { ownerId },
      _sum: { size: true },
    });
    return agg._sum.size ?? 0;
  }

  async getUsageSummary(userId: string): Promise<QuotaUsageSummary> {
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      select: { membershipTier: true, convertedPagesTotal: true, quota: true },
    });
    if (!user) {
      throw new NotFoundException('Kullanıcı bulunamadı.');
    }

    const storageUsedBytes = await this.getStorageUsedBytes(userId);
    const { storageQuotaBytes, converterQuotaPages } = this.resolveLimits(user);

    return {
      membershipTier: user.membershipTier,
      storage: {
        usedBytes: storageUsedBytes,
        limitBytes: storageQuotaBytes,
      },
      converter: {
        usedPages: Number(user.convertedPagesTotal),
        limitPages: converterQuotaPages,
      },
    };
  }

  // `UserQuota` satırı olmayan (ör. migration'dan önce oluşmuş) kullanıcılar için
  // tier'a göre varsayılan sabitlere düşer.
  private resolveLimits(user: {
    membershipTier: MembershipTier;
    quota: { storageQuotaBytes: bigint; converterQuotaPages: number | null } | null;
  }): { storageQuotaBytes: number; converterQuotaPages: number } {
    if (user.quota) {
      return {
        storageQuotaBytes: Number(user.quota.storageQuotaBytes),
        converterQuotaPages: user.quota.converterQuotaPages ?? CONVERTER_QUOTA_PAGES[user.membershipTier],
      };
    }
    return {
      storageQuotaBytes: STORAGE_QUOTA_BYTES[user.membershipTier],
      converterQuotaPages: CONVERTER_QUOTA_PAGES[user.membershipTier],
    };
  }

  // Bir dönüştürme isteğinden önce çağrılır. Önce dönüşüm (converter) kotasını
  // (sayfa bazlı), ardından depolama kotasını (bayt bazlı) kontrol eder; ikisi
  // de uygunsa converter kotasını rezerve eder (sayaç artırılır). Worker'a
  // giden istek başarısız olursa releaseConversionQuota ile geri alınmalıdır.
  async reserveConversionQuota(userId: string, fileSizeBytes: number, pageCount: number): Promise<void> {
    await this.prisma.$transaction(async (tx) => {
      // "users" satırı kilitleniyor (convertedPagesTotal'a yazacağız); user_quotas
      // sadece okunuyor, o yüzden join'e FOR UPDATE gerekmiyor.
      const rows = await tx.$queryRaw<
        {
          membershipTier: MembershipTier;
          convertedPagesTotal: bigint;
          storageQuotaBytes: bigint | null;
          converterQuotaPages: number | null;
        }[]
      >`SELECT u."membershipTier", u."convertedPagesTotal",
               q."storageQuotaBytes", q."converterQuotaPages"
        FROM "users" u
        LEFT JOIN "user_quotas" q ON q."userId" = u."id"
        WHERE u."id" = ${userId} FOR UPDATE OF u`;

      const user = rows[0];
      if (!user) {
        throw new NotFoundException('Kullanıcı bulunamadı.');
      }

      const { storageQuotaBytes, converterQuotaPages } = this.resolveLimits({
        membershipTier: user.membershipTier,
        quota:
          user.storageQuotaBytes === null
            ? null
            : { storageQuotaBytes: user.storageQuotaBytes, converterQuotaPages: user.converterQuotaPages },
      });

      const converterUsed = Number(user.convertedPagesTotal);
      if (converterUsed + pageCount > converterQuotaPages) {
        throw new ConverterQuotaExceededException(converterUsed, converterQuotaPages, pageCount);
      }

      const storageUsed = await this.getStorageUsedBytes(userId, tx);
      if (storageUsed + fileSizeBytes > storageQuotaBytes) {
        throw new StorageQuotaExceededException(storageUsed, storageQuotaBytes, fileSizeBytes);
      }

      await tx.user.update({
        where: { id: userId },
        data: { convertedPagesTotal: { increment: pageCount } },
      });
    });
  }

  // Bir dosya yüklemesinden önce çağrılır (converter kotasını etkilemez).
  // Depolama kullanımı FileAsset satırlarından canlı hesaplandığı için ayrı bir
  // sayaç rezervasyonu yok; users satırını kilitleyip aynı transaction içinde
  // tekrar hesaplayarak eşzamanlı yüklemelerdeki yarış durumunu daraltıyoruz.
  //
  // `fn` (asıl blob upload + FileAsset.create) bilerek aynı transaction içinde,
  // FOR UPDATE kilidi altında çalıştırılıyor: kilit yalnızca kontrol sırasında
  // tutulup bırakılsaydı, iki eşzamanlı yükleme teorik olarak ikisi de kontrolü
  // geçip kotayı aşabilirdi (asıl yazı transaction dışındaydı). Kilidi blob
  // put() süresince de tutmak bunu kapatıyor; bedeli aynı kullanıcının
  // eşzamanlı yüklemelerinin serileşmesi (başka kullanıcıları etkilemez) — bu
  // yüzden timeout'u varsayılan 5s'in üzerine, ağ gecikmesine yer bırakacak
  // şekilde çıkarıyoruz.
  async withStorageQuotaLock<T>(
    userId: string,
    fileSizeBytes: number,
    fn: (tx: Prisma.TransactionClient) => Promise<T>,
  ): Promise<T> {
    return this.prisma.$transaction(
      async (tx) => {
        const rows = await tx.$queryRaw<
          {
            membershipTier: MembershipTier;
            storageQuotaBytes: bigint | null;
            converterQuotaPages: number | null;
          }[]
        >`SELECT u."membershipTier",
               q."storageQuotaBytes", q."converterQuotaPages"
        FROM "users" u
        LEFT JOIN "user_quotas" q ON q."userId" = u."id"
        WHERE u."id" = ${userId} FOR UPDATE OF u`;

        const user = rows[0];
        if (!user) {
          throw new NotFoundException('Kullanıcı bulunamadı.');
        }

        const { storageQuotaBytes } = this.resolveLimits({
          membershipTier: user.membershipTier,
          quota:
            user.storageQuotaBytes === null
              ? null
              : { storageQuotaBytes: user.storageQuotaBytes, converterQuotaPages: user.converterQuotaPages },
        });

        const storageUsed = await this.getStorageUsedBytes(userId, tx);
        if (storageUsed + fileSizeBytes > storageQuotaBytes) {
          throw new StorageQuotaExceededException(storageUsed, storageQuotaBytes, fileSizeBytes);
        }

        return fn(tx);
      },
      { timeout: 20000 },
    );
  }

  // Rezerve edilmiş dönüşüm kotasını (sayfa) geri verir (worker isteği başarısız olduğunda).
  async releaseConversionQuota(userId: string, pageCount: number): Promise<void> {
    await this.prisma.user.update({
      where: { id: userId },
      data: { convertedPagesTotal: { decrement: pageCount } },
    });
  }
}
