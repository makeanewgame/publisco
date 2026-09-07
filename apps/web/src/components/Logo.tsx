import { Link } from 'react-router-dom';

export function Logo({ className = '' }: { className?: string }) {
  return (
    <Link to="/" className={`flex items-center ${className}`}>
      <img src="/publisco-logo.svg" alt="publisco" className={'h-10 w-auto'} />
    </Link>
  );
}
