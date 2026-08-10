-- DropIndex
DROP INDEX "email_verification_tokens_tokenHash_key";

-- AlterTable
ALTER TABLE "email_verification_tokens" ADD COLUMN     "attempts" INTEGER NOT NULL DEFAULT 0;
