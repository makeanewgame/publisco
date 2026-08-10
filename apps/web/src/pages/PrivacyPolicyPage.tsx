import { LegalDocument } from '../components/LegalDocument';

const SECTIONS = [
  'dataCollection',
  'dataUsage',
  'fileRetention',
  'thirdParty',
  'cookies',
  'security',
  'rights',
  'changes',
];

export default function PrivacyPolicyPage() {
  return <LegalDocument translationKey="legal.privacyPolicy" sections={SECTIONS} />;
}
