import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { useLocale } from '../i18n';
import {
  cancelSubscription,
  getInvoices,
  getSubscription,
  resumeSubscription,
  type Invoice,
  type SubscriptionSummary,
} from '../lib/paymentsApi';

export default function AccountPage() {
  const { locale, t } = useLocale();
  const [summary, setSummary] = useState<SubscriptionSummary | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(true);
  const [summaryError, setSummaryError] = useState('');

  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [isLoadingInvoices, setIsLoadingInvoices] = useState(true);
  const [invoicesError, setInvoicesError] = useState('');

  const [isActionPending, setIsActionPending] = useState(false);
  const [actionError, setActionError] = useState('');

  const dateFormatter = new Intl.DateTimeFormat(locale === 'tr' ? 'tr-TR' : 'en-US', { dateStyle: 'medium' });

  useEffect(() => {
    getSubscription()
      .then(setSummary)
      .catch(() => setSummaryError(t('account.loadError')))
      .finally(() => setIsLoadingSummary(false));

    getInvoices()
      .then(setInvoices)
      .catch(() => setInvoicesError(t('account.invoicesLoadError')))
      .finally(() => setIsLoadingInvoices(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const subscription = summary?.subscription ?? null;
  const isCancelled = subscription?.status === 'cancelled';

  async function handleCancel() {
    setActionError('');
    setIsActionPending(true);
    try {
      const updated = await cancelSubscription();
      setSummary((prev) => (prev ? { ...prev, subscription: updated } : prev));
    } catch {
      setActionError(t('account.cancelError'));
    } finally {
      setIsActionPending(false);
    }
  }

  async function handleResume() {
    setActionError('');
    setIsActionPending(true);
    try {
      const updated = await resumeSubscription();
      setSummary((prev) => (prev ? { ...prev, subscription: updated } : prev));
    } catch {
      setActionError(t('account.resumeError'));
    } finally {
      setIsActionPending(false);
    }
  }

  return (
    <main>
      <div className="mx-auto flex max-w-4xl flex-col gap-6 rounded-[36px] border border-[#e8d9c4] bg-[#fffdf8] p-8 shadow-[0_20px_70px_rgba(36,28,21,0.08)] lg:p-10 my-8">
        <h1 className="text-3xl font-semibold tracking-tight">{t('account.title')}</h1>

        <div className="rounded-[24px] border border-[#e8d9c4] bg-[#fff8ee] p-6">
          {isLoadingSummary ? (
            <p className="text-sm text-[#6e6257]">{t('account.loading')}</p>
          ) : summaryError ? (
            <p className="text-sm text-red-600">{summaryError}</p>
          ) : (
            <div className="flex flex-col gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-[#9b8b7e]">{t('account.planLabel')}</p>
                <p className="mt-1 text-2xl font-semibold text-[#241c15]">
                  {summary?.membershipTier === 'PREMIUM' ? t('account.premiumLabel') : t('account.freeLabel')}
                </p>
              </div>

              {subscription && (
                <p className="text-sm text-[#6e6257]">
                  {isCancelled
                    ? subscription.endsAt &&
                      t('account.cancelledNotice', { date: dateFormatter.format(new Date(subscription.endsAt)) })
                    : subscription.renewsAt &&
                      t('account.renewsOn', { date: dateFormatter.format(new Date(subscription.renewsAt)) })}
                </p>
              )}

              {!subscription && summary?.membershipTier === 'FREE' && (
                <Link to="/premium">
                  <Button className="w-fit rounded-full bg-mint px-6 py-3 text-white">{t('account.noSubscriptionCta')}</Button>
                </Link>
              )}

              {actionError && <p className="text-sm text-red-600">{actionError}</p>}

              {subscription && (
                <div>
                  {isCancelled ? (
                    <Button
                      onClick={handleResume}
                      disabled={isActionPending}
                      className="w-fit rounded-full bg-mint px-6 py-3 text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isActionPending ? t('account.resuming') : t('account.resumeCta')}
                    </Button>
                  ) : (
                    <Button
                      onClick={handleCancel}
                      disabled={isActionPending}
                      className="w-fit rounded-full border-2 border-[#e8d9c4] bg-transparent px-6 py-3 text-[#6e6257] hover:bg-[#f5e8da] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isActionPending ? t('account.cancelling') : t('account.cancelCta')}
                    </Button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-4">
          <h2 className="text-xl font-semibold tracking-tight">{t('account.invoicesTitle')}</h2>
          <div className="rounded-[24px] border border-[#e8d9c4] bg-[#fff8ee] p-6">
            {isLoadingInvoices ? (
              <p className="text-sm text-[#6e6257]">{t('account.loading')}</p>
            ) : invoicesError ? (
              <p className="text-sm text-red-600">{invoicesError}</p>
            ) : invoices.length === 0 ? (
              <p className="text-sm text-[#6e6257]">{t('account.invoicesEmpty')}</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {invoices.map((invoice) => (
                  <li
                    key={invoice.id}
                    className="flex flex-col gap-3 rounded-[20px] border border-[#ead8c6] bg-[#fffdf8] p-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <p className="text-sm font-medium text-[#241c15]">{dateFormatter.format(new Date(invoice.createdAt))}</p>
                      <p className="text-xs text-[#9b8b7e]">
                        {invoice.totalFormatted} • {invoice.statusFormatted}
                      </p>
                    </div>
                    {invoice.invoiceUrl && (
                      <a
                        href={invoice.invoiceUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="w-fit rounded-full border border-[#ead8c6] bg-[#fffdf8] px-4 py-2 text-sm text-[#241c15] hover:bg-[#fff5e9]"
                      >
                        {t('account.viewInvoice')}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
