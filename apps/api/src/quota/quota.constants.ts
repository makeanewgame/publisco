import { MembershipTier } from '../generated/prisma/client';

export const STORAGE_QUOTA_BYTES: Record<MembershipTier, number> = {
  [MembershipTier.FREE]: 50 * 1024 * 1024, // 50MB
  [MembershipTier.PREMIUM]: 2 * 1024 * 1024 * 1024, // 2GB
};

export const CONVERTER_QUOTA_PAGES: Record<MembershipTier, number> = {
  [MembershipTier.FREE]: 500,
  [MembershipTier.PREMIUM]: 5000,
};
