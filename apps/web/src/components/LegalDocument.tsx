import { Link } from 'react-router-dom';
import { useLocale } from '../i18n';

interface LegalDocumentProps {
  translationKey: string;
  sections: string[];
}

export function LegalDocument({ translationKey, sections }: LegalDocumentProps) {
  const { t } = useLocale();

  return (
    <main>
      <div className="mx-auto flex max-w-3xl flex-col gap-6 rounded-[36px] border border-[#e8d9c4] bg-[#fffdf8] p-8 shadow-[0_20px_70px_rgba(36,28,21,0.08)] lg:p-10 my-8">
        <div>
          <Link to="/" className="text-sm text-[#6e6257] transition hover:text-[#241c15]">
            ← publisco
          </Link>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight">{t(`${translationKey}.title`)}</h1>
          <p className="mt-1 text-xs text-[#9b8b7e]">{t(`${translationKey}.lastUpdated`)}</p>
          <p className="mt-4 text-sm leading-7 text-[#6e6257]">{t(`${translationKey}.intro`)}</p>
        </div>

        <div className="flex flex-col gap-6">
          {sections.map((section) => (
            <div key={section}>
              <h2 className="text-lg font-semibold text-[#241c15]">{t(`${translationKey}.${section}.title`)}</h2>
              <p className="mt-2 text-sm leading-7 text-[#6e6257]">{t(`${translationKey}.${section}.text`)}</p>
            </div>
          ))}
        </div>

        <p className="border-t border-[#e8d9c4] pt-6 text-sm text-[#6e6257]">{t(`${translationKey}.contact`)}</p>
      </div>
    </main>
  );
}
