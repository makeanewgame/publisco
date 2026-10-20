import { Logger } from '@nestjs/common';
import { MembershipTier, Subscription } from '../generated/prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { defaultQuotaData } from '../users/users.service';

// Lemon Squeezy abonelik erişiminin devam ettiğini kabul ettiğimiz durumlar.
// "cancelled" bilinçli olarak burada yok: kullanıcı iptal etse de dönem
// sonuna (ends_at) kadar erişimi sürer — tier'ı normalde gerçek
// "subscription_expired" webhook'u geldiğinde FREE'ye düşürüyoruz.
export const ACTIVE_SUBSCRIPTION_STATUSES = new Set(['active', 'on_trial']);

// subscription_expired webhook'unun ends_at'ten sonra gelmesi için tanınan pay;
// bu süre de geçmişse webhook kaybolmuş sayılır ve güvenlik ağı devreye girer.
export const LAPSED_PREMIUM_GRACE_MS = 24 * 60 * 60 * 1000;

const logger = new Logger('Membership');

// membershipTier tek başına quota limitlerini değiştirmez: bir UserQuota
// satırı varsa QuotaService.resolveLimits orayı tier sabitlerine tercih
// eder (bkz. quota.service.ts), o yüzden ikisini birlikte güncelliyoruz.
export async function setMembershipTier(prisma: PrismaService, userId: string, tier: MembershipTier): Promise<void> {
  const quotaData = defaultQuotaData(tier);
  await prisma.$transaction([
    prisma.user.update({ where: { id: userId }, data: { membershipTier: tier } }),
    prisma.userQuota.upsert({
      where: { userId },
      create: { userId, ...quotaData },
      update: quotaData,
    }),
  ]);
}

// Premium dönemi bitmiş ama tier'ı hâlâ PREMIUM olan kullanıcı mı? Son
// aboneliği aktif değil ve ends_at + LAPSED_PREMIUM_GRACE_MS geçmişse evet.
// Aboneliği olmayan PREMIUM kullanıcıya (ör. elle verilmiş) dokunulmaz.
export function isLapsedPremium(
  tier: MembershipTier,
  latest: Pick<Subscription, 'status' | 'endsAt'> | null,
  now: Date,
): boolean {
  if (tier !== MembershipTier.PREMIUM || !latest || ACTIVE_SUBSCRIPTION_STATUSES.has(latest.status)) {
    return false;
  }
  return latest.endsAt !== null && latest.endsAt.getTime() + LAPSED_PREMIUM_GRACE_MS < now.getTime();
}

// subscription_expired webhook'u hiç gelmezse (Lemon Squeezy tarafında bir
// sorun) kullanıcı süresiz premium kalırdı. API serverless çalıştığından
// periyodik bir job yerine kontrol, premium'un anlam taşıdığı her okumada
// (kota rezervasyonu/özeti, abonelik özeti) yapılır: dönem bittikten sonra
// premium limitleri hiçbir yoldan kullanılamaz. Tier düşürüldüyse true döner.
export async function downgradeLapsedPremium(prisma: PrismaService, userId: string, now = new Date()): Promise<boolean> {
  const user = await prisma.user.findUnique({ where: { id: userId }, select: { membershipTier: true } });
  if (!user || user.membershipTier !== MembershipTier.PREMIUM) {
    return false;
  }
  const latest = await prisma.subscription.findFirst({
    where: { userId },
    orderBy: { createdAt: 'desc' },
    select: { status: true, endsAt: true, lemonSqueezySubscriptionId: true },
  });
  if (!isLapsedPremium(user.membershipTier, latest, now)) {
    return false;
  }
  logger.warn(
    `subscription_expired webhook'u gelmemiş: kullanıcı ${userId} FREE'ye düşürüldü ` +
      `(subscription=${latest?.lemonSqueezySubscriptionId}, status=${latest?.status}, endsAt=${latest?.endsAt?.toISOString()})`,
  );
  await setMembershipTier(prisma, userId, MembershipTier.FREE);
  return true;
}
