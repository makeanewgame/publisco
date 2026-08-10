import { useState } from 'react';
import { GoogleLogin, type CredentialResponse } from '@react-oauth/google';
import { useDispatch } from 'react-redux';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { PasswordInput } from '../components/ui/password-input';
import { Logo } from '../components/Logo';
import { useLocale } from '../i18n';
import { useTheme } from '../theme';
import { navPillClass } from '../lib/themeClasses';
import { useSignUpMutation, useSignInMutation, useGoogleAuthMutation } from '../app/services/authApi';
import { setCredentials } from '../app/authSlice';

export default function AuthPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { locale, setLocale, t } = useLocale();
  const { theme } = useTheme();
  const isSignUp = location.pathname.includes('/signup');
  const redirectTo = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const [signUp] = useSignUpMutation();
  const [signIn] = useSignInMutation();
  const [googleAuth] = useGoogleAuthMutation();

  const handleGoogleSuccess = async (credentialResponse: CredentialResponse) => {
    if (!credentialResponse.credential) {
      return;
    }
    setError('');
    setLoading(true);
    try {
      const response = await googleAuth({ idToken: credentialResponse.credential, locale }).unwrap();
      dispatch(setCredentials(response));
      navigate(redirectTo);
    } catch (err: any) {
      setError(err.data?.message || t('auth.errorGoogle'));
    } finally {
      setLoading(false);
    }
  };

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

    if (isSignUp && !name.trim()) {
      setError(t('auth.errorNameRequired'));
      return;
    }
    if (!email.trim()) {
      setError(t('auth.errorEmailRequired'));
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError(t('auth.errorEmailInvalid'));
      return;
    }
    if (!password) {
      setError(t('auth.errorPasswordRequired'));
      return;
    }
    if (isSignUp && !isPasswordValid) {
      setError(t('auth.errorPasswordRules'));
      return;
    }

    setLoading(true);

    try {
      if (isSignUp) {
        const response = await signUp({ email, password, name, locale }).unwrap();
        // Oturum burada açılmaz: e-posta doğrulanana kadar token verilmez,
        // kullanıcı kodu girip doğrulayınca giriş yapılır.
        navigate('/auth/verify-email', { state: { email: response.user.email } });
      } else {
        const response = await signIn({ email, password }).unwrap();
        dispatch(setCredentials(response));
        navigate(redirectTo);
      }
    } catch (err: any) {
      setError(err.data?.message || t('auth.genericError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className='my-24'>
      <div className="mx-auto flex max-w-4xl flex-col gap-6 rounded-[36px] border border-[#e8d9c4] bg-[#fffdf8] p-8 shadow-[0_20px_70px_rgba(36,28,21,0.08)] lg:p-10">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{isSignUp ? t('auth.signupTitle') : t('auth.title')}</h1>
          </div>
        </div>
        <div className="mx-auto w-full max-w-xl">
          <div className="rounded-[24px] border border-[#e8d9c4] bg-[#fff8ee] p-6">
            <div className="flex justify-center">
              <GoogleLogin
                onSuccess={handleGoogleSuccess}
                onError={() => setError(t('auth.errorGoogle'))}
                text={isSignUp ? 'signup_with' : 'signin_with'}
                width="320"
              />
            </div>

            <div className="my-5 flex items-center gap-3 text-xs font-medium uppercase tracking-wide text-[#9c8f81]">
              <span className="h-px flex-1 bg-[#ead8c6]" />
              {t('auth.orDivider')}
              <span className="h-px flex-1 bg-[#ead8c6]" />
            </div>

            <form onSubmit={handleSubmit} noValidate className="space-y-4">
              {isSignUp && (
                <>
                  <div>
                    <label className="block text-sm font-semibold text-[#241c15]">{t('auth.nameLabel')}</label>
                    <input
                      className="mt-2 w-full rounded-full border border-[#ead8c6] bg-[#fffdf8] px-4 py-3 text-sm outline-none"
                      placeholder={t('auth.namePlaceholder')}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                    />
                  </div>
                </>
              )}

              <div>
                <label className="block text-sm font-semibold text-[#241c15]">{t('auth.emailLabel')}</label>
                <input
                  className="mt-2 w-full rounded-full border border-[#ead8c6] bg-[#fffdf8] px-4 py-3 text-sm outline-none"
                  placeholder={t('auth.emailPlaceholder')}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-[#241c15]">{t('auth.passwordLabel')}</label>
                <PasswordInput
                  className="mt-2"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  toggleLabel={{ show: t('auth.showPassword'), hide: t('auth.hidePassword') }}
                />
                {isSignUp && password.length > 0 && (
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

              {error && (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <Button
                type="submit"
                disabled={loading || (isSignUp && !isPasswordValid)}
                className="mt-6 w-full rounded-full bg-[#14b78c] px-4 py-3 text-white hover:bg-[#0c9973] disabled:opacity-50"
              >
                {loading ? '...' : (isSignUp ? t('auth.submitSignUp') : t('auth.submitSignIn'))}
              </Button>
            </form>

            <div className="mt-4 space-y-3 text-sm text-[#6e6257]">
              {!isSignUp && (
                <p>
                  <Link to="/auth/forgot-password" className="font-semibold text-[#14b78c] hover:text-[#0c9973]">
                    {t('auth.forgotPassword')}
                  </Link>
                </p>
              )}
              <p>
                {isSignUp ? t('auth.switchSignIn') : t('auth.switchSignUp')}{' '}
                <Link to={isSignUp ? '/auth/signin' : '/auth/signup'} className="font-semibold text-[#14b78c] hover:text-[#0c9973]">
                  {isSignUp ? t('auth.submitSignIn') : t('auth.submitSignUp')}
                </Link>
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
