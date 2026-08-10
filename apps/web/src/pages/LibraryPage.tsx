import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { useLocale } from '../i18n';
import { AuthExpiredError } from '../lib/authFetch';
import { triggerDownload } from '../lib/download';
import { formatBytes } from '../lib/formatBytes';
import { deleteFile, fetchFileBlob, listFiles, type FileAsset } from '../lib/filesApi';

type FileType = 'EPUB' | 'PDF' | '—';

function fileTypeLabel(file: FileAsset): FileType {
  if (file.contentType === 'application/epub+zip' || /\.epub$/i.test(file.fileName)) {
    return 'EPUB';
  }
  if (file.contentType === 'application/pdf' || /\.pdf$/i.test(file.fileName)) {
    return 'PDF';
  }
  return '—';
}

function FileTypeIcon({ type }: { type: FileType }) {
  const common = 'h-4 w-4';
  if (type === 'EPUB') {
    return (
      <svg viewBox="0 0 24 24" fill="none" className={common} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 5.5C4 4.67 4.67 4 5.5 4H11a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H5.5A1.5 1.5 0 0 1 4 16.5v-11Z" />
        <path d="M20 5.5c0-.83-.67-1.5-1.5-1.5H13a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h5.5c.83 0 1.5-.67 1.5-1.5v-11Z" />
      </svg>
    );
  }
  if (type === 'PDF') {
    return (
      <svg viewBox="0 0 24 24" fill="none" className={common} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M7 3h7l5 5v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
        <path d="M14 3v5h5" />
      </svg>
    );
  }
  return null;
}

export default function LibraryPage() {
  const { locale, t } = useLocale();
  const [files, setFiles] = useState<FileAsset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  const setPending = (id: string, pending: boolean) => {
    setPendingIds((prev) => {
      const next = new Set(prev);
      if (pending) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };

  const loadFiles = () => {
    setIsLoading(true);
    setLoadError('');
    listFiles()
      .then(setFiles)
      .catch((error) => {
        if (error instanceof AuthExpiredError) {
          window.location.href = '/auth/signin';
          return;
        }
        setLoadError(t('library.loadError'));
      })
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    loadFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDownload = async (file: FileAsset) => {
    setActionError('');
    setPending(file.id, true);
    try {
      const blob = await fetchFileBlob(file.id);
      triggerDownload(blob, file.fileName);
    } catch (error) {
      if (error instanceof AuthExpiredError) {
        window.location.href = '/auth/signin';
        return;
      }
      setActionError(t('library.downloadError'));
    } finally {
      setPending(file.id, false);
    }
  };

  const handleDelete = async (file: FileAsset) => {
    setActionError('');
    setPending(file.id, true);
    try {
      await deleteFile(file.id);
      setFiles((prev) => prev.filter((item) => item.id !== file.id));
    } catch (error) {
      if (error instanceof AuthExpiredError) {
        window.location.href = '/auth/signin';
        return;
      }
      setActionError(t('library.deleteError'));
    } finally {
      setPending(file.id, false);
    }
  };

  const dateFormatter = new Intl.DateTimeFormat(locale === 'tr' ? 'tr-TR' : 'en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });

  return (
    <main>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 rounded-[36px] border border-[#e8d9c4] bg-[#fffdf8] p-8 shadow-[0_20px_70px_rgba(36,28,21,0.08)] lg:p-10 my-8">
        <h1 className="text-3xl font-semibold tracking-tight">{t('library.title')}</h1>

        {actionError && (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {actionError}
          </div>
        )}

        <div className="rounded-[24px] border border-[#e8d9c4] bg-[#fff8ee] p-6">
          {isLoading ? (
            <p className="text-sm text-[#6e6257]">{t('library.loading')}</p>
          ) : loadError ? (
            <p className="text-sm text-red-600">{loadError}</p>
          ) : files.length === 0 ? (
            <p className="text-sm text-[#6e6257]">{t('library.empty')}</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {files.map((file) => {
                const pending = pendingIds.has(file.id);
                const sizeLabel = formatBytes(file.size);
                const typeLabel = fileTypeLabel(file);
                return (
                  <li
                    key={file.id}
                    className="flex flex-col gap-3 rounded-[20px] border border-[#ead8c6] bg-[#fffdf8] p-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span
                        className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white ${typeLabel === 'PDF' ? 'bg-coral' : 'bg-[#14b78c]'
                          }`}
                      >
                        <FileTypeIcon type={typeLabel} />
                        {typeLabel}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-[#241c15]">{file.fileName}</p>
                        <p className="text-xs text-[#9b8b7e]">
                          {dateFormatter.format(new Date(file.createdAt))}
                          {sizeLabel && ` • ${sizeLabel}`}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button
                        className="rounded-full border border-[#ead8c6] bg-[#fffdf8] px-4 py-2 text-sm text-[#241c15] hover:bg-[#fff5e9] disabled:cursor-not-allowed disabled:opacity-60"
                        onClick={() => handleDownload(file)}
                        disabled={pending}
                      >
                        {t('library.download')}
                      </Button>
                      <button
                        type="button"
                        onClick={() => handleDelete(file)}
                        disabled={pending}
                        aria-label={t('library.delete')}
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#9b6b4f] transition hover:bg-[#f6ebdc] hover:text-coral disabled:cursor-not-allowed disabled:opacity-60"
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
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </main>
  );
}
