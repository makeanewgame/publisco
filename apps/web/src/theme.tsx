import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type ThemeName = 'default' | 'folder';

const STORAGE_KEY = 'publisco-theme';

function getInitialTheme(): ThemeName {

  return 'default'

  if (typeof window === 'undefined') return 'default';
  return window.localStorage.getItem(STORAGE_KEY) === 'folder' ? 'folder' : 'default';
}

type ThemeContextValue = {
  theme: ThemeName;
  setTheme: (next: ThemeName) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeName>(getInitialTheme);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme,
      // toggleTheme: () => setTheme((prev) => (prev === 'folder' ? 'default' : 'folder')),
      toggleTheme: () => setTheme((prev) => (prev === 'folder' ? 'default' : 'default')),
    }),
    [theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider');
  return ctx;
}
