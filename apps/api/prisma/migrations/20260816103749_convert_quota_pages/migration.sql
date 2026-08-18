-- Dönüşüm kotası bayt yerine sayfa bazlı hale geliyor (free=500, premium=5000
-- sayfa). Mevcut bayt sayaçları sayfa sayısıyla karşılaştırılamaz olduğu için
-- taşınmıyor, sıfırdan başlatılıyor.

-- users.convertedBytesTotal -> users.convertedPagesTotal
ALTER TABLE "users" DROP COLUMN "convertedBytesTotal";
ALTER TABLE "users" ADD COLUMN "convertedPagesTotal" BIGINT NOT NULL DEFAULT 0;

-- user_quotas.converterQuotaBytes -> user_quotas.converterQuotaPages
ALTER TABLE "user_quotas" DROP COLUMN "converterQuotaBytes";
ALTER TABLE "user_quotas" ADD COLUMN "converterQuotaPages" INTEGER;

-- convert_jobs: rezervasyonu geri almak için sayfa sayısı gerekiyor
ALTER TABLE "convert_jobs" ADD COLUMN "pageCount" INTEGER NOT NULL DEFAULT 0;
