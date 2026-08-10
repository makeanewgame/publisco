import * as React from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface PasswordInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  toggleLabel?: { show: string; hide: string };
}

const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ className, toggleLabel, ...props }, ref) => {
    const [visible, setVisible] = React.useState(false);

    return (
      <div className={cn('relative', className)}>
        <input
          type={visible ? 'text' : 'password'}
          className="w-full rounded-full border border-[#ead8c6] bg-[#fffdf8] px-4 py-3 pr-12 text-sm outline-none"
          ref={ref}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((prev) => !prev)}
          aria-label={visible ? toggleLabel?.hide ?? 'Hide password' : toggleLabel?.show ?? 'Show password'}
          tabIndex={-1}
          className="absolute inset-y-0 right-4 flex items-center text-[#9b8b7e] transition hover:text-[#241c15]"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    );
  },
);
PasswordInput.displayName = 'PasswordInput';

export { PasswordInput };
