import { useTheme } from '../theme';
import { useLocale } from '../i18n';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const { t } = useLocale();
  const isFolder = theme === 'folder';
  const label = isFolder ? t('nav.themeFolder') : t('nav.themeDefault');

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isFolder}
      aria-label={label}
      onClick={toggleTheme}
      className="group relative inline-flex h-10 w-16 shrink-0 items-center rounded-full bg-white shadow-lg transition-all duration-200 hover:shadow-xl border border-[#e8d9c4]"
      title={label}
    >
      {/* Background that changes based on theme */}
      <div
        className={`absolute inset-0 rounded-full transition-colors duration-200 ${isFolder ? 'bg-gradient-to-r from-mint to-[#0f9f7a]' : 'bg-gradient-to-r from-[#e8d9c4] to-[#d9ccc4]'
          }`}
        style={{
          opacity: 0.15,
        }}
      />

      {/* Sliding circle */}
      <span
        className={`relative ml-1 inline-block h-7 w-7 transform rounded-full bg-white shadow-md transition-all duration-300 ${isFolder ? 'translate-x-7' : 'translate-x-0'
          }`}
      />

      {/* Text indicators */}
      <div className="absolute inset-0 flex items-center justify-between px-2 text-xs font-bold">
        <span className="text-[#8b7b6d]" title="Classic theme">
          C
        </span>
        <span className="text-[#8b7b6d]" title="Folder theme">
          F
        </span>
      </div>
    </button>
  );
}
