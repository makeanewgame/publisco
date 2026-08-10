import { useEffect, useState } from 'react';
import { useDispatch } from 'react-redux';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Logo } from '../components/Logo';
import { useLocale } from '../i18n';
import { useTheme } from '../theme';
import { navPillClass } from '../lib/themeClasses';
import { useVerifyEmailMutation, useResendVerificationMutation } from '../app/services/authApi';
import { setCredentials } from '../app/authSlice';

const RESEND_COOLDOWN_SECONDS = 60;

export default function VerifyEmailPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { locale, setLocale, t } = useLocale();
  const { theme } = useTheme();
  const email = (location.state as { email?: string } | null)?.email ?? '';

  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  const [verifyEmail] = useVerifyEmailMutation();
  const [resendVerification] = useResendVerificationMutation();

  useEffect(() => {
    if (!email) {
      navigate('/auth/signup');
    }
  }, [email, navigate]);

  useEffect(() => {
    if (cooldown === 0) return;
    const timer = setInterval(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!/^\d{6}$/.test(code)) {
      setError(t('verifyEmail.errorCodeFormat'));
      return;
    }

    setLoading(true);
    try {
      const response = await verifyEmail({ email, code }).unwrap();
      dispatch(setCredentials(response));
      setSuccess(true);
      setTimeout(() => navigate('/'), 2000);
    } catch (err: any) {
      setError(err.data?.message || t('verifyEmail.errorGeneric'));
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError('');
    try {
      await resendVerification({ email }).unwrap();
      setCooldown(RESEND_COOLDOWN_SECONDS);
    } catch {
      setError(t('verifyEmail.errorGeneric'));
    }
  };

  return (
    <main>
      <div className="mx-auto flex max-w-md flex-col gap-6 rounded-[36px] border border-[#e8d9c4] bg-[#fffdf8] p-8 shadow-[0_20px_70px_rgba(36,28,21,0.08)] lg:p-10">
        <Logo />
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-3xl font-semibold tracking-tight">{t('verifyEmail.title')}</h1>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setLocale(locale === 'tr' ? 'en' : 'tr')}
              className={navPillClass(theme)}
            >
              {locale === 'tr' ? 'EN' : 'TR'}
            </button>
          </div>
        </div>

        <div className="rounded-[24px] border border-[#e8d9c4] bg-[#fff8ee] p-6">
          {success ? (
            <div className="space-y-4 text-center">
              <div className="rounded-full bg-green-100 p-4 text-4xl">✓</div>
              <h2 className="text-xl font-semibold">{t('verifyEmail.successTitle')}</h2>
              <p className="text-sm text-[#6e6257]">{t('verifyEmail.successDescription')}</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate className="space-y-4">
              <p className="text-sm leading-7 text-[#6e6257]">
                {t('verifyEmail.description', { email })}
              </p>

              <div>
                <label className="block text-sm font-semibold text-[#241c15]">{t('verifyEmail.codeLabel')}</label>
                <input
                  className="mt-2 w-full rounded-full border border-[#ead8c6] bg-[#fffdf8] px-4 py-3 text-center text-lg tracking-[0.5em] outline-none"
                  placeholder="123456"
                  inputMode="numeric"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  disabled={loading}
                />
              </div>

              {error && (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <Button
                type="submit"
                disabled={loading || code.length !== 6}
                className="w-full rounded-full bg-[#14b78c] px-4 py-3 text-white hover:bg-[#0c9973] disabled:opacity-50"
              >
                {loading ? '...' : t('verifyEmail.submit')}
              </Button>

              <div className="text-center text-sm text-[#6e6257]">
                {cooldown > 0 ? (
                  <span>{t('verifyEmail.resendCooldown', { seconds: cooldown })}</span>
                ) : (
                  <button
                    type="button"
                    onClick={handleResend}
                    className="font-semibold text-[#14b78c] hover:text-[#0c9973]"
                  >
                    {t('verifyEmail.resend')}
                  </button>
                )}
              </div>
            </form>
          )}
        </div>

        <div className="text-center text-sm text-[#6e6257]">
          <Link to="/" className="font-semibold text-[#241c15]">
            {t('auth.home')}
          </Link>
        </div>
      </div>
    </main>
  );
}
