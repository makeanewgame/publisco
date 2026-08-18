import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { useLocale } from '../i18n';
import { AuthExpiredError } from '../lib/authFetch';
import {
  analyzePdf,
  convertPdf,
  QuotaExceededError,
  type AnalyzeWarning,
  type ConvertProgress,
  type DetectedChapter,
} from '../lib/convertApi';
import { triggerDownload } from '../lib/download';
import { formatBytes } from '../lib/formatBytes';
import { deleteFile, uploadFile } from '../lib/filesApi';
import { getQuota, type QuotaUsageSummary } from '../lib/quotaApi';

const PDF_MIME_TYPE = 'application/pdf';

const LANGUAGE_OPTIONS = [
  { value: 'auto', tesseract: 'auto', labelKey: 'convert.languageAuto' },
  { value: 'tr', tesseract: 'tur', labelKey: 'convert.languageTr' },
  { value: 'en', tesseract: 'eng', labelKey: 'convert.languageEn' },
  { value: 'de', tesseract: 'deu', labelKey: 'convert.languageDe' },
  { value: 'fr', tesseract: 'fra', labelKey: 'convert.languageFr' },
  { value: 'es', tesseract: 'spa', labelKey: 'convert.languageEs' },
  { value: 'it', tesseract: 'ita', labelKey: 'convert.languageIt' },
  { value: 'pt', tesseract: 'por', labelKey: 'convert.languagePt' },
  { value: 'ru', tesseract: 'rus', labelKey: 'convert.languageRu' },
  { value: 'ar', tesseract: 'ara', labelKey: 'convert.languageAr' },
  { value: 'nl', tesseract: 'nld', labelKey: 'convert.languageNl' },
  { value: 'pl', tesseract: 'pol', labelKey: 'convert.languagePl' },
] as const;

