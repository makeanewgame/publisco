-- CreateTable
CREATE TABLE "user_quotas" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "storageQuotaBytes" BIGINT NOT NULL,
    "converterQuotaBytes" BIGINT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "user_quotas_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "user_quotas_userId_key" ON "user_quotas"("userId");

-- AddForeignKey
ALTER TABLE "user_quotas" ADD CONSTRAINT "user_quotas_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Backfill: mevcut kullanıcılar için o anki membershipTier'a karşılık gelen
-- kota değerlerini doldur (bkz. apps/api/src/quota/quota.constants.ts).
INSERT INTO "user_quotas" ("id", "userId", "storageQuotaBytes", "converterQuotaBytes", "createdAt", "updatedAt")
SELECT
    'uq_' || substr(md5(random()::text || u."id"), 1, 20),
    u."id",
    CASE u."membershipTier"
        WHEN 'FREE' THEN 52428800        -- 50MB
        WHEN 'PREMIUM' THEN 2147483648   -- 2GB
    END,
    CASE u."membershipTier"
        WHEN 'FREE' THEN 209715200       -- 200MB
        WHEN 'PREMIUM' THEN NULL         -- sınırsız
    END,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM "users" u
ON CONFLICT ("userId") DO NOTHING;
