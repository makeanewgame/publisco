import { useEffect, useMemo, type ReactNode } from 'react';
import i18n from 'i18next';
import { initReactI18next, useTranslation } from 'react-i18next';

import en from './locales/en/common.json';
import tr from './locales/tr/common.json';

export type Locale = 'tr' | 'en';

const storedLocale = typeof window !== 'undefined' ? window.localStorage.getItem('publisco-locale') : null;
const initialLocale: Locale = storedLocale === 'en' ? 'en' : 'tr';

void i18n.use(initReactI18next).init({
  resources: {
    tr: { translation: tr },
    en: { translation: en },
  },
  lng: initialLocale,
  fallbackLng: 'tr',
  interpolation: {
    escapeValue: false,
  },
});

export function LocaleProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('publisco-locale', i18n.language === 'en' ? 'en' : 'tr');
      document.documentElement.lang = i18n.language === 'en' ? 'en' : 'tr';
    }

    const handleLanguageChanged = (language: string) => {
      const locale = language === 'en' ? 'en' : 'tr';
      window.localStorage.setItem('publisco-locale', locale);
      document.documentElement.lang = locale;
    };

    i18n.on('languageChanged', handleLanguageChanged);

    return () => {
      i18n.off('languageChanged', handleLanguageChanged);
    };
  }, []);

  return children;
}

export function useLocale() {
  const { t } = useTranslation();

  return useMemo(
    () => ({
      locale: (i18n.language === 'en' ? 'en' : 'tr') as Locale,
      setLocale: (next: Locale) => void i18n.changeLanguage(next),
      t: (key: string, replacements?: Record<string, string | number>) => t(key, replacements),
    }),
    [t],
  );
}
