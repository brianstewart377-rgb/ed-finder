// HUD primitives — chunky rounded brushed-steel panels matching reference images.
import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';

export function Panel({ children, className = '', active = false, ...rest }) {
  const cls = [
    'panel',
    active ? 'panel-active' : '',
    className,
  ].filter(Boolean).join(' ');
  return <div className={cls} {...rest}>{children}</div>;
}

export function GlassPanel({ children, className = '', ...rest }) {
  return <div className={`glass ${className}`} {...rest}>{children}</div>;
}

export function Readout({ children, className = '', size = 'md' }) {
  const sz = size === 'sm' ? 'px-2 py-0.5 text-[10px]'
           : size === 'lg' ? 'px-3 py-1.5 text-sm'
           : 'px-2.5 py-1 text-xs';
  return <span className={`readout font-mono ${sz} ${className}`}>{children}</span>;
}

export function PanelHeader({ icon, title, sub, right, className = '' }) {
  return (
    <header className={`flex items-center gap-2.5 px-4 py-3 border-b border-[hsla(232,22%,60%,0.22)] ${className}`}>
      {icon && (
        <span className="text-[var(--ed-orange-lt)] text-glow-orange flex-shrink-0">{icon}</span>
      )}
      <div className="min-w-0 flex-1">
        <div className="font-display text-[12px] tracking-[0.2em] text-[var(--steel-100)] truncate">{title}</div>
        {sub && <div className="text-[10px] text-[var(--steel-400)] font-mono truncate mt-0.5">{sub}</div>}
      </div>
      {right}
    </header>
  );
}

// ── Section panel with header banner — the look from the reference images ──
export function SectionPanel({ icon, title, right, defaultOpen = true, collapsible = true, children, className = '' }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`section-panel ${className}`}>
      <button
        type="button"
        onClick={() => collapsible && setOpen((v) => !v)}
        className="section-panel-header w-full text-left group"
        style={{ cursor: collapsible ? 'pointer' : 'default' }}
      >
        {icon && <span className="text-[var(--ed-orange-lt)] flex-shrink-0">{icon}</span>}
        <span className="font-display text-[11px] tracking-[0.22em] text-[var(--steel-100)] flex-1">{title}</span>
        {right}
        {collapsible && (
          <ChevronDown
            size={14}
            strokeWidth={2}
            className={`text-[var(--steel-400)] transition-transform ${open ? '' : '-rotate-90'}`}
          />
        )}
      </button>
      <div
        className={`overflow-hidden transition-[max-height] duration-300 ease-out ${open ? '' : 'max-h-0'}`}
        style={open ? { maxHeight: '4000px' } : undefined}
      >
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function SectionLabel({ children, className = '' }) {
  return (
    <div className={`flex items-center gap-2 mb-1.5 ${className}`}>
      <span className="font-display text-[9px] tracking-[0.22em] text-[var(--steel-400)]">{children}</span>
      <span className="flex-1 h-px bg-[hsla(232,22%,60%,0.2)]" />
    </div>
  );
}

export function RatingBar({ score, label, color, size = 'md' }) {
  const w = size === 'sm' ? 'h-[3px]' : size === 'lg' ? 'h-1.5' : 'h-1';
  const pct = Math.max(0, Math.min(100, score ?? 0));
  return (
    <div className="flex items-center gap-2 min-w-0">
      {label && (
        <span className="font-mono text-[9px] uppercase tracking-wider text-[var(--steel-400)] w-[68px] flex-shrink-0">{label}</span>
      )}
      <div className={`relative flex-1 ${w} bg-[hsla(232,22%,15%,0.85)] rounded-full overflow-hidden`}>
        <div
          className={`absolute inset-y-0 left-0 ${w} rounded-full`}
          style={{
            width: `${pct}%`,
            background: color,
            boxShadow: `0 0 8px ${color}66`,
          }}
        />
      </div>
      <span className="font-mono text-[10px] text-[var(--steel-200)] w-7 text-right tabular-nums">{score ?? '—'}</span>
    </div>
  );
}

