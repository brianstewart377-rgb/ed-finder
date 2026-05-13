import type { SimulateBuildResponse } from '@/types/api';
import { Chip } from '../components';
import { formatObservedValue, titleCase } from '../utils/formatters';

export function ObservedVsPredictedPanel({
  summary,
  diffs,
}: {
  summary: SimulateBuildResponse['observation_summary'];
  diffs: SimulateBuildResponse['prediction_observation_diffs'];
}) {
  if (!summary) return null;
  const hasDiffs = Array.isArray(diffs) && diffs.length > 0;
  return (
    <div className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">
        Observed vs Predicted
      </div>
      <p className="font-mono text-[11px] leading-snug text-silver-dk">{summary.summary}</p>
      <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[10px]">
        <Chip tone={summary.mismatch_count > 0 ? 'warn' : 'good'}>{summary.confirmed_count} confirmed</Chip>
        <Chip tone={summary.mismatch_count > 0 ? 'warn' : 'default'}>{summary.mismatch_count} mismatch</Chip>
        <Chip>{summary.observed_only_count} observed-only</Chip>
        <Chip>{titleCase(summary.confidence_impact)} impact</Chip>
      </div>
      {!hasDiffs && (
        <div className="mt-2 rounded border border-border/50 bg-bg3/45 px-2 py-1.5 font-mono text-[10px] leading-snug text-silver-dk">
          Results are predicted from current mechanics rules.
        </div>
      )}
      {hasDiffs && (
        <details className="mt-3 rounded border border-border/60 bg-bg2/55 px-2 py-2">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-silver">
            Observation Diffs
          </summary>
          <div className="mt-2 space-y-1.5">
            {diffs.slice(0, 8).map((diff) => (
              <div key={`${diff.area}-${diff.subject_id}-${diff.status}`} className="rounded border border-border/50 bg-bg3/45 px-2 py-1.5">
                <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10px]">
                  <span className="text-silver">{titleCase(diff.area)} · {diff.subject_id}</span>
                  <span className={diff.status === 'mismatch' ? 'text-gold' : diff.status === 'confirmed' ? 'text-green' : 'text-silver-dk'}>{titleCase(diff.status)}</span>
                </div>
                <div className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">{diff.reason}</div>
                <div className="mt-1 grid gap-1 font-mono text-[10px] text-silver-dk sm:grid-cols-2">
                  <span><span className="text-silver">Predicted:</span> {formatObservedValue(diff.predicted_value)}</span>
                  <span><span className="text-silver">Observed:</span> {formatObservedValue(diff.observed_value)}</span>
                </div>
                {diff.recommended_action && <div className="mt-1 font-mono text-[10px] leading-snug text-gold">{diff.recommended_action}</div>}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
