import { Link } from 'react-router-dom';
import { useTheme } from '../theme';

export function Logo({ className = '' }: { className?: string }) {
  const { theme: designTheme } = useTheme();

  const logoImg = (
    <picture>
      <source srcSet="/publisco-logo-dark.svg" media="(prefers-color-scheme: dark)" />
      <img src="/publisco-logo.svg" alt="publisco" className={designTheme === 'folder' ? 'h-6 w-auto' : 'h-10 w-auto'} />
    </picture>
  );

  if (designTheme === 'folder') {
    return (
      <Link to="/" className={`tab logo-tab inline-flex w-fit items-center gap-2 ${className}`}>
        {logoImg}
      </Link>
    );
  }

  return (
    <Link to="/" className={`flex items-center ${className}`}>
      <img src="/publisco-logo.svg" alt="publisco" className={'h-10 w-auto'} />

      {/* {logoImg} */}
    </Link>
  );
}