function sanitizeFileName(name: string): string {
  return name.replace(/[\\/:*?"<>|]+/g, ' ').trim();
}

function parsePageRange(value: string): { start_page: number; end_page: number } | null {
  const match = value.trim().match(/^(\d+)\s*-\s*(\d+)$/);
  if (!match) {
    return null;
  }
  const start_page = Number(match[1]);
  const end_page = Number(match[2]);
  if (start_page < 1 || end_page < start_page) {
    return null;
  }
  return { start_page, end_page };
}

interface FileAnalysisState {
  status: 'loading' | 'done' | 'error';
  title: string;
  author: string;
  chapters: DetectedChapter[];
  warnings: AnalyzeWarning[];
}

function QuotaBar({
  label,
  used,
  limit,
  formatValue,
}: {
  label: string;
  used: number;
  limit: number | null;
  formatValue: (value: number) => string;
}) {
  const isUnlimited = limit === null;
  const pct = isUnlimited ? 100 : Math.min(100, (used / limit) * 100);
  const isNearLimit = !isUnlimited && pct >= 90;
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-[#6e6257]">
        <span>{label}</span>
        <span>
          {formatValue(used)} / {isUnlimited ? '∞' : formatValue(limit)}
        </span>
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-[#ead8c6]">
        <div
          className={`h-full rounded-full transition-all ${isNearLimit ? 'bg-coral' : 'bg-mint'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

interface FileConversionProgress extends ConvertProgress {
  fileName: string;
}

// Sayfa bazlı canlı yüzde (current_page/total_pages/percent) Modal'ın
// map-reduce mimarisinde takip edilmiyor (paralel container'lar arasında
// toplam ilerleme anlamlı bir şekilde hesaplanamıyor) — bu yüzden belirsiz
// (indeterminate) bir gösterge kullanılıyor.
function ConversionProgressPanel({ progress, t }: { progress: FileConversionProgress; t: (key: string) => string }) {
  return (
    <div className="rounded-[24px] border border-[#e8d9c4] bg-[#fff8ee] p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="font-semibold text-[#241c15]">{progress.fileName}</span>
      </div>
      <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-[#ead8c6]">
        <div className="h-full w-1/3 animate-pulse rounded-full bg-mint" />
      </div>
      <p className="mt-2 text-xs text-[#6e6257]">{t('convert.progress.processingUnknown')}</p>
    </div>
  );
}

export default function ConvertPage() {
  const { t } = useLocale();
  const [file, setFile] = useState<File | null>(null);
  const [fileTypeError, setFileTypeError] = useState(false);
  const [showAuthPrompt, setShowAuthPrompt] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [mode, setMode] = useState<'auto' | 'advanced'>('auto');
  const [showAdvancedModal, setShowAdvancedModal] = useState(false);
  const [bookTitle, setBookTitle] = useState('');
  const [bookAuthor, setBookAuthor] = useState('');
  const [bookLanguage, setBookLanguage] = useState('auto');
  const [pageRange, setPageRange] = useState('');
  const [showValidation, setShowValidation] = useState(false);
  const [isConverting, setIsConverting] = useState(false);
  const [convertError, setConvertError] = useState('');
  const [quotaError, setQuotaError] = useState<QuotaExceededError | null>(null);
  const [quota, setQuota] = useState<QuotaUsageSummary | null>(null);
  const [conversionWarnings, setConversionWarnings] = useState<string[]>([]);
  const [conversionProgress, setConversionProgress] = useState<FileConversionProgress | null>(null);
  const [analysis, setAnalysis] = useState<FileAnalysisState | null>(null);
  const cancelControllerRef = useRef<AbortController | null>(null);

  const WARNING_LABEL_KEYS: Record<AnalyzeWarning, string> = {
    title: 'convert.warningTitle',
    author: 'convert.warningAuthor',
    chapters: 'convert.warningChapters',
  };

  const missingFile = !file;
  const missingTitle = !bookTitle.trim();
  const missingAuthor = !bookAuthor.trim();
  const missingLanguage = !bookLanguage.trim();
  const hasMissingFields = missingFile || missingLanguage || (mode === 'advanced' && (missingTitle || missingAuthor));

  const refreshQuota = () => {
    if (!localStorage.getItem('accessToken')) {
      setQuota(null);
      return;
    }
    getQuota()
      .then(setQuota)
      .catch(() => {
        // Kota widget'ı en iyi çaba (best-effort); yüklenemezse sessizce gizli kalır.
      });
  };

  useEffect(() => {
    refreshQuota();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runAnalysis = async (targetFile: File) => {
    setAnalysis({ status: 'loading', title: '', author: '', chapters: [], warnings: [] });
    try {
      const result = await analyzePdf(targetFile);
      setAnalysis({
        status: 'done',
        title: result.title || targetFile.name.replace(/\.pdf$/i, ''),
        author: result.author || t('convert.unknownAuthor'),
        chapters: result.chapters,
        warnings: result.warnings,
      });
    } catch {
      setAnalysis({
        status: 'error',
        title: targetFile.name.replace(/\.pdf$/i, ''),
        author: t('convert.unknownAuthor'),
        chapters: [],
        warnings: ['title', 'author', 'chapters'],
      });
    }
  };

  const updateAnalysis = (patch: Partial<Pick<FileAnalysisState, 'title' | 'author'>>) => {
    setAnalysis((prev) => (prev ? { ...prev, ...patch } : prev));
  };

  const selectFile = (files: File[]) => {
    const pdfFile = files.find((candidate) => candidate.type === PDF_MIME_TYPE);
    setFileTypeError(!pdfFile);
    if (!pdfFile) {
      return;
    }
    setFile(pdfFile);
    setAnalysis(null);
    if (mode === 'auto') {
      runAnalysis(pdfFile);
    }
  };

  const handleFileSelection = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files && files.length > 0) {
      selectFile(Array.from(files));
    }
    event.target.value = '';
  };

  const handleRemoveFile = () => {
    setFile(null);
    setAnalysis(null);
  };

  const handleConvert = async () => {
    const token = localStorage.getItem('accessToken');
    if (!token) {
      setShowAuthPrompt(true);
      return;
    }
    if (hasMissingFields) {
      setShowValidation(true);
      return;
    }
    setShowValidation(false);
    setConvertError('');
    setConversionWarnings([]);
    setConversionProgress(null);
    setIsConverting(true);

    const controller = new AbortController();
    cancelControllerRef.current = controller;

    const warnings: string[] = [];

    try {
      if (!file) {
        return;
      }

      let title = bookTitle.trim();
      let author = bookAuthor.trim();
      let chapters: DetectedChapter[] = [];

      if (mode === 'auto') {
        // Dosya eklenirken/moda geçilirken tetiklenen analiz genelde çoktan bitmiştir;
        // kullanıcının düzenlediği değerler varsa onlar kullanılır. Bitmemişse (veya
        // hiç tetiklenmemişse) burada bekleyip aynı fallback mantığıyla tamamlanır.
        let currentAnalysis = analysis;
        if (!currentAnalysis || currentAnalysis.status === 'loading') {
          try {
            const result = await analyzePdf(file);
            currentAnalysis = {
              status: 'done',
              title: result.title || file.name.replace(/\.pdf$/i, ''),
              author: result.author || t('convert.unknownAuthor'),
              chapters: result.chapters,
              warnings: result.warnings,
            };
          } catch {
            currentAnalysis = {
              status: 'error',
              title: file.name.replace(/\.pdf$/i, ''),
              author: t('convert.unknownAuthor'),
              chapters: [],
              warnings: ['title', 'author', 'chapters'],
            };
          }
        }

        title = currentAnalysis.title.trim() || file.name.replace(/\.pdf$/i, '');
        author = currentAnalysis.author.trim() || t('convert.unknownAuthor');
        chapters = currentAnalysis.chapters;
        if (currentAnalysis.warnings.length > 0) {
          const labels = currentAnalysis.warnings.map((warning) => t(WARNING_LABEL_KEYS[warning]));
          warnings.push(labels.join(', '));
        }
      }

      const selectedLanguage = LANGUAGE_OPTIONS.find((option) => option.value === bookLanguage);
      const options: { chapters?: DetectedChapter[]; ocr_language: string; start_page?: number; end_page?: number } = {
        ocr_language: selectedLanguage?.tesseract ?? 'auto',
      };
      if (chapters.length > 0) {
        options.chapters = chapters;
      }
      if (mode === 'advanced') {
        const range = parsePageRange(pageRange);
        if (range) {
          options.start_page = range.start_page;
          options.end_page = range.end_page;
        }
      }

      // Kota kontrolü (converter -> storage) API tarafında /convert içinde yapılır;
      // aşım durumunda QuotaExceededError fırlatılır (aşağıdaki catch'te yakalanır).
      const epubBlob = await convertPdf(
        { file, title, author, language: bookLanguage, options },
        (progress) => {
          setConversionProgress({ ...progress, fileName: file.name });
        },
        controller.signal,
      );
      const epubFileName = `${sanitizeFileName(title) || 'book'}.epub`;
      triggerDownload(epubBlob, epubFileName);

      // Kütüphaneye kaydetme en iyi çaba (best-effort): başarısız olsa da indirme akışını bozmasın.
      // Orijinal PDF sadece EPUB'a çevrilmek için kütüphaneye yükleniyor; dönüşüm zaten
      // tamamlandığından PDF'in kendisine artık ihtiyaç yok, yükleme sonrası hemen siliniyor
      // ki blob depolamayı (ve kullanıcının kotasını) boşuna kaplamasın.
      uploadFile(file, file.name)
        .then((asset) =>
          deleteFile(asset.id).catch((error) =>
            console.error('PDF kütüphaneden silinemedi:', error),
          ),
        )
        .catch((error) => console.error('PDF kütüphaneye kaydedilemedi:', error));
      uploadFile(epubBlob, epubFileName).catch((error) => console.error('EPUB kütüphaneye kaydedilemedi:', error));

      setFile(null);
      setAnalysis(null);
      setConversionWarnings(warnings);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        // Kullanıcı "İptal" ile durdurdu — hata olarak gösterme.
      } else if (error instanceof AuthExpiredError) {
        window.location.href = '/auth/signin';
        return;
      } else if (error instanceof QuotaExceededError) {
        setQuotaError(error);
      } else {
        setConvertError(error instanceof Error ? error.message : t('convert.conversionFailed'));
      }
    } finally {
      cancelControllerRef.current = null;
      setIsConverting(false);
      setConversionProgress(null);
      refreshQuota();
    }
  };

  const handleCancelConvert = () => {
    cancelControllerRef.current?.abort();
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragActive(true);
  };

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragActive(false);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragActive(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length === 0) {
      return;
    }
    selectFile(files);
  };

  return (
    <main>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 rounded-[36px] border border-[#e8d9c4] bg-[#fffdf8] p-8 shadow-[0_20px_70px_rgba(36,28,21,0.08)] lg:p-10 my-8">
        <h1 className="text-3xl font-semibold tracking-tight">{t('convert.title')}</h1>

        {quota && (
          <div className="rounded-[24px] border border-[#e8d9c4] bg-[#fff8ee] p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-[#241c15]">{t('convert.quota.heading')}</span>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white ${quota.membershipTier === 'PREMIUM' ? 'bg-[#14b78c]' : 'bg-[#9b8b7e]'
                  }`}
              >
                {quota.membershipTier === 'PREMIUM' ? t('convert.quota.tierPremium') : t('convert.quota.tierFree')}
              </span>
            </div>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <QuotaBar
                label={t('convert.quota.storageLabel')}
                used={quota.storage.usedBytes}
                limit={quota.storage.limitBytes}
                formatValue={formatBytes}
              />
              <QuotaBar
                label={t('convert.quota.converterLabel')}
                used={quota.converter.usedPages}
                limit={quota.converter.limitPages}
                formatValue={(value) => `${value} ${t('convert.quota.pagesUnit')}`}
              />
            </div>
            {quota.membershipTier === 'FREE' && (
              <Link
                to="/premium"
                className="mt-4 inline-block text-sm font-semibold text-[#0c7a5e] transition hover:text-[#14b78c]"
              >
                {t('convert.quota.upgradeLink')}
              </Link>
            )}
          </div>
        )}

        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`relative overflow-hidden rounded-[28px] border border-dashed p-8 text-center transition ${isDragActive ? 'border-[#14b78c] bg-[#ecfdf7]' : 'border-[#f0caa8] bg-[#fff8ee]'
            }`}
        >
          <div className="absolute left-5 top-5 h-10 w-10 rounded-full bg-[#ffd976]/70" />
          <div className="absolute bottom-4 right-6 h-8 w-8 rounded-full bg-[#ffc2d1]/70" />
          <div className="relative mx-auto flex max-w-xl flex-col items-center justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[#14b78c] text-white">
              <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3v14" />
                <path d="m7 10 5-5 5 5" />
                <path d="M5 19h14" />
              </svg>
            </div>
            <p className="mt-4 text-xl font-semibold">{t('convert.dropTitle')}</p>
            <p className="mt-2 text-sm leading-7 text-[#6e6257]">{t('convert.dropDescription')}</p>
            <label className="mt-6 inline-flex cursor-pointer items-center rounded-full bg-mint px-5 py-3 text-sm font-semibold text-white transition hover:bg-mint/90">
              <span>{t('convert.selectFile')}</span>
              <input type="file" accept="application/pdf" className="hidden" onChange={handleFileSelection} />
            </label>
            {fileTypeError && (
              <p className="mt-3 text-sm text-red-600">{t('convert.invalidFileType')}</p>
            )}
            {file && (
              <div className="mt-5 w-full max-w-2xl rounded-[20px] border border-[#ead8c6] bg-[#fff8ee] px-4 py-3 text-left text-sm text-[#241c15]">
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate font-medium">{file.name}</span>
                  <button
                    type="button"
                    onClick={handleRemoveFile}
                    aria-label={t('convert.removeFile')}
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[#9b6b4f] transition hover:bg-[#f6ebdc] hover:text-coral"
                  >
                    <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3 6h18" />
                      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                      <path d="M10 11v6" />
                      <path d="M14 11v6" />
                    </svg>
                  </button>
                </div>

                {mode === 'auto' && analysis?.status === 'loading' && (
                  <p className="mt-2 text-xs text-[#9b8b7e]">{t('convert.analyzing')}</p>
                )}

                {mode === 'auto' && analysis && analysis.status !== 'loading' && (
                  <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                    <label className="flex-1">
                      <span className="mb-1 block text-xs text-[#5f544b]">{t('convert.titleField')}</span>
                      <input
                        className="w-full rounded-full border border-[#ead8c6] bg-[#fffdf8] px-3 py-1.5 text-sm outline-none"
                        value={analysis.title}
                        onChange={(event) => updateAnalysis({ title: event.target.value })}
                      />
                    </label>
                    <label className="flex-1">
                      <span className="mb-1 block text-xs text-[#5f544b]">{t('convert.authorField')}</span>
                      <input
                        className="w-full rounded-full border border-[#ead8c6] bg-[#fffdf8] px-3 py-1.5 text-sm outline-none"
                        value={analysis.author}
                        onChange={(event) => updateAnalysis({ author: event.target.value })}
                      />
                    </label>
                  </div>
                )}

                {mode === 'auto' && analysis && analysis.status !== 'loading' && analysis.chapters.length > 0 && (
                  <p className="mt-2 text-xs text-[#9b8b7e]">
                    {t('convert.chaptersDetectedCount', { count: analysis.chapters.length })}
                  </p>
                )}

                {mode === 'auto' && analysis && analysis.warnings.length > 0 && (
                  <p className="mt-2 text-xs text-amber-700">
                    {analysis.warnings.map((warning) => t(WARNING_LABEL_KEYS[warning])).join(', ')}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="rounded-[24px] border border-[#e8d9c4] bg-[#fff8ee] p-6">
          <h2 className="text-lg font-semibold">{t('convert.settingsHeading')}</h2>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                setMode('auto');
                if (file && !analysis) {
                  runAnalysis(file);
                }
              }}
              className={`rounded-full border px-4 py-2 text-sm font-medium transition ${mode === 'auto' ? 'border-mint bg-mint text-white' : 'border-[#ead8c6] bg-[#fffdf8] text-[#241c15] hover:bg-[#fff5e9]'
                }`}
            >
              {t('convert.modeAuto')}
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('advanced');
                setShowAdvancedModal(true);
              }}
              className={`rounded-full border px-4 py-2 text-sm font-medium transition ${mode === 'advanced' ? 'border-mint bg-mint text-white' : 'border-[#ead8c6] bg-[#fffdf8] text-[#241c15] hover:bg-[#fff5e9]'
                }`}
            >
              {t('convert.modeAdvanced')}
            </button>
          </div>

          <div className="mt-4">
            {mode === 'auto' ? (
              <div className="rounded-[20px] border border-[#ead8c6] bg-[#fffdf8] p-4 text-sm text-[#5f544b]">
                {t('convert.modeAutoDescription')}
              </div>
            ) : (
              <div className="rounded-[20px] border border-[#ead8c6] bg-[#fffdf8] p-4 text-sm">
                <p className="text-[#241c15]">
                  {t('convert.modeAdvancedSummary', { title: bookTitle || '—', author: bookAuthor || '—' })}
                </p>
                <button
                  type="button"
                  onClick={() => setShowAdvancedModal(true)}
                  className="mt-2 font-semibold text-[#0c7a5e] transition hover:text-[#14b78c]"
                >
                  {t('convert.modeAdvancedEdit')}
                </button>
              </div>
            )}
          </div>

          <label className="mt-4 block max-w-xs rounded-[20px] border border-[#ead8c6] bg-[#fffdf8] p-4 text-sm">
            <span className="mb-2 block font-semibold text-[#241c15]">{t('convert.languageField')}</span>
            <select
              className={`w-full rounded-full border bg-[#fffdf8] px-3 py-2 outline-none ${showValidation && missingLanguage ? 'border-red-400' : 'border-[#ead8c6]'}`}
              value={bookLanguage}
              onChange={(event) => setBookLanguage(event.target.value)}
            >
              {LANGUAGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {t(option.labelKey)}
                </option>
              ))}
            </select>
          </label>
        </div>

        {showValidation && hasMissingFields && (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {t('convert.formError')}
          </div>
        )}

        {convertError && (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {convertError}
          </div>
        )}

        {!isConverting && conversionWarnings.length > 0 && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            <p className="font-semibold">{t('convert.conversionWarningsHeading')}</p>
            <ul className="mt-1 list-disc pl-5">
              {conversionWarnings.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          </div>
        )}

        {isConverting && conversionProgress && <ConversionProgressPanel progress={conversionProgress} t={t} />}

        <div className="flex flex-wrap gap-3">
          <Button
            className="rounded-full bg-coral px-6 py-3 text-white hover:bg-coral/90 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={handleConvert}
            disabled={isConverting}
          >
            {isConverting ? t('convert.converting') : t('convert.submit')}
          </Button>
          <Button
            className="rounded-full border-2 border-mint bg-transparent px-6 py-3 text-mint hover:bg-mint-pale disabled:cursor-not-allowed disabled:opacity-60"
            onClick={handleCancelConvert}
            disabled={!isConverting}
          >
            {t('convert.cancel')}
          </Button>
        </div>
      </div>

      {showAuthPrompt && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setShowAuthPrompt(false)}
        >
          <div
            className="w-full max-w-md rounded-[24px] border border-[#a6f4dc] bg-[#ecfdf7] p-6 text-sm text-[#0e614c] shadow-[0_20px_70px_rgba(36,28,21,0.2)]"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="font-semibold">{t('convert.authTitle')}</p>
            <p className="mt-2">{t('convert.authDescription')}</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link to="/auth/signin">
                <Button className="rounded-full border border-[#e8d9c4] bg-[#fffdf8] px-4 py-2 text-[#241c15] hover:bg-[#fff5e9]">{t('convert.authLogin')}</Button>
              </Link>
              <Link to="/auth/signup">
                <Button className="rounded-full bg-mint px-4 py-2 text-white hover:bg-mint/90">{t('convert.authSignup')}</Button>
              </Link>
              <Button
                className="rounded-full bg-transparent px-4 py-2 text-[#0e614c] hover:bg-[#d1faec]"
                onClick={() => setShowAuthPrompt(false)}
              >
                {t('convert.cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {quotaError && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setQuotaError(null)}
        >
          <div
            className="w-full max-w-md rounded-[24px] border border-[#f3c9c9] bg-[#fff5f5] p-6 text-sm text-[#7a2e2e] shadow-[0_20px_70px_rgba(36,28,21,0.2)]"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="font-semibold">
              {quotaError.code === 'CONVERTER_QUOTA_EXCEEDED'
                ? t('convert.quota.converterExceededTitle')
                : t('convert.quota.storageExceededTitle')}
            </p>
            <p className="mt-2">
              {quotaError.code === 'CONVERTER_QUOTA_EXCEEDED'
                ? t('convert.quota.converterExceededDescription')
                : t('convert.quota.storageExceededDescription')}
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              {quotaError.code === 'CONVERTER_QUOTA_EXCEEDED' ? (
                <Link to="/premium">
                  <Button className="rounded-full bg-mint px-4 py-2 text-white hover:bg-mint/90">
                    {t('convert.quota.upgradeCta')}
                  </Button>
                </Link>
              ) : (
                <Link to="/library">
                  <Button className="rounded-full bg-mint px-4 py-2 text-white hover:bg-mint/90">
                    {t('convert.quota.manageStorageCta')}
                  </Button>
                </Link>
              )}
              <Button
                className="rounded-full bg-transparent px-4 py-2 text-[#7a2e2e] hover:bg-[#fbe0e0]"
                onClick={() => setQuotaError(null)}
              >
                {t('convert.cancel')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {showAdvancedModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => setShowAdvancedModal(false)}
        >
          <div
            className="w-full max-w-lg rounded-[24px] border border-[#e8d9c4] bg-[#fffdf8] p-6 text-sm text-[#241c15] shadow-[0_20px_70px_rgba(36,28,21,0.2)]"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="text-lg font-semibold">{t('convert.advancedModalTitle')}</p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <label className="rounded-[20px] border border-[#ead8c6] bg-[#fff8ee] p-4 text-sm">
                <span className="mb-2 block font-semibold text-[#241c15]">{t('convert.titleField')}</span>
                <input
                  className={`w-full rounded-full border bg-[#fffdf8] px-3 py-2 outline-none ${showValidation && missingTitle ? 'border-red-400' : 'border-[#ead8c6]'}`}
                  placeholder={t('convert.titlePlaceholder')}
                  value={bookTitle}
                  onChange={(event) => setBookTitle(event.target.value)}
                />
              </label>
              <label className="rounded-[20px] border border-[#ead8c6] bg-[#fff8ee] p-4 text-sm">
                <span className="mb-2 block font-semibold text-[#241c15]">{t('convert.authorField')}</span>
                <input
                  className={`w-full rounded-full border bg-[#fffdf8] px-3 py-2 outline-none ${showValidation && missingAuthor ? 'border-red-400' : 'border-[#ead8c6]'}`}
                  placeholder={t('convert.authorPlaceholder')}
                  value={bookAuthor}
                  onChange={(event) => setBookAuthor(event.target.value)}
                />
              </label>
              <label className="rounded-[20px] border border-[#ead8c6] bg-[#fff8ee] p-4 text-sm md:col-span-2">
                <span className="mb-2 block font-semibold text-[#241c15]">{t('convert.rangeLabel')}</span>
                <input
                  className="w-full rounded-full border border-[#ead8c6] bg-[#fffdf8] px-3 py-2 outline-none"
                  placeholder={t('convert.rangePlaceholder')}
                  value={pageRange}
                  onChange={(event) => setPageRange(event.target.value)}
                />
              </label>
            </div>
            <div className="mt-4 flex justify-end">
              <Button
                className="rounded-full bg-mint px-5 py-2 text-sm text-white hover:bg-mint/90"
                onClick={() => setShowAdvancedModal(false)}
              >
                {t('convert.advancedModalSave')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
