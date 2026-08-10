import { useEffect } from 'react';
import { motion } from 'motion/react';
import { useSelector } from 'react-redux';
import { Link, useLocation } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Navbar } from '../components/Navbar';
import { HeroVisualCard } from '../components/hero/HeroVisualCard';
import { PlatformStrip } from '../components/PlatformStrip';
import { FaqAccordion } from '../components/FaqAccordion';
import { useLocale } from '../i18n';
import { useTheme } from '../theme';
import { selectCurrentUser } from '../app/authSlice';

type FeatureIconType = 'document' | 'bolt' | 'lock';

function FeatureIcon({ type }: { type: FeatureIconType }) {
  const common = 'h-5 w-5';

  if (type === 'bolt') {
    return (
      <svg viewBox="0 0 24 24" fill="none" className={common} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="m13 2-8 12h6l-1 8 8-12h-6l1-8Z" />
      </svg>
    );
  }

  if (type === 'lock') {
    return (
      <svg viewBox="0 0 24 24" fill="none" className={common} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="10" width="16" height="11" rx="2" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" className={common} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 3h7l5 5v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

export default function HomePage() {
  const { t } = useLocale();
  const { theme } = useTheme();
  const location = useLocation();
  const user = useSelector(selectCurrentUser);
  const isAuthenticated = !!user;

  useEffect(() => {
    if (location.pathname === '/' && location.hash) {
      document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [location.pathname, location.hash]);

  const heroTitleText = t('hero.title');
  const heroHighlightWord = t('hero.highlightWord');
  const highlightIndex = heroHighlightWord ? heroTitleText.indexOf(heroHighlightWord) : -1;
  const heroTitleBefore = highlightIndex >= 0 ? heroTitleText.slice(0, highlightIndex) : heroTitleText;
  const heroTitleHighlight = highlightIndex >= 0 ? heroTitleText.slice(highlightIndex, highlightIndex + heroHighlightWord.length) : '';
  const heroTitleAfter = highlightIndex >= 0 ? heroTitleText.slice(highlightIndex + heroHighlightWord.length) : '';

  const heroAccent = (
    <span className="block text-[#14b78c]" style={{ fontFamily: 'Caveat, cursive' }}>
      {t('hero.accent')}
    </span>
  );

  const heroBadge = (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      className="mb-4 inline-flex w-fit items-center rounded-full border border-[#a6f4dc] bg-[#ecfdf7] px-3 py-1.5 text-sm font-medium text-[#0c7a5e]"
    >
      {t('hero.badge')}
    </motion.div>
  );

  const features = [
    { title: t('features.section1.title'), text: t('features.section1.text'), icon: 'document' as const },
    { title: t('features.section2.title'), text: t('features.section2.text'), icon: 'bolt' as const },
    { title: t('features.section3.title'), text: t('features.section3.text'), icon: 'lock' as const },
  ];

  const badgeColors = ['bg-mint-soft', 'bg-coral-soft', 'bg-butter-soft', 'bg-sky-soft'];

  const howSteps = [
    { title: t('howItWorks.step1.title'), text: t('howItWorks.step1.text') },
    { title: t('howItWorks.step2.title'), text: t('howItWorks.step2.text') },
    { title: t('howItWorks.step3.title'), text: t('howItWorks.step3.text') },
  ];

  const useCases = [
    { title: t('useCases.item1.title'), description: t('useCases.item1.description') },
    { title: t('useCases.item2.title'), description: t('useCases.item2.description') },
    { title: t('useCases.item3.title'), description: t('useCases.item3.description') },
  ];

  const faqItems = [
    { question: t('faq.q1.question'), answer: t('faq.q1.answer') },
    { question: t('faq.q2.question'), answer: t('faq.q2.answer') },
    { question: t('faq.q3.question'), answer: t('faq.q3.answer') },
    { question: t('faq.q4.question'), answer: t('faq.q4.answer') },
  ];

  return (
    <main className="px-4 py-10 sm:px-6 sm:py-14 lg:px-8 lg:py-16">
      <div className="mx-auto flex max-w-7xl flex-col">
        {theme === 'folder' ? (
          <div className="folder-wrap">


            <div className="paper-body">
              <div className="relative grid gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:gap-14">
                <div className="flex flex-col justify-center">
                  {heroBadge}
                  <h1 className="max-w-3xl text-4xl font-black leading-[0.95] tracking-[-0.03em] text-[#241c15] sm:text-5xl lg:text-6xl">
                    {heroTitleBefore}
                    {highlightIndex >= 0 && (
                      <span className="hl-wrap">
                        <span className="hl-mark" />
                        <span className="hl-text">{heroTitleHighlight}</span>
                      </span>
                    )}
                    {heroTitleAfter}{' '}
                    {heroAccent}
                  </h1>
                  <p className="mt-5 max-w-2xl text-lg leading-8 text-[#5f544b]">
                    {t('hero.description')}
                  </p>
                  <div className="mt-8 flex flex-wrap gap-3">
                    <Link to="/convert">
                      <Button className="rounded-full bg-coral px-6 py-3 text-white shadow-[0_12px_32px_rgba(255,138,94,0.28)] hover:bg-coral/90">
                        {t('hero.ctaPrimary')}
                      </Button>
                    </Link>
                    <Button className="rounded-full border-2 border-mint bg-transparent px-6 py-3 text-mint hover:bg-mint-pale">
                      {t('hero.ctaSecondary')}
                    </Button>
                  </div>
                </div>

                <div className="flex items-center justify-center">
                  <HeroVisualCard />
                </div>
              </div>
            </div>
          </div>
        ) : (
          <>
            <section className="relative overflow-hidden rounded-[36px] border border-[#e8d9c4] bg-[#fffdf8] p-8 shadow-[0_24px_60px_-30px_rgba(36,30,23,0.18)] sm:p-10 lg:p-14">
              <motion.div
                className="absolute left-[-30px] top-[-20px] h-28 w-28 rounded-full bg-coral-soft/70 pointer-events-none"
                animate={{
                  x: [0, 15, -5, 10, 10, 0],
                  y: [0, 10, -10, 5, 5, 0],
                  scale: [1, 1.05, 1, 1.6, 0.7, 1],
                  opacity: [0.7, 0.7, 0.7, 0.15, 0.15, 0.7],
                }}
                transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut', times: [0, 0.3, 0.6, 0.8, 0.9, 1] }}
              />
              <motion.div
                className="absolute bottom-10 right-10 h-20 w-20 rounded-full bg-[#ffc2d1]/70 pointer-events-none"
                animate={{
                  x: [0, 25, -15, 20, 20, 0],
                  y: [0, -20, 15, -10, -10, 0],
                  scale: [1, 0.95, 1, 1.5, 0.7, 1],
                  opacity: [0.8, 0.8, 0.8, 0.2, 0.2, 0.8],
                }}
                transition={{ duration: 20, delay: 7, repeat: Infinity, ease: 'easeInOut', times: [0, 0.3, 0.6, 0.85, 0.92, 1] }}
              />
              <motion.div
                className="absolute right-16 top-1/3 h-7 w-7 rounded-full border border-[#14b78c]/40 pointer-events-none"
                animate={{
                  x: [0, -15, 20, -5, -5, 0],
                  y: [0, 25, -10, 15, 15, 0],
                  rotate: 12,
                  scale: [1, 1.2, 1, 1.8, 0.7, 1],
                  opacity: [0.6, 0.6, 0.6, 0.15, 0.15, 0.6],
                }}
                transition={{ duration: 16, delay: 4, repeat: Infinity, ease: 'easeInOut', times: [0, 0.35, 0.65, 0.8, 0.9, 1] }}
              />
              <motion.div
                className="absolute left-1/3 top-4 h-8 w-8 rounded-full border border-butter-soft pointer-events-none"
                animate={{
                  x: [0, -20, 15, -10, -10, 0],
                  y: [0, 15, -20, 10, 10, 0],
                  rotate: -18,
                  scale: [1, 1.1, 1, 1.7, 0.7, 1],
                  opacity: [0.6, 0.6, 0.6, 0.15, 0.15, 0.6],
                }}
                transition={{ duration: 15, delay: 2, repeat: Infinity, ease: 'easeInOut', times: [0, 0.25, 0.55, 0.75, 0.85, 1] }}
              />

              <div className="relative grid gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:gap-14">
                <div className="flex flex-col justify-center">
                  {heroBadge}
                  <motion.h1
                    initial={{ opacity: 0, y: 15 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7, ease: 'easeOut', delay: 0.1 }}
                    className="max-w-3xl text-4xl font-black leading-[0.95] tracking-[-0.03em] text-[#241c15] sm:text-5xl lg:text-6xl"
                  >
                    {heroTitleBefore}
                    {highlightIndex >= 0 && (
                      <span className="hl-wrap">
                        <span className="hl-mark" />
                        <span className="hl-text">{heroTitleHighlight}</span>
                      </span>
                    )}
                    {heroTitleAfter}{' '}
                    {heroAccent}
                  </motion.h1>
                  <motion.p
                    initial={{ opacity: 0, y: 15 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7, ease: 'easeOut', delay: 0.2 }}
                    className="mt-5 max-w-2xl text-lg leading-8 text-[#5f544b]"
                  >
                    {t('hero.description')}
                  </motion.p>
                  <motion.div
                    initial={{ opacity: 0, y: 15 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7, ease: 'easeOut', delay: 0.3 }}
                    className="mt-8 flex flex-wrap gap-3"
                  >
                    <Link to="/convert">
                      <Button className="rounded-full bg-coral px-6 py-3 text-white shadow-[0_12px_32px_rgba(255,138,94,0.28)] hover:bg-coral/90">
                        {t('hero.ctaPrimary')}
                      </Button>
                    </Link>
                    <Button className="rounded-full border-2 border-mint bg-transparent px-6 py-3 text-mint hover:bg-mint-pale">
                      {t('hero.ctaSecondary')}
                    </Button>
                  </motion.div>
                </div>

                <div className="flex items-center justify-center">
                  <HeroVisualCard />
                </div>
              </div>
            </section>
          </>
        )}
      </div>

      <div className="my-16 -mx-4 sm:my-20 sm:-mx-6 lg:my-24 lg:-mx-8">
        <PlatformStrip />
      </div>

      <div className="mx-auto flex max-w-7xl flex-col gap-20 sm:gap-24 lg:gap-28">
        {/* Nasıl çalışır — asymmetric: heading pinned left, connected vertical timeline right */}
        <section id="how" className="grid gap-8 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
          <div className="lg:self-center">
            <p className="mb-1 text-2xl text-[#14b78c] text-4xl" style={{ fontFamily: 'Caveat, cursive' }}>
              {t('howItWorks.eyebrow')}
            </p>
            <h2 className="text-2xl font-bold tracking-tight text-[#241c15] sm:text-3xl">{t('howItWorks.heading')}</h2>
            <p className="max-w-xs text-sm leading-7 text-[#6e6257]">{t('howItWorks.subtitle')}</p>
          </div>

          <div className="relative">
            <div className="absolute left-5 top-2 bottom-2 w-px bg-gradient-to-b from-[#14b78c] via-[#14b78c]/25 to-transparent" />
            <div className="flex flex-col gap-9">
              {howSteps.map((item, index) => (
                <div key={item.title} className="relative flex gap-6">
                  <div className="relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#14b78c] text-sm font-bold text-white shadow-[0_10px_24px_-8px_rgba(20,183,140,0.55)]">
                    {index + 1}
                  </div>
                  <div className="pt-1">
                    <h3 className="text-lg font-semibold text-[#241c15]">{item.title}</h3>
                    <p className="mt-1.5 max-w-md text-sm leading-7 text-[#6e6257]">{item.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Neden Publisco — bento: one lead feature, two stacked alongside */}
        <section id="features">
          <div className="mb-8 sm:mb-10">
            <p className="mb-1 text-4xl text-[#ff8a5e]" style={{ fontFamily: 'Caveat, cursive' }}>
              {t('features.eyebrow')}
            </p>
            <h2 className="text-2xl font-semibold tracking-tight text-[#241c15] sm:text-3xl">{t('features.heading')}</h2>
          </div>
          <div className="grid gap-4 lg:grid-cols-3 lg:grid-rows-2">
            <div className="rounded-[28px] border border-[#e8d9c4] bg-gradient-to-br from-[#fffdf8] to-[#fff3e4] p-7 shadow-[0_16px_34px_-22px_rgba(36,30,23,0.16)] sm:p-8 lg:col-span-2 lg:row-span-2 lg:flex lg:flex-col">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-mint-soft text-[#241c15]">
                <FeatureIcon type={features[0].icon} />
              </div>

              <div className="my-10 flex flex-1 items-center justify-center gap-3 lg:my-12">
                <div className="flex flex-col gap-2.5 rounded-2xl border border-[#e8d9c4] bg-[#f6ebdc] p-4">
                  <div className="h-2 w-16 rounded-full bg-[#c9bcac]" />
                  <div className="h-2 w-9 rounded-full bg-[#c9bcac]" />
                  <div className="h-2 w-12 rounded-full bg-[#c9bcac]" />
                  <div className="h-2 w-14 rounded-full bg-[#c9bcac]" />
                </div>
                <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5 shrink-0 text-[#14b78c]" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h14" />
                  <path d="m12 5 7 7-7 7" />
                </svg>
                <div className="flex flex-col gap-2.5 rounded-2xl border border-[#a6f4dc] bg-[#ecfdf7] p-4 shadow-[0_10px_24px_-12px_rgba(20,183,140,0.4)]">
                  <div className="h-2 w-16 rounded-full bg-[#14b78c]" />
                  <div className="h-2 w-16 rounded-full bg-[#14b78c]" />
                  <div className="h-2 w-16 rounded-full bg-[#14b78c]" />
                  <div className="h-2 w-16 rounded-full bg-[#14b78c]" />
                </div>
              </div>

              <div>
                <h3 className="text-2xl font-semibold text-[#241c15]">{features[0].title}</h3>
                <p className="mt-3 max-w-md text-base leading-7 text-[#6e6257]">{features[0].text}</p>
              </div>
            </div>
            {features.slice(1).map((item, index) => (
              <div key={item.title} className="rounded-[24px] border border-[#e8d9c4] bg-[#fffdf8] p-6 shadow-[0_16px_34px_-22px_rgba(36,30,23,0.16)]">
                <div className={`mb-3 flex h-11 w-11 items-center justify-center rounded-full ${badgeColors[index % badgeColors.length]} text-[#241c15]`}>
                  <FeatureIcon type={item.icon} />
                </div>
                <h3 className="text-lg font-semibold text-[#241c15]">{item.title}</h3>
                <p className="mt-2 text-sm leading-7 text-[#6e6257]">{item.text}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Kimler için ideal — editorial list, no cards, dividers only */}
        <section id="use-cases" className="grid gap-8 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
          <div className="lg:self-center">
            <p className="mb-1 text-4xl text-[#14b78c]" style={{ fontFamily: 'Caveat, cursive' }}>
              {t('useCases.eyebrow')}
            </p>
            <h2 className="text-2xl font-semibold tracking-tight text-[#241c15] sm:text-3xl">{t('useCases.heading')}</h2>
          </div>
          <div className="divide-y divide-[#e8d9c4]">
            {useCases.map((item, index) => (
              <div key={item.title} className="group flex items-start gap-6 py-6 transition-transform duration-200 first:pt-0 last:pb-0 hover:translate-x-1.5">
                <span className="w-10 shrink-0 text-3xl font-black text-[#e8d9c4] transition-colors duration-200 group-hover:text-[#14b78c]">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <div>
                  <h3 className="text-lg font-semibold text-[#241c15]">{item.title}</h3>
                  <p className="mt-1.5 text-sm leading-7 text-[#6e6257]">{item.description}</p>
                </div>
              </div>
            ))}
          </div>
        </section>



        <section id="cta" className="relative overflow-hidden rounded-[36px] border border-[#e8d9c4] bg-gradient-to-r from-[#14b78c]/5 to-[#ff8a5e]/5 p-8 shadow-[0_10px_30px_rgba(36,28,21,0.04)] sm:p-12 lg:p-16">
          <div className="absolute left-[-40px] top-[-40px] h-40 w-40 rounded-full bg-mint-soft/30" />
          <div className="absolute right-[-30px] bottom-[-30px] h-32 w-32 rounded-full bg-coral-soft/30" />
          <div className="relative mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-black tracking-[-0.02em] text-[#241c15] sm:text-4xl">
              {t('finalCta.heading')}
            </h2>
            <p className="mt-4 text-lg leading-7 text-[#6e6257]">
              {t('finalCta.description')}
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link to="/convert">
                <Button className="rounded-full bg-mint px-8 py-3 text-white shadow-[0_12px_32px_rgba(20,183,140,0.28)] hover:bg-mint/90">
                  {t('finalCta.primary')}
                </Button>
              </Link>
              {!isAuthenticated && (
                <Link to="/auth/signup">
                  <Button className="rounded-full border-2 border-[#e8d9c4] bg-[#fffdf8] px-8 py-3 text-[#241c15] hover:bg-[#fff5e9]">
                    {t('finalCta.secondary')}
                  </Button>
                </Link>
              )}
            </div>
          </div>
        </section>

        <section id="faq" className="mx-auto w-full max-w-3xl">
          <div className="col-span-full mb-8 text-center sm:mb-10">
            <h2 className="text-2xl font-semibold tracking-tight text-[#241c15]">{t('faq.heading')}</h2>
          </div>
          <FaqAccordion items={faqItems} />
        </section>
      </div>
    </main>
  );
}
