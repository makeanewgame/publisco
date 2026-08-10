-- CreateEnum
CREATE TYPE "MembershipTier" AS ENUM ('FREE', 'PREMIUM');

-- AlterTable
ALTER TABLE "users" ADD COLUMN     "convertedBytesTotal" BIGINT NOT NULL DEFAULT 0,
ADD COLUMN     "membershipTier" "MembershipTier" NOT NULL DEFAULT 'FREE';
