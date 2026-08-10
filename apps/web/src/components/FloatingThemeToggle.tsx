import { useTheme } from '../theme';
import { useLocale } from '../i18n';

export function FloatingThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const { t } = useLocale();
  const isFolder = theme === 'folder';
  const label = isFolder ? t('nav.themeFolder') : t('nav.themeDefault');

  return (
    <div className="right-4 top-4 z-100 flex items-center gap-2">
      <button
        type="button"
        role="switch"
        aria-checked={isFolder}
        aria-label={label}
        onClick={toggleTheme}
        className="group relative inline-flex h-10 w-16 items-center rounded-full bg-white shadow-lg transition-all duration-200 hover:shadow-xl border border-[#e8d9c4]"
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

      {/* Tooltip */}
      <div className="hidden group-hover:block absolute right-20 top-1/2 -translate-y-1/2 bg-[#241c15] text-white text-xs px-3 py-2 rounded-lg whitespace-nowrap">
        {label}
        <div className="absolute right-[-4px] top-1/2 -translate-y-1/2 w-0 h-0 border-l-4 border-l-[#241c15] border-t-2 border-t-transparent border-b-2 border-b-transparent" />
      </div>
    </div>
  );
}
