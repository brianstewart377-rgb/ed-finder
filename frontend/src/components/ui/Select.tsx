'use client';

import { forwardRef, useId } from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { ChevronDown } from 'lucide-react';
import { cn } from '../../lib/cn';

const sizeStyles = {
  sm: 'text-label py-1.5 pl-2.5 pr-7',
  md: 'text-overline py-2 pl-3.5 pr-8',
} as const;

type SelectSize = keyof typeof sizeStyles;

export interface SelectProps {
  label?: string;
  options: { value: string; label: string; disabled?: boolean }[];
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  size?: SelectSize;
  error?: string;
  className?: string;
}

export const Select = forwardRef<HTMLButtonElement, SelectProps>(
  (
    {
      label,
      options,
      value,
      onChange,
      placeholder = 'Select…',
      size = 'md',
      error,
      className,
    },
    ref,
  ) => {
    const generatedId = useId();
    const id = `select-${generatedId}`;

    const selectedOption = options.find((o) => o.value === value);

    return (
      <div className="space-y-1">
        {label && (
          <label
            htmlFor={id}
            className="block font-mono text-label uppercase tracking-[0.12em] text-silver-dk"
          >
            {label}
          </label>
        )}
        <SelectPrimitive.Root value={value} onValueChange={onChange}>
          <SelectPrimitive.Trigger
            ref={ref}
            id={id}
            aria-invalid={!!error}
            className={cn(
              'group inline-flex w-full items-center justify-between',
              'bg-gradient-to-b from-bg3 to-bg2',
              'border border-border',
              'rounded-chunk-sm',
              'text-text font-ui',
              'shadow-inner-soft',
              'transition-colors duration-fast',
              'focus:outline-none focus:border-orange/65 focus:ring-2 focus:ring-orange/20',
              'disabled:opacity-40 disabled:cursor-not-allowed',
              'data-[placeholder]:text-silver-2',
              error && 'border-red/50 focus:border-red/65 focus:ring-red/20',
              sizeStyles[size],
              className,
            )}
          >
            <SelectPrimitive.Value placeholder={placeholder}>
              {selectedOption?.label}
            </SelectPrimitive.Value>
            <SelectPrimitive.Icon asChild>
              <ChevronDown
                size={14}
                className="text-silver-2 transition-transform duration-fast group-data-[state=open]:rotate-180"
              />
            </SelectPrimitive.Icon>
          </SelectPrimitive.Trigger>

          <SelectPrimitive.Portal>
            <SelectPrimitive.Content
              position="popper"
              sideOffset={4}
              className={cn(
                'z-50 max-h-[300px] min-w-[var(--radix-select-trigger-width)] overflow-hidden',
                'rounded-chunk-sm',
                'border border-silver/20',
                'bg-bg2',
                'shadow-metal',
                'backdrop-blur-xl',
                'animate-fade-up',
              )}
            >
              <SelectPrimitive.ScrollUpButton className="flex items-center justify-center py-1 text-silver-2">
                <ChevronDown size={12} className="rotate-180" />
              </SelectPrimitive.ScrollUpButton>

              <SelectPrimitive.Viewport className="p-1">
                {options.map((option) => (
                  <SelectPrimitive.Item
                    key={option.value}
                    value={option.value}
                    disabled={option.disabled}
                    className={cn(
                      'relative flex items-center rounded-chunk-sm py-1.5 pl-2 pr-8',
                      'font-ui text-overline text-text',
                      'cursor-pointer select-none outline-none',
                      'data-[disabled]:opacity-30 data-[disabled]:cursor-not-allowed',
                      'data-[highlighted]:bg-orange/15 data-[highlighted]:text-orange-lt data-[highlighted]:outline-none',
                      'data-[state=checked]:text-orange data-[state=checked]:font-semibold',
                    )}
                  >
                    <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                  </SelectPrimitive.Item>
                ))}
              </SelectPrimitive.Viewport>

              <SelectPrimitive.ScrollDownButton className="flex items-center justify-center py-1 text-silver-2">
                <ChevronDown size={12} />
              </SelectPrimitive.ScrollDownButton>
            </SelectPrimitive.Content>
          </SelectPrimitive.Portal>
        </SelectPrimitive.Root>
        {error && (
          <p className="text-label text-red" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  },
);

Select.displayName = 'Select';
