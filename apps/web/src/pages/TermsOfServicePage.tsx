import { LegalDocument } from '../components/LegalDocument';

const SECTIONS = [
  'acceptance',
  'serviceDescription',
  'accountResponsibility',
  'acceptableUse',
  'plans',
  'intellectualProperty',
  'disclaimer',
  'termination',
  'changes',
];

export default function TermsOfServicePage() {
  return <LegalDocument translationKey="legal.termsOfService" sections={SECTIONS} />;
}
