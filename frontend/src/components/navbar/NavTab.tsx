import { Badge } from '../ui/Badge';

export function NavTab({ label, active, onClick, testid, badge, title, compact = false }: {
  label:   string;
  active:  boolean;
  onClick: () => void;
  testid:  string;
  badge?:  number;
  title?:  string;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      title={title}
      aria-current={active ? 'page' : undefined}
      className={[
        'group relative inline-flex items-center gap-1.5 px-3.5 py-2 rounded-chunk-sm whitespace-nowrap',
        compact ? 'w-full justify-between' : '',
        'font-display font-bold text-[12.5px] tracking-[0.1em] uppercase',
        'transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/80',
        active
          ? 'text-white shadow-brand-glow'
          : 'text-silver hover:text-white hover:bg-bg3/70',
      ].join(' ')}
      style={active ? {
        background: 'linear-gradient(180deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0) 20%), linear-gradient(180deg, rgba(255,122,20,0.3) 0%, rgba(255,122,20,0.12) 100%)',
        border: '1px solid rgba(255,122,20,0.55)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08), 0 10px 24px -18px rgba(255,122,20,0.75)',
      } : {
        border: '1px solid rgba(148,163,184,0.08)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.02)',
      }}
    >
      <span>{label}</span>
      {badge !== undefined && badge > 0 && (
        <Badge
          count={badge > 99 ? '99+' : badge}
          variant="orange"
          size="sm"
        />
      )}
      {active && (
        <span
          className="absolute -bottom-[7px] left-1/2 -translate-x-1/2 h-[3px] w-8 rounded-full"
          style={{ background: 'linear-gradient(90deg, transparent, #ff7a14, transparent)' }}
        />
      )}
    </button>
  );
}
