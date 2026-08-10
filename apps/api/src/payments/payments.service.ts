import { Injectable, Logger, NotFoundException, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createHmac, timingSafeEqual } from 'crypto';
import {
  cancelSubscription as lemonSqueezyCancelSubscription,
  createCheckout,
  lemonSqueezySetup,
  listSubscriptionInvoices,
  updateSubscription as lemonSqueezyUpdateSubscription,
} from '@lemonsqueezy/lemonsqueezy.js';
import { PrismaService } from '../prisma/prisma.service';
import { MembershipTier, Subscription } from '../generated/prisma/client';
import { defaultQuotaData } from '../users/users.service';

export interface SubscriptionDto {
  status: string;
  renewsAt: string | null;
  endsAt: string | null;
  variantId: string;
}

export interface SubscriptionSummaryDto {
  membershipTier: MembershipTier;
  subscription: SubscriptionDto | null;
}

export interface InvoiceDto {
  id: string;
  status: string;
  statusFormatted: string;
  totalFormatted: string;
  billingReason: string;
  invoiceUrl: string | null;
  createdAt: string;
}

function toSubscriptionDto(row: Subscription): SubscriptionDto {
  return {
    status: row.status,
    renewsAt: row.renewsAt?.toISOString() ?? null,
    endsAt: row.endsAt?.toISOString() ?? null,
    variantId: row.variantId,
  };
}

interface LemonSqueezyWebhookPayload {
  meta: {
    event_name: string;
    custom_data?: Record<string, unknown>;
  };
  data: {
    id: string;
    attributes: {
      customer_id: number;
      variant_id: number;
      status: string;
      renews_at: string | null;
      ends_at: string | null;
    };
  };
}

// Lemon Squeezy abonelik erişiminin devam ettiğini kabul ettiğimiz durumlar.
// "cancelled" bilinçli olarak burada yok: kullanıcı iptal etse de dönem
// sonuna (ends_at) kadar erişimi sürer — tier'ı ancak gerçek
// "subscription_expired" webhook'u geldiğinde FREE'ye düşürüyoruz.
const ACTIVE_SUBSCRIPTION_STATUSES = new Set(['active', 'on_trial']);

@Injectable()
export class PaymentsService implements OnModuleInit {
  private readonly logger = new Logger(PaymentsService.name);

  constructor(
    private readonly config: ConfigService,
    private readonly prisma: PrismaService,
  ) {}

  onModuleInit() {
    lemonSqueezySetup({
      apiKey: this.config.get<string>('LEMONSQUEEZY_API_KEY'),
      onError: (error) => this.logger.error(`Lemon Squeezy API hatası: ${error.message}`),
    });
  }

  async createCheckoutUrl(user: { userId: string; email: string }, locale?: 'tr' | 'en'): Promise<string> {
    const storeId = this.config.get<string>('LEMONSQUEEZY_STORE_ID');
    const variantId = this.config.get<string>('LEMONSQUEEZY_PREMIUM_VARIANT_ID');

    const { data, error } = await createCheckout(storeId as string, variantId as string, {
      checkoutData: {
        email: user.email,
        custom: { user_id: user.userId },
      },
      // Frontend bu URL'i tam sayfa yönlendirme yerine Lemon.js overlay'i
      // (window.LemonSqueezy.Url.Open) ile açıyor (bkz. PremiumPage.tsx) —
      // embed:true overlay'e uygun stille dönmesini sağlıyor. locale
      // verilmezse checkout mağaza varsayılanına, sonra tarayıcı diline
      // düşer — bu da uygulamanın kendi dil seçiminden bağımsız kalabilir
      // (bkz. NOTES.md), o yüzden burada açıkça frontend'in dili geçiliyor.
      // `locale` SDK'nın CheckoutOptions tipinde henüz yok ama Lemon
      // Squeezy API'si destekliyor (bkz. checkout_options.locale, API docs).
      checkoutOptions: { embed: true, locale } as { embed: boolean; locale?: string },
    });

    if (error || !data) {
      throw new Error(`Lemon Squeezy checkout oluşturulamadı: ${error?.message}`);
    }

    return data.data.attributes.url;
  }

  async getSubscriptionSummary(userId: string): Promise<SubscriptionSummaryDto> {
    const [user, subscription] = await Promise.all([
      this.prisma.user.findUniqueOrThrow({ where: { id: userId }, select: { membershipTier: true } }),
      this.findLatestSubscription(userId),
    ]);
    return {
      membershipTier: user.membershipTier,
      subscription: subscription ? toSubscriptionDto(subscription) : null,
    };
  }

  async cancelSubscription(userId: string): Promise<SubscriptionDto> {
    const subscription = await this.findLatestSubscription(userId);
    if (!subscription) {
      throw new NotFoundException('Aktif bir abonelik bulunamadı.');
    }

    const { data, error } = await lemonSqueezyCancelSubscription(subscription.lemonSqueezySubscriptionId);
    if (error || !data) {
      throw new Error(`Abonelik iptal edilemedi: ${error?.message}`);
    }

    return toSubscriptionDto(await this.syncSubscriptionFromApi(subscription.id, data.data.attributes));
  }

