'use client';

import { forwardRef } from 'react';
import * as CollapsiblePrimitive from '@radix-ui/react-collapsible';
import { ChevronRight } from 'lucide-react';
import { cn } from '../../lib/cn';

export interface CollapsibleProps
  extends React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.Root> {
  /** Clickable header that toggles the section */
  trigger: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

export const Collapsible = forwardRef<HTMLDivElement, CollapsibleProps>(
  (
    { trigger, children, defaultOpen, open, onOpenChange, className, ...props },
    ref,
  ) => {
    return (
      <CollapsiblePrimitive.Root
        open={open}
        defaultOpen={defaultOpen}
        onOpenChange={onOpenChange}
        className={cn('space-y-1', className)}
        {...props}
      >
        <CollapsiblePrimitive.Trigger
          className={cn(
            'group flex w-full items-center gap-1.5',
            'font-mono text-label uppercase tracking-[0.12em] text-silver-dk',
            'hover:text-silver transition-colors duration-fast',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/60 focus-visible:ring-offset-1 focus-visible:ring-offset-bg1 rounded',
          )}
        >
          <ChevronRight
            size={12}
            className="transition-transform duration-fast group-data-[state=open]:rotate-90 text-silver-2"
          />
          {trigger}
        </CollapsiblePrimitive.Trigger>
        <CollapsiblePrimitive.Content
          ref={ref}
          className={cn(
            'overflow-hidden',
            'data-[state=closed]:animate-collapse-up data-[state=open]:animate-collapse-down',
          )}
        >
          <div className="pt-1 space-y-2">{children}</div>
        </CollapsiblePrimitive.Content>
      </CollapsiblePrimitive.Root>
    );
  },
);

Collapsible.displayName = 'Collapsible';
