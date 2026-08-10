import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { useLocale } from '../i18n';
import { getQuota, type QuotaUsageSummary } from '../lib/quotaApi';
import { createCheckoutSession } from '../lib/paymentsApi';

declare global {
  interface Window {
    createLemonSqueezy?: () => void;
    LemonSqueezy?: {
      Setup: (options: { eventHandler: (event: { event: string }) => void }) => void;
      Url: { Open: (url: string) => void; Close: () => void };
    };
  }
}

const LEMON_SQUEEZY_SCRIPT_SRC = 'https://app.lemonsqueezy.com/js/lemon.js';

export default function PremiumPage() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const [quota, setQuota] = useState<QuotaUsageSummary | null>(null);
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [isLemonLoaded, setIsLemonLoaded] = useState(false);
  const [checkoutSucceeded, setCheckoutSucceeded] = useState(false);
  const isSignedIn = Boolean(localStorage.getItem('accessToken'));

  useEffect(() => {
    if (!isSignedIn) {
      return;
    }
    getQuota()
      .then(setQuota)
      .catch(() => {
        // Sayfa üyelik durumu olmadan da görüntülenebilir; sessizce yut.
      });
  }, [isSignedIn]);

  // Checkout'u tam sayfa yönlendirme yerine Lemon.js overlay'i içinde açmak
  // için (bkz. handleUpgrade) — kullanıcı sitede kalır.
  useEffect(() => {
    const script = document.createElement('script');
    script.src = LEMON_SQUEEZY_SCRIPT_SRC;
    script.defer = true;
    script.onload = () => setIsLemonLoaded(true);
    document.body.appendChild(script);
    return () => {
      document.body.removeChild(script);
    };
  }, []);

  useEffect(() => {
    if (!isLemonLoaded) {
      return;
    }
    // Ödeme overlay içinde tamamlanıyor; membershipTier'ın asıl güncellemesi
    // webhook üzerinden gelir (bkz. payments.service.ts) — bu sadece anlık
    // kullanıcı geri bildirimi için.
    window.LemonSqueezy?.Setup({
      eventHandler: (event) => {
        if (event.event === 'Checkout.Success') {
          setCheckoutSucceeded(true);
        }
      },
    });
  }, [isLemonLoaded]);

  const isPremium = quota?.membershipTier === 'PREMIUM';

  async function handleUpgrade() {
    if (!isSignedIn) {
      navigate('/auth/signin');
      return;
    }
    setIsCheckingOut(true);
    try {
      const { url } = await createCheckoutSession();
      window.createLemonSqueezy?.();
      window.LemonSqueezy?.Url.Open(url);
    } catch {
      // Checkout oluşturulamadıysa kullanıcıyı butonla tekrar denemeye bırak.
    } finally {
      setIsCheckingOut(false);
    }
  }

  return (
    <main>
      <div className="mx-auto flex max-w-4xl flex-col gap-6 rounded-[36px] border border-[#e8d9c4] bg-[#fffdf8] p-8 shadow-[0_20px_70px_rgba(36,28,21,0.08)] lg:p-10 my-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{t('premium.title')}</h1>
          <p className="mt-2 text-sm leading-7 text-[#6e6257]">{t('premium.subtitle')}</p>
        </div>

        {isPremium && (
          <div className="rounded-2xl border border-[#a6f4dc] bg-[#ecfdf7] px-4 py-3 text-sm text-[#0e614c]">
            {t('premium.alreadyPremium')}
          </div>
        )}

        {checkoutSucceeded && (
          <div className="rounded-2xl border border-[#a6f4dc] bg-[#ecfdf7] px-4 py-3 text-sm text-[#0e614c]">
            {t('premium.checkoutSuccess')}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-[24px] border border-[#ead8c6] bg-[#fff8ee] p-6">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#9b8b7e]">{t('premium.freeTier')}</p>
            <p className="mt-1 text-2xl font-semibold text-[#241c15]">{t('premium.freePrice')}</p>
            <ul className="mt-4 flex flex-col gap-2 text-sm text-[#5f544b]">
              <li>{t('premium.freeStorage')}</li>
              <li>{t('premium.freeConverter')}</li>
            </ul>
          </div>

          <div className="relative rounded-[24px] border-2 border-[#14b78c] bg-[#ecfdf7] p-6">
            <span className="absolute -top-3 right-6 rounded-full bg-[#14b78c] px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white">
              {t('premium.recommended')}
            </span>
            <p className="text-xs font-semibold uppercase tracking-wide text-[#0c7a5e]">{t('premium.premiumTier')}</p>
            <p className="mt-1 text-2xl font-semibold text-[#0e614c]">{t('premium.premiumPrice')}</p>
            <ul className="mt-4 flex flex-col gap-2 text-sm text-[#0e614c]">
              <li>{t('premium.premiumStorage')}</li>
              <li>{t('premium.premiumConverter')}</li>
            </ul>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <Button
            onClick={handleUpgrade}
            disabled={isPremium || isCheckingOut || (isSignedIn && !isLemonLoaded)}
            className="rounded-full bg-mint px-6 py-3 text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isCheckingOut
              ? t('premium.upgradeCtaLoading')
              : !isSignedIn
                ? t('premium.signInToUpgrade')
                : t('premium.upgradeCta')}
          </Button>
          <Link to="/convert">
            <Button className="rounded-full border-2 border-mint bg-transparent px-6 py-3 text-mint hover:bg-mint-pale">
              {t('premium.backToConvert')}
            </Button>
          </Link>
        </div>
      </div>
    </main>
  );
}