export function TierPill({ score, tier }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 font-display text-[9px] tracking-[0.18em] rounded-full border"
      style={{
        color: tier.color,
        borderColor: `${tier.color}88`,
        background: `${tier.color}1a`,
        boxShadow: `0 0 10px ${tier.color}33, inset 0 1px 0 ${tier.color}33`,
      }}
    >
      <span className="font-mono text-[12px] font-bold tabular-nums">{score ?? '—'}</span>
      <span>{tier.label}</span>
    </span>
  );
}

export function HudButton({ children, active = false, onClick, className = '', icon: Icon, size = 'md', title, ...rest }) {
  const sz = size === 'sm' ? 'px-2.5 py-1.5 text-[10px]' : 'px-3.5 py-2 text-[11px]';
  return (
    <button
      onClick={onClick}
      title={title}
      className={[
        'font-display tracking-[0.14em] inline-flex items-center gap-1.5 border transition-all rounded-full',
        sz,
        active
          ? 'bg-[hsla(22,100%,50%,0.18)] text-[var(--ed-orange-lt)] border-[hsla(22,100%,50%,0.5)] shadow-[0_0_14px_hsla(22,100%,50%,0.3)]'
          : 'bg-[hsla(232,18%,28%,0.6)] text-[var(--steel-300)] border-[hsla(232,22%,60%,0.32)] hover:text-[var(--steel-100)] hover:border-[hsla(232,30%,75%,0.5)] hover:bg-[hsla(232,18%,38%,0.6)]',
        className,
      ].join(' ')}
      {...rest}
    >
      {Icon && <Icon size={12} strokeWidth={1.75} />}
      {children}
    </button>
  );
}

export function KeyHint({ k, label }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[9px] text-[var(--steel-400)] font-mono">
      <kbd className="px-1.5 py-0.5 bg-[hsla(232,30%,12%,0.85)] border border-[hsla(232,22%,60%,0.32)] rounded-[4px] text-[var(--steel-200)] tabular-nums">
        {k}
      </kbd>
      {label}
    </span>
  );
}

// ── Pill toggle (matches Feature Filters in reference image) ──
export function ToggleSwitch({ checked, onChange, size = 'md' }) {
  const w = size === 'sm' ? 32 : 40;
  const h = size === 'sm' ? 18 : 22;
  const tx = size === 'sm' ? 14 : 18;
  return (
    <span
      onClick={() => onChange?.(!checked)}
      className="relative cursor-pointer flex-shrink-0 transition-colors"
      style={{
        width: w,
        height: h,
        borderRadius: 999,
        background: checked
          ? 'linear-gradient(180deg, var(--ed-orange-lt) 0%, var(--ed-orange) 100%)'
          : 'hsla(232, 30%, 8%, 0.85)',
        border: `1px solid ${checked ? 'hsla(22, 100%, 35%, 0.9)' : 'hsla(232, 22%, 50%, 0.4)'}`,
        boxShadow: checked
          ? '0 0 12px hsla(22, 100%, 50%, 0.5), inset 0 1px 0 hsla(45, 95%, 65%, 0.4)'
          : 'inset 0 1px 2px hsla(248, 60%, 0%, 0.5)',
      }}
    >
      <span
        className="absolute top-1/2 -translate-y-1/2 transition-all"
        style={{
          left: checked ? `calc(100% - ${tx + 3}px)` : '3px',
          width: tx,
          height: h - 6,
          borderRadius: 999,
          background: checked
            ? 'linear-gradient(180deg, #fff8eb 0%, #ffd9a0 100%)'
            : 'linear-gradient(180deg, hsl(232, 18%, 88%) 0%, hsl(232, 14%, 75%) 100%)',
          boxShadow: '0 1px 2px hsla(0,0%,0%,0.4)',
        }}
      />
    </span>
  );
}
