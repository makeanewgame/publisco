import { authFetch } from './authFetch';

export interface CheckoutSession {
  url: string;
}

export type MembershipTier = 'FREE' | 'PREMIUM';

export interface SubscriptionInfo {
  status: string;
  renewsAt: string | null;
  endsAt: string | null;
  variantId: string;
}

export interface SubscriptionSummary {
  membershipTier: MembershipTier;
  subscription: SubscriptionInfo | null;
}

export interface Invoice {
  id: string;
  status: string;
  statusFormatted: string;
  totalFormatted: string;
  billingReason: string;
  invoiceUrl: string | null;
  createdAt: string;
}

export async function createCheckoutSession(locale?: 'tr' | 'en'): Promise<CheckoutSession> {
  const response = await authFetch('/payments/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ locale }),
  });
  if (!response.ok) {
    throw new Error(`Failed to create checkout session (${response.status})`);
  }
  return response.json();
}

export async function getSubscription(): Promise<SubscriptionSummary> {
  const response = await authFetch('/payments/subscription');
  if (!response.ok) {
    throw new Error(`Failed to load subscription (${response.status})`);
  }
  return response.json();
}

export async function cancelSubscription(): Promise<SubscriptionInfo> {
  const response = await authFetch('/payments/subscription/cancel', { method: 'POST' });
  if (!response.ok) {
    throw new Error(`Failed to cancel subscription (${response.status})`);
  }
  return response.json();
}

export async function resumeSubscription(): Promise<SubscriptionInfo> {
  const response = await authFetch('/payments/subscription/resume', { method: 'POST' });
  if (!response.ok) {
    throw new Error(`Failed to resume subscription (${response.status})`);
  }
  return response.json();
}

export async function getInvoices(): Promise<Invoice[]> {
  const response = await authFetch('/payments/invoices');
  if (!response.ok) {
    throw new Error(`Failed to load invoices (${response.status})`);
  }
  return response.json();
}
