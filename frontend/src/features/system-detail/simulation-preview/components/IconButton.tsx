import type { ReactNode } from 'react';

export function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="grid h-9 w-9 place-items-center rounded-chunk-sm border border-border bg-bg3 text-silver-dk hover:border-orange/50 hover:text-orange disabled:opacity-35 disabled:cursor-not-allowed"
    >
      {children}
    </button>
  );
}
