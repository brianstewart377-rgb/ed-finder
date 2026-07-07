import { BadgeInfo } from 'lucide-react';
import { Chip } from './components';
import type { ColonyRoleHint } from './colonyRoleHintUtils';

export function ColonyRoleHints({
  hints,
  compact = false,
}: {
  hints: ColonyRoleHint[];
  compact?: boolean;
}) {
  if (hints.length === 0) return null;
  const visible = compact ? hints.slice(0, 3) : hints;
  const extra = hints.length - visible.length;

  return (
    <section
      aria-label="Advisory colony role hints"
      data-testid="colony-role-hints"
      className="rounded border border-cyan/20 bg-cyan/5 px-2 py-2"
    >
      <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.14em] text-cyan">
        <BadgeInfo size={12} />
        Role hints
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1.5 font-mono text-[10px]">
        {visible.map((hint) => (
          <Chip key={hint.id} tone={hint.tone === 'good' ? 'good' : hint.tone === 'warn' ? 'warn' : 'default'}>
            {hint.label} - {sourceLabel(hint.source)}
          </Chip>
        ))}
        {extra > 0 && <Chip>+{extra} more</Chip>}
      </div>
      {!compact && (
        <div className="mt-2 space-y-1 font-mono text-[10px] leading-snug text-silver-dk">
          {visible.map((hint) => (
            <p key={`${hint.id}-detail`}>
              <span className="text-silver">{hint.label}:</span> {hint.detail}
            </p>
          ))}
          <p className="text-silver-dk">
            Advisory only: role hints do not edit roles, save role state, run Preview, generate Suggested Builds, or change mechanics.
          </p>
        </div>
      )}
    </section>
  );
}

function sourceLabel(source: ColonyRoleHint['source']): string {
  if (source === 'observed') return 'observed';
  if (source === 'future-editable') return 'future editable';
  return 'inferred';
}
