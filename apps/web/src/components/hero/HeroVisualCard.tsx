import { motion } from 'motion/react';
import { useLocale } from '../../i18n';

export function HeroVisualCard() {
  const { t } = useLocale();

  return (
    <div className="relative w-full max-w-[400px] aspect-square flex items-center justify-center">
      {/* Ambient conic glow */}
      <motion.div
        animate={{
          scale: [1, 1.05, 1],
          opacity: [0.15, 0.25, 0.15],
          rotate: [0, 90, 180, 270, 360],
        }}
        transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
        className="absolute w-[130%] h-[130%] bg-[conic-gradient(from_90deg_at_50%_50%,#14b78c_0%,#fffdf8_50%,#ff8a5e_100%)] rounded-[100px] blur-3xl pointer-events-none mix-blend-multiply"
      />

      {/* Floating card stack */}
      <motion.div
        animate={{ y: [-8, 8, -8] }}
        transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
        className="relative w-full h-full"
      >
        <div className="absolute right-0 bottom-2 w-[90%] h-[94%] bg-[#f6ebdc] rounded-[32px] shadow-[0_20px_40px_-10px_rgba(36,28,21,0.1)] border border-[#e8d9c4]" />
        <div className="absolute right-3 bottom-5 w-[92%] h-[94%] bg-[#fff8ee] rounded-[32px] shadow-[0_15px_30px_-5px_rgba(36,28,21,0.05)] border border-[#ead8c6]" />

        <div className="absolute right-6 bottom-8 w-[94%] h-[96%] bg-white/95 backdrop-blur-2xl rounded-[32px] shadow-[0_30px_60px_-15px_rgba(20,183,140,0.14),0_0_0_1px_rgba(255,255,255,0.8)_inset] border border-[#e8d9c4] p-7 flex flex-col items-center relative overflow-hidden">
          {/* Subtle technical grid */}
          <div className="absolute inset-0 pointer-events-none bg-[linear-gradient(to_right,#14b78c0a_1px,transparent_1px),linear-gradient(to_bottom,#14b78c0a_1px,transparent_1px)] bg-[size:1.25rem_1.25rem] [mask-image:radial-gradient(ellipse_70%_70%_at_50%_40%,#000_20%,transparent_100%)]" />

          {/* Animated flow rings */}
          <div className="absolute inset-0 pointer-events-none flex items-center justify-center -translate-y-6">
            <svg viewBox="0 0 400 400" className="w-[150%] h-[150%] opacity-70">
              <defs>
                <linearGradient id="hero-ring-glow" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#14b78c" stopOpacity="0" />
                  <stop offset="25%" stopColor="#14b78c" stopOpacity="0.8" />
                  <stop offset="75%" stopColor="#14b78c" stopOpacity="0.8" />
                  <stop offset="100%" stopColor="#14b78c" stopOpacity="0" />
                </linearGradient>
              </defs>
              <motion.circle
                cx="200" cy="200" r="90" fill="none"
                stroke="url(#hero-ring-glow)" strokeWidth="1.5" strokeDasharray="4 12"
                animate={{ rotate: 360 }}
                style={{ originX: '200px', originY: '200px' }}
                transition={{ duration: 25, repeat: Infinity, ease: 'linear' }}
              />
              <motion.circle
                cx="200" cy="200" r="130" fill="none"
                stroke="url(#hero-ring-glow)" strokeWidth="1" strokeDasharray="2 8"
                animate={{ rotate: -360 }}
                style={{ originX: '200px', originY: '200px' }}
                transition={{ duration: 40, repeat: Infinity, ease: 'linear' }}
              />
            </svg>
          </div>

          {/* Core conversion emblem */}
          <div className="relative flex-1 w-full flex items-center justify-center z-10 pt-3">
            <div className="relative w-24 h-24 flex items-center justify-center">
              <motion.div animate={{ scale: [1, 1.1, 1.4], opacity: [0, 0.2, 0] }} transition={{ duration: 3, repeat: Infinity, ease: 'easeOut', times: [0, 0.2, 1] }} className="absolute inset-0 bg-[#14b78c] rounded-3xl" />
              <motion.div animate={{ scale: [1, 1.1, 1.4], opacity: [0, 0.2, 0] }} transition={{ duration: 3, repeat: Infinity, ease: 'easeOut', times: [0, 0.2, 1], delay: 1.5 }} className="absolute inset-0 bg-[#14b78c] rounded-3xl" />

              <motion.div
                animate={{ y: [-3, 3, -3] }}
                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                className="relative w-full h-full bg-gradient-to-br from-[#35d6a9] to-[#0c9973] rounded-3xl shadow-[0_20px_40px_-10px_rgba(20,183,140,0.5),inset_0_2px_0_rgba(255,255,255,0.3)] overflow-hidden flex items-center justify-center border border-[#6ee8c5]"
              >
                <motion.div
                  animate={{ top: ['-20%', '120%'] }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                  className="absolute left-0 right-0 h-[3px] bg-white z-20 shadow-[0_0_20px_6px_rgba(255,255,255,0.9)]"
                />

                <svg viewBox="0 0 64 64" className="w-12 h-12 z-10 text-white overflow-visible">
                  <rect x="14" y="8" width="36" height="48" rx="5" fill="none" stroke="currentColor" strokeWidth="2.5" />
                  <path d="M 34 8 L 34 22 L 50 22" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

                  <motion.rect x="22" y="30" height="3.5" rx="1.75" fill="currentColor"
                    initial={{ width: 12 }}
                    animate={{ width: [12, 22, 12] }}
                    transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                  />
                  <motion.rect x="22" y="38" height="3.5" rx="1.75" fill="currentColor"
                    initial={{ width: 22 }}
                    animate={{ width: [22, 14, 22] }}
                    transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut', delay: 0.3 }}
                  />
                  <motion.rect x="22" y="46" height="3.5" rx="1.75" fill="currentColor"
                    initial={{ width: 16 }}
                    animate={{ width: [16, 22, 16] }}
                    transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut', delay: 0.6 }}
                  />
                </svg>
              </motion.div>

              {/* Orbiting elements */}
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 12, repeat: Infinity, ease: 'linear' }}
                className="absolute w-[180px] h-[180px] rounded-full pointer-events-none"
              >
                <motion.div
                  animate={{ rotate: -360 }}
                  transition={{ duration: 12, repeat: Infinity, ease: 'linear' }}
                  className="absolute -top-3 left-1/2 -translate-x-1/2 w-9 h-9 bg-white/95 backdrop-blur-md rounded-[14px] shadow-[0_10px_20px_-5px_rgba(20,183,140,0.2)] border border-[#14b78c]/30 flex items-center justify-center text-[#14b78c]"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>
                </motion.div>

                <motion.div
                  animate={{ rotate: -360 }}
                  transition={{ duration: 12, repeat: Infinity, ease: 'linear' }}
                  className="absolute -bottom-3 left-1/2 -translate-x-1/2 w-8 h-8 bg-gradient-to-tr from-[#ff8a5e] to-[#ffab85] rounded-full shadow-[0_10px_20px_-5px_rgba(255,138,94,0.4)] border border-white flex items-center justify-center text-white"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
                </motion.div>
              </motion.div>
            </div>
          </div>

          {/* Status area */}
          <div className="w-full flex flex-col items-center z-10 mt-5">
            <motion.div
              animate={{ backgroundPosition: ['0% 50%', '200% 50%'] }}
              transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
              className="font-bold text-[11px] sm:text-xs tracking-[0.35em] mb-4 uppercase text-transparent bg-clip-text"
              style={{
                backgroundImage: 'linear-gradient(90deg, #14b78c 0%, #6ee8c5 25%, #14b78c 50%, #6ee8c5 75%, #14b78c 100%)',
                backgroundSize: '200% auto',
              }}
            >
              {t('hero.cardStatus')}
            </motion.div>

            <div className="w-[85%] h-2 relative mb-6">
              <svg className="w-full h-full overflow-visible" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="hero-bar-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#14b78c" stopOpacity="0.2" />
                    <stop offset="60%" stopColor="#14b78c" stopOpacity="0.8" />
                    <stop offset="100%" stopColor="#14b78c" stopOpacity="1" />
                  </linearGradient>
                  <filter id="hero-comet-flare">
                    <feGaussianBlur stdDeviation="3.5" result="coloredBlur" />
                    <feMerge>
                      <feMergeNode in="coloredBlur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>

                <rect width="100%" height="100%" rx="4" fill="#f3ece0" className="shadow-[inset_0_1px_3px_rgba(0,0,0,0.06)]" />

                <motion.rect
                  height="100%" rx="4" fill="url(#hero-bar-grad)"
                  initial={{ width: '0%' }}
                  animate={{ width: ['0%', '100%', '0%'] }}
                  transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
                />

                <motion.circle
                  cy="50%" r="4.5" fill="#ffffff" filter="url(#hero-comet-flare)"
                  initial={{ cx: '0%' }}
                  animate={{ cx: ['0%', '100%', '0%'] }}
                  transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
                />
              </svg>
            </div>

            <div className="w-[90%] py-3 px-4 bg-white border border-[#e8d9c4] rounded-[24px] shadow-[0_5px_15px_-5px_rgba(36,28,21,0.05)] text-center flex items-center justify-center gap-2.5 mt-2">
              <motion.div animate={{ x: [0, 4, 0] }} transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#14b78c" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
              </motion.div>
              <span className="text-[#6e6257] text-[11px] font-semibold uppercase tracking-wider">{t('hero.cardMeta')}</span>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
