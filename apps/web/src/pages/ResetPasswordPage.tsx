import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { PasswordInput } from '../components/ui/password-input';
import { Logo } from '../components/Logo';
import { useLocale } from '../i18n';
import { useTheme } from '../theme';
import { navPillClass } from '../lib/themeClasses';
import { useResetPasswordMutation } from '../app/services/authApi';

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const { locale, setLocale, t } = useLocale();
  const { theme } = useTheme();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const [resetPassword] = useResetPasswordMutation();

  const passwordRules = {
    minLength: password.length >= 8,
    hasUpper: /[A-Z]/.test(password),
    hasLower: /[a-z]/.test(password),
    hasPunctuation: /[!"#$%&'()*+,\-./:;<=>?@[\]^_`{|}~]/.test(password),
  };
  const isPasswordValid = Object.values(passwordRules).every(Boolean);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!token) {
      setError(t('resetPassword.errorTokenMissing'));
      return;
    }
    if (!isPasswordValid) {
      setError(t('auth.errorPasswordRules'));
      return;
    }
    if (password !== confirmPassword) {
      setError(t('resetPassword.errorPasswordMismatch'));
      return;
    }

    setLoading(true);
    try {
      await resetPassword({ token, newPassword: password }).unwrap();
      setSuccess(true);
      setTimeout(() => {
        navigate('/auth/signin');
      }, 3000);
    } catch (err: any) {
      setError(err.data?.message || t('resetPassword.genericError'));
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
            <h1 className="text-3xl font-semibold tracking-tight">{t('resetPassword.title')}</h1>
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
              <h2 className="text-xl font-semibold">{t('resetPassword.successTitle')}</h2>
              <p className="text-sm text-[#6e6257]">{t('resetPassword.successDescription')}</p>
              <p className="text-xs text-[#9b8b7e]">{t('resetPassword.redirectNotice')}</p>
            </div>
          ) : !token ? (
            <div className="space-y-4 text-center">
              <p className="text-sm text-[#6e6257]">{t('resetPassword.errorTokenMissing')}</p>
              <Link to="/auth/forgot-password" className="font-semibold text-[#14b78c] hover:text-[#0c9973]">
                {t('resetPassword.backToForgotPassword')}
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate className="space-y-4">
              <p className="text-sm leading-7 text-[#6e6257]">
                {t('resetPassword.description')}
              </p>

              <div>
                <label className="block text-sm font-semibold text-[#241c15]">{t('resetPassword.newPasswordLabel')}</label>
                <PasswordInput
                  className="mt-2"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                  toggleLabel={{ show: t('auth.showPassword'), hide: t('auth.hidePassword') }}
                />
                {password.length > 0 && (
                  <ul className="mt-2 space-y-1 px-2 text-xs">
                    <li className={passwordRules.minLength ? 'text-green-600' : 'text-[#0c7a5e]'}>
                      {passwordRules.minLength ? '✓' : '•'} {t('auth.passwordRuleMinLength')}
                    </li>
                    <li className={passwordRules.hasUpper ? 'text-green-600' : 'text-[#0c7a5e]'}>
                      {passwordRules.hasUpper ? '✓' : '•'} {t('auth.passwordRuleUpper')}
                    </li>
                    <li className={passwordRules.hasLower ? 'text-green-600' : 'text-[#0c7a5e]'}>
                      {passwordRules.hasLower ? '✓' : '•'} {t('auth.passwordRuleLower')}
                    </li>
                    <li className={passwordRules.hasPunctuation ? 'text-green-600' : 'text-[#0c7a5e]'}>
                      {passwordRules.hasPunctuation ? '✓' : '•'} {t('auth.passwordRulePunctuation')}
                    </li>
                  </ul>
                )}
              </div>

              <div>
                <label className="block text-sm font-semibold text-[#241c15]">{t('resetPassword.confirmPasswordLabel')}</label>
                <PasswordInput
                  className="mt-2"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  disabled={loading}
                  toggleLabel={{ show: t('auth.showPassword'), hide: t('auth.hidePassword') }}
                />
              </div>

              {error && (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <Button
                type="submit"
                disabled={loading || !isPasswordValid}
                className="w-full rounded-full bg-[#14b78c] px-4 py-3 text-white hover:bg-[#0c9973] disabled:opacity-50"
              >
                {loading ? t('resetPassword.sending') : t('resetPassword.submit')}
              </Button>
            </form>
          )}
        </div>

        <div className="text-center text-sm text-[#6e6257]">
          <Link to="/auth/signin" className="font-semibold text-[#241c15]">
            {t('forgotPassword.backLink')}
          </Link>
        </div>
      </div>
    </main>
  );
}
