import { useLocale } from '../i18n';

const PLATFORMS = ['Kindle', 'Apple Books', 'Kobo', 'Google Play Books'];

export function PlatformStrip() {
  const { t } = useLocale();
  const track = [...PLATFORMS, ...PLATFORMS];

  return (
    <div className="border-y border-[#e8d9c4]/70 bg-[#fffdf8] py-6">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <p className="mb-4 text-center text-xs font-semibold uppercase tracking-[0.2em] text-[#a89a89]">
          {t('platforms.caption')}
        </p>
        <div className="relative overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
          <div className="marquee-track flex w-max items-center gap-16">
            {track.map((name, index) => (
              <span
                key={`${name}-${index}`}
                className="shrink-0 text-lg font-bold tracking-tight text-[#c9bcac] grayscale transition-colors duration-200 hover:text-[#6e6257]"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
