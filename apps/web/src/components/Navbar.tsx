import { useDispatch, useSelector } from 'react-redux';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import { Logo } from './Logo';
import { navPillClass, userChipClass } from '../lib/themeClasses';
import { useLocale } from '../i18n';
import { useTheme } from '../theme';
import { clearCredentials, selectCurrentUser } from '../app/authSlice';
import { ThemeToggle } from './ThemeToggle';

export function Navbar() {
  const { locale, setLocale, t } = useLocale();
  const { theme } = useTheme();
  const { pathname } = useLocation();
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const user = useSelector(selectCurrentUser);
  const isAuthenticated = !!user;

  const handleLogout = () => {
    dispatch(clearCredentials());
    navigate('/');
  };

  const isConvertActive = pathname === '/convert';
  const isLibraryActive = pathname === '/library';
  const isPremiumActive = pathname === '/premium';
  const isAccountActive = pathname === '/account';

  const localeToggle = (
    <button
      type="button"
      onClick={() => setLocale(locale === 'tr' ? 'en' : 'tr')}
      className="rounded-full px-3 py-2 text-xs font-semibold transition-all duration-200 text-[#6e6257] hover:bg-[#f5e8da] hover:text-[#241c15]"
      title={locale === 'tr' ? 'Switch to English' : 'Türkçeye geç'}
    >
      {locale === 'tr' ? 'EN' : 'TR'}
    </button>
  );

  const userChip = user && (
    <div className={userChipClass(theme)}>
      <div className="flex items-center gap-2">
        {user.avatarUrl ? (
          <img src={user.avatarUrl} alt={user.name} className="h-6 w-6 rounded-full" />
        ) : (
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#14b78c] text-xs font-bold text-white">
            {user.name?.charAt(0).toUpperCase() || user.email.charAt(0).toUpperCase()}
          </div>
        )}
        <span className="text-sm font-medium text-[#241c15]">{user.name || user.email}</span>
      </div>
      <button type="button" onClick={handleLogout} className="ml-2 text-xs text-[#0c7a5e] transition hover:text-[#14b78c]">
        {t('library.logout')}
      </button>
    </div>
  );

  if (theme === 'folder') {
    return (
      <div className="tabs-row">
        <ThemeToggle />
        <Logo />
        <Link to="/#features" className="tab t1">{t('nav.features')}</Link>
        <Link to="/#how" className="tab t2">{t('nav.how')}</Link>
        <Link to="/#faq" className="tab t3">{t('nav.faq')}</Link>
        <Link to="/convert" className={navPillClass(theme, isConvertActive)}>{t('library.convert')}</Link>
        <Link to="/premium" className={navPillClass(theme, isPremiumActive)}>{t('nav.pricing')}</Link>
        {isAuthenticated && (
          <>
            <Link to="/library" className={navPillClass(theme, isLibraryActive)}>{t('nav.library')}</Link>
            <Link to="/account" className={navPillClass(theme, isAccountActive)}>{t('nav.account')}</Link>
          </>
        )}
        <div className="tabs-row-end">
          {localeToggle}
          {!isAuthenticated && (
            <>
              <Link to="/auth/signin" className="tab tab-ghost">{t('nav.login')}</Link>
              <Link to="/auth/signup" className="tab-cta">{t('nav.signup')}</Link>
            </>
          )}
          {userChip}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto">
      <nav className="sticky top-0 z-50 flex flex-wrap items-center justify-between gap-4 border-b border-[#e8d9c4]/50 bg-[#fffdf8]/95 px-4 py-4 backdrop-blur-md sm:px-6 lg:px-8 shadow-[0_1px_3px_rgba(36,28,21,0.06)]">
        <div className="flex items-center gap-8">
          <ThemeToggle />
          <Logo />
          <div className="hidden items-center gap-1 text-[#6e6257] lg:flex">
            <Link
              to="/#features"
              className="rounded-lg px-3 py-2 transition-all duration-200 hover:bg-[#f5e8da] hover:text-[#241c15]"
            >
              {t('nav.features')}
            </Link>
            <Link
              to="/#how"
              className="rounded-lg px-3 py-2 transition-all duration-200 hover:bg-[#f5e8da] hover:text-[#241c15]"
            >
              {t('nav.how')}
            </Link>
            <Link
              to="/#faq"
              className="rounded-lg px-3 py-2 transition-all duration-200 hover:bg-[#f5e8da] hover:text-[#241c15]"
            >
              {t('nav.faq')}
            </Link>
            <Link to="/premium" className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${isPremiumActive ? 'bg-mint text-white shadow-[0_4px_12px_rgba(20,183,140,0.25)]' : 'text-[#6e6257] hover:bg-mint/10 hover:text-mint'}`}>
              {t('nav.pricing')}
            </Link>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <div className="h-5 w-px bg-[#e8d9c4]" />
          <Link to="/convert" className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${isConvertActive ? 'bg-mint text-white shadow-[0_4px_12px_rgba(20,183,140,0.25)]' : 'text-[#6e6257] hover:bg-mint/10 hover:text-mint'}`}>
            {t('library.convert')}
          </Link>

          {isAuthenticated && (
            <>
              <Link to="/library" className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${isLibraryActive ? 'bg-[#14b78c] text-white shadow-[0_4px_12px_rgba(20,183,140,0.25)]' : 'text-[#6e6257] hover:bg-mint/10 hover:text-mint'}`}>
                {t('nav.library')}
              </Link>
              <Link to="/account" className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-200 ${isAccountActive ? 'bg-[#14b78c] text-white shadow-[0_4px_12px_rgba(20,183,140,0.25)]' : 'text-[#6e6257] hover:bg-mint/10 hover:text-mint'}`}>
                {t('nav.account')}
              </Link>
            </>
          )}

          {!isAuthenticated && (
            <>
              <Link to="/auth/signin">
                <Button className="rounded-full border border-[#d9ccc4] bg-transparent px-4 py-2 text-sm font-medium text-[#6e6257] transition-all duration-200 hover:border-[#c4b5a8] hover:bg-[#f9f3ed]">
                  {t('nav.login')}
                </Button>
              </Link>
              <Link to="/auth/signup">
                <Button className="rounded-full bg-mint px-4 py-2 text-sm font-medium text-white shadow-[0_4px_12px_rgba(20,183,140,0.25)] transition-all duration-200 hover:bg-[#0f9f7a] hover:shadow-[0_6px_16px_rgba(20,183,140,0.35)]">
                  {t('nav.signup')}
                </Button>
              </Link>
            </>
          )}
          {userChip}

          {localeToggle}

        </div>
      </nav>
    </div>

  );
}
