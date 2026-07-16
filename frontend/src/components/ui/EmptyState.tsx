import { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import { Button } from './Button';
import { Card } from './Card';

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <Card variant="thin" padding="lg" className={cn('text-center', className)}>
      <div className="flex flex-col items-center gap-3 max-w-sm mx-auto">
        {icon && (
          <div className="text-3xl opacity-50 select-none" aria-hidden="true">
            {icon}
          </div>
        )}
        <h3 className="font-display text-sm text-orange tracking-[0.08em]">
          {title}
        </h3>
        {description && (
          <p className="text-overline text-silver-dk leading-relaxed">
            {description}
          </p>
        )}
        {action && (
          <Button variant="metal" size="sm" onClick={action.onClick}>
            {action.label}
          </Button>
        )}
      </div>
    </Card>
  );
}
