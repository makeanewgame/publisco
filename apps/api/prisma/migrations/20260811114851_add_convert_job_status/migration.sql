-- CreateEnum
CREATE TYPE "ConvertJobStatus" AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');

-- AlterTable
-- `updatedAt` mevcut satırlar için CURRENT_TIMESTAMP ile dolduruluyor (Prisma
-- `@updatedAt` alanı client tarafında yönetiyor, DB default'u yalnızca
-- backfill için gerekli — bu tabloda az sayıda geçici satır olduğundan güvenli).
ALTER TABLE "convert_jobs" ADD COLUMN     "epubUrl" TEXT,
ADD COLUMN     "errorMessage" TEXT,
ADD COLUMN     "status" "ConvertJobStatus" NOT NULL DEFAULT 'PENDING',
ADD COLUMN     "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;
