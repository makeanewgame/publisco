import { Link } from 'react-router-dom';
import { useTheme } from '../theme';
import { useLocale } from '../i18n';
import { Logo } from './Logo';

export function Footer() {
  const { theme } = useTheme();
  const { t } = useLocale();
  const currentYear = new Date().getFullYear();

  if (theme === 'folder') {
    return (
      <footer className="border-t border-[#e8d9c4] bg-[#fffdf8] px-4 py-6 text-sm text-[#5f544b]">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="flex items-center gap-2">
            <Logo />
            <span className="text-xs">© {currentYear}</span>
          </div>
          <div className="flex flex-wrap justify-center gap-6 text-xs">
            <a href="#features" className="transition hover:text-[#241c15]">{t('footer.features')}</a>
            <a href="#how" className="transition hover:text-[#241c15]">{t('footer.flow')}</a>
            <a href="#faq" className="transition hover:text-[#241c15]">{t('nav.faq')}</a>
          </div>
        </div>
      </footer>
    );
  }

  return (
    <footer className="border-t border-[#e8d9c4] bg-gradient-to-b from-[#fffdf8] to-[#faf6f0]">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid gap-8 md:grid-cols-4">
          {/* Brand section */}
          <div className="md:col-span-1">
            <Logo className="mb-4" />
            <p className="text-sm leading-6 text-[#6e6257]">
              {t('footer.description')}
            </p>
          </div>

          {/* Quick links */}
          <div>
            <h3 className="text-sm font-semibold text-[#241c15]">{t('footer.explore')}</h3>
            <ul className="mt-4 space-y-3">
              <li>
                <a href="#features" className="text-sm text-[#6e6257] transition hover:text-[#241c15]">
                  {t('footer.features')}
                </a>
              </li>
              <li>
                <a href="#how" className="text-sm text-[#6e6257] transition hover:text-[#241c15]">
                  {t('footer.flow')}
                </a>
              </li>
              <li>
                <a href="#faq" className="text-sm text-[#6e6257] transition hover:text-[#241c15]">
                  {t('nav.faq')}
                </a>
              </li>
            </ul>
          </div>

          {/* Account */}
          <div>
            <h3 className="text-sm font-semibold text-[#241c15]">{t('footer.account')}</h3>
            <ul className="mt-4 space-y-3">
              <li>
                <Link to="/auth/signin" className="text-sm text-[#6e6257] transition hover:text-[#241c15]">
                  {t('nav.login')}
                </Link>
              </li>
              <li>
                <Link to="/auth/signup" className="text-sm text-[#6e6257] transition hover:text-[#241c15]">
                  {t('nav.signup')}
                </Link>
              </li>
              <li>
                <Link to="/library" className="text-sm text-[#6e6257] transition hover:text-[#241c15]">
                  {t('nav.library')}
                </Link>
              </li>
            </ul>
          </div>

          {/* Contact & Info */}
          <div>
            <h3 className="text-sm font-semibold text-[#241c15]">{t('footer.contact')}</h3>
            <ul className="mt-4 space-y-3">
              <li>
                <a href="mailto:hello@publisco.com" className="text-sm text-[#6e6257] transition hover:text-[#241c15]">
                  hello@publisco.com
                </a>
              </li>
              <li>
                <a href="https://twitter.com/publisco" className="text-sm text-[#6e6257] transition hover:text-[#241c15]">
                  Twitter
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom section */}
        <div className="mt-12 border-t border-[#e8d9c4] pt-8">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <p className="text-xs text-[#6e6257]">
              © {currentYear} publisco. {t('footer.rightsReserved')}
            </p>
            <div className="flex gap-6 text-xs text-[#6e6257]">
              <Link to="/privacy-policy" className="transition hover:text-[#241c15]">{t('footer.privacyPolicy')}</Link>
              <Link to="/terms-of-service" className="transition hover:text-[#241c15]">{t('footer.termsOfService')}</Link>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
