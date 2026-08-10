import { authFetch } from './authFetch';

export type MembershipTier = 'FREE' | 'PREMIUM';

export interface QuotaBucketUsage {
  usedBytes: number;
  limitBytes: number | null;
}

export interface QuotaUsageSummary {
  membershipTier: MembershipTier;
  storage: QuotaBucketUsage;
  converter: QuotaBucketUsage;
}

export async function getQuota(): Promise<QuotaUsageSummary> {
  const response = await authFetch('/quota');
  if (!response.ok) {
    throw new Error(`Failed to load quota (${response.status})`);
  }
  return response.json();
}