  async resumeSubscription(userId: string): Promise<SubscriptionDto> {
    const subscription = await this.findLatestSubscription(userId);
    if (!subscription) {
      throw new NotFoundException('Aktif bir abonelik bulunamadı.');
    }

    const { data, error } = await lemonSqueezyUpdateSubscription(subscription.lemonSqueezySubscriptionId, {
      cancelled: false,
    });
    if (error || !data) {
      throw new Error(`Abonelik devam ettirilemedi: ${error?.message}`);
    }

    return toSubscriptionDto(await this.syncSubscriptionFromApi(subscription.id, data.data.attributes));
  }

  async listInvoices(userId: string): Promise<InvoiceDto[]> {
    const subscription = await this.findLatestSubscription(userId);
    if (!subscription) {
      return [];
    }

    const { data, error } = await listSubscriptionInvoices({
      filter: { subscriptionId: subscription.lemonSqueezySubscriptionId },
    });
    if (error || !data) {
      throw new Error(`Faturalar alınamadı: ${error?.message}`);
    }

    return data.data.map((invoice) => ({
      id: invoice.id,
      status: invoice.attributes.status,
      statusFormatted: invoice.attributes.status_formatted,
      totalFormatted: invoice.attributes.total_formatted,
      billingReason: invoice.attributes.billing_reason,
      invoiceUrl: invoice.attributes.urls.invoice_url,
      createdAt: invoice.attributes.created_at,
    }));
  }

  private findLatestSubscription(userId: string) {
    return this.prisma.subscription.findFirst({ where: { userId }, orderBy: { createdAt: 'desc' } });
  }

  // Cancel/resume çağrısının sonucunu webhook'u beklemeden hemen yerel satıra
  // yazar: local dev'de tünel yoksa webhook hiç gelmeyebilir, prod'da da
  // kullanıcı butona bastığı anda güncel durumu görmeli.
  private syncSubscriptionFromApi(
    subscriptionRowId: string,
    attrs: { status: string; renews_at: string | null; ends_at: string | null },
  ) {
    return this.prisma.subscription.update({
      where: { id: subscriptionRowId },
      data: {
        status: attrs.status,
        renewsAt: attrs.renews_at ? new Date(attrs.renews_at) : null,
        endsAt: attrs.ends_at ? new Date(attrs.ends_at) : null,
      },
    });
  }

  verifyWebhookSignature(rawBody: Buffer, signatureHeader: string | undefined): boolean {
    const secret = this.config.get<string>('LEMONSQUEEZY_WEBHOOK_SECRET');
    if (!secret || !signatureHeader) {
      return false;
    }
    const digest = createHmac('sha256', secret).update(rawBody).digest('hex');
    const expected = Buffer.from(digest, 'utf8');
    const actual = Buffer.from(signatureHeader, 'utf8');
    return expected.length === actual.length && timingSafeEqual(expected, actual);
  }

  async handleWebhookEvent(payload: LemonSqueezyWebhookPayload): Promise<void> {
    const eventName = payload.meta.event_name;
    if (!eventName.startsWith('subscription_')) {
      // order_* / license_key_* gibi diğer event'lerle şimdilik ilgilenmiyoruz.
      return;
    }

    const attrs = payload.data.attributes;
    const subscriptionId = payload.data.id;
    const customerId = String(attrs.customer_id);
    const customUserId = payload.meta.custom_data?.user_id;

    const user =
      typeof customUserId === 'string'
        ? await this.prisma.user.findUnique({ where: { id: customUserId } })
        : await this.prisma.user.findFirst({ where: { lemonSqueezyCustomerId: customerId } });

    if (!user) {
      this.logger.warn(`${eventName} için kullanıcı bulunamadı (subscription=${subscriptionId})`);
      return;
    }

    await this.prisma.subscription.upsert({
      where: { lemonSqueezySubscriptionId: subscriptionId },
      create: {
        userId: user.id,
        lemonSqueezySubscriptionId: subscriptionId,
        variantId: String(attrs.variant_id),
        status: attrs.status,
        renewsAt: attrs.renews_at ? new Date(attrs.renews_at) : null,
        endsAt: attrs.ends_at ? new Date(attrs.ends_at) : null,
      },
      update: {
        status: attrs.status,
        renewsAt: attrs.renews_at ? new Date(attrs.renews_at) : null,
        endsAt: attrs.ends_at ? new Date(attrs.ends_at) : null,
      },
    });

    if (!user.lemonSqueezyCustomerId) {
      await this.prisma.user.update({
        where: { id: user.id },
        data: { lemonSqueezyCustomerId: customerId },
      });
    }

    if (eventName === 'subscription_expired') {
      await this.setMembershipTier(user.id, MembershipTier.FREE);
    } else if (ACTIVE_SUBSCRIPTION_STATUSES.has(attrs.status)) {
      await this.setMembershipTier(user.id, MembershipTier.PREMIUM);
    }
  }

  // membershipTier tek başına quota limitlerini değiştirmez: bir UserQuota
  // satırı varsa QuotaService.resolveLimits orayı tier sabitlerine tercih
  // eder (bkz. quota.service.ts), o yüzden ikisini birlikte güncelliyoruz.
  private async setMembershipTier(userId: string, tier: MembershipTier): Promise<void> {
    const quotaData = defaultQuotaData(tier);
    await this.prisma.$transaction([
      this.prisma.user.update({ where: { id: userId }, data: { membershipTier: tier } }),
      this.prisma.userQuota.upsert({
        where: { userId },
        create: { userId, ...quotaData },
        update: quotaData,
      }),
    ]);
  }
}
