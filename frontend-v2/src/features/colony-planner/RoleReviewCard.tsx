import { roleCompactLabel } from './colonyRoles';
import type { RoleReviewResult } from './colonyRoleReview';

export function RoleReviewCard({
  title = 'Strategic Role Review',
  result,
  compact = false,
}: {
  title?: string;
  result: RoleReviewResult;
  compact?: boolean;
}) {
  const toneClass = result.consistency === 'aligned'
    ? 'border-green/35 bg-green/10 text-green'
    : result.consistency === 'diverging'
      ? 'border-gold/40 bg-gold/10 text-gold'
      : result.consistency === 'partial'
        ? 'border-cyan/30 bg-cyan/5 text-cyan'
        : 'border-border/60 bg-bg3/45 text-silver-dk';

  return (
    <section
      data-testid="strategic-role-review-card"
      className="rounded-chunk-lg border border-cyan/25 bg-bg3/35 px-3 py-2 font-mono text-[11px] leading-snug text-silver-dk"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[10px] uppercase tracking-[0.16em] text-cyan">{title}</div>
        <span className={['rounded border px-2 py-1 text-[10px] uppercase tracking-[0.12em]', toneClass].join(' ')}>
          {result.consistencyLabel}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
        <span className="rounded border border-green/35 bg-green/10 px-1.5 py-0.5 uppercase tracking-[0.12em] text-green">
          Declared Strategy: {result.coverage.declaredCount}
        </span>
        <span className="rounded border border-orange/35 bg-orange/10 px-1.5 py-0.5 uppercase tracking-[0.12em] text-orange">
          Observed Colony State: {result.coverage.observedCount}
        </span>
        <span className="rounded border border-cyan/30 bg-cyan/5 px-1.5 py-0.5 uppercase tracking-[0.12em] text-cyan">
          Matched: {result.coverage.matchedCount}
        </span>
        {result.coverage.mismatchCount > 0 && (
          <span className="rounded border border-gold/35 bg-gold/10 px-1.5 py-0.5 uppercase tracking-[0.12em] text-gold">
            Mismatch: {result.coverage.mismatchCount}
          </span>
        )}
      </div>
      {!compact && (
        <>
          <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
            {result.declaredRoles.slice(0, 4).map((role) => (
              <span key={role.id} className="rounded border border-green/35 bg-green/10 px-1.5 py-0.5 uppercase tracking-[0.12em] text-green">
                Declared: {roleCompactLabel(role.role_id)}
              </span>
            ))}
            {result.observedRoles.slice(0, 4).map((role) => (
              <span key={role.id} className="rounded border border-orange/35 bg-orange/10 px-1.5 py-0.5 uppercase tracking-[0.12em] text-orange">
                {role.label}
              </span>
            ))}
          </div>
          <div className="mt-2 space-y-1">
            {result.summaries.map((summary) => (
              <p key={summary}>{summary}</p>
            ))}
          </div>
          {result.conflicts.length > 0 && (
            <div className="mt-2 space-y-1 text-gold">
              {result.conflicts.map((conflict) => <p key={conflict}>{conflict}</p>)}
            </div>
          )}
          <p className="mt-2 border-t border-cyan/15 pt-2 text-[10px]">
            Review-only: role review never changes declared strategy, observed evidence, Preview, Suggested Builds, scoring, or mechanics.
          </p>
        </>
      )}
    </section>
  );
}
