import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Logo } from '../components/Logo';
import { useLocale } from '../i18n';
import { useTheme } from '../theme';
import { navPillClass } from '../lib/themeClasses';
import { useForgotPasswordMutation } from '../app/services/authApi';

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const { locale, setLocale, t } = useLocale();
  const { theme } = useTheme();
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const [forgotPassword] = useForgotPasswordMutation();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await forgotPassword({ email }).unwrap();
      setSuccess(true);
      setTimeout(() => {
        navigate('/auth/signin');
      }, 3000);
    } catch (err: any) {
      setError(err.data?.message || t('forgotPassword.genericError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main>
      <div className="mx-auto flex max-w-md flex-col gap-6 rounded-[36px] border border-[#e8d9c4] bg-[#fffdf8] p-8 shadow-[0_20px_70px_rgba(36,28,21,0.08)] lg:p-10">
        <Logo />
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t('forgotPassword.title')}</h1>
          </div>
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
              <h2 className="text-xl font-semibold">{t('forgotPassword.successTitle')}</h2>
              <p className="text-sm text-[#6e6257]">
                {t('forgotPassword.successDescription')}
              </p>
              <p className="text-xs text-[#9b8b7e]">{t('forgotPassword.redirectNotice')}</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="text-sm leading-7 text-[#6e6257]">
                {t('forgotPassword.description')}
              </p>

              <div>
                <label className="block text-sm font-semibold text-[#241c15]">{t('forgotPassword.emailLabel')}</label>
                <input
                  className="mt-2 w-full rounded-full border border-[#ead8c6] bg-[#fffdf8] px-4 py-3 text-sm outline-none"
                  placeholder={t('forgotPassword.emailPlaceholder')}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
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
                disabled={loading}
                className="w-full rounded-full bg-[#14b78c] px-4 py-3 text-white hover:bg-[#0c9973] disabled:opacity-50"
              >
                {loading ? t('forgotPassword.sending') : t('forgotPassword.submit')}
              </Button>

              <div className="text-center text-sm text-[#6e6257]">
                <Link to="/auth/signin" className="font-semibold text-[#14b78c] hover:text-[#0c9973]">
                  {t('forgotPassword.backLink')}
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
