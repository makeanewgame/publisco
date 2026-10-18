-- AlterEnum
ALTER TYPE "ConvertJobStatus" ADD VALUE 'CANCELLED';

-- AlterTable
ALTER TABLE "convert_jobs" ADD COLUMN     "modalCallId" TEXT;
