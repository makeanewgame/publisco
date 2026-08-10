import { MembershipTier } from '../generated/prisma/client';

export const STORAGE_QUOTA_BYTES: Record<MembershipTier, number> = {
  [MembershipTier.FREE]: 50 * 1024 * 1024, // 50MB
  [MembershipTier.PREMIUM]: 2 * 1024 * 1024 * 1024, // 2GB
};

// null = sınırsız (premium dönüşüm kotası)
export const CONVERTER_QUOTA_BYTES: Record<MembershipTier, number | null> = {
  [MembershipTier.FREE]: 200 * 1024 * 1024, // 200MB
  [MembershipTier.PREMIUM]: null,
};
