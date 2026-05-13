import type { SimulateBuildResponse } from '@/types/api';
import { Chip } from '../components';
import { titleCase } from '../utils/formatters';
import { repairSeverityTone } from '../utils/toneHelpers';

export function CpRepairPanel({ suggestions }: { suggestions: SimulateBuildResponse['cp_repair_suggestions'] }) {
  if (!suggestions || suggestions.length === 0) return null;
  const order: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
  const sorted = [...suggestions].sort((a, b) => (order[a.severity] ?? 99) - (order[b.severity] ?? 99));
  return (
    <div className="rounded-chunk-lg border border-gold/35 bg-gold/5 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-gold">
        CP Repair Suggestions
      </div>
      <div className="space-y-2">
        {sorted.slice(0, 3).map((suggestion) => (
          <div key={`${suggestion.type}-${suggestion.summary}-${suggestion.affected_steps.join('-')}`} className="rounded border border-border/60 bg-bg3/45 px-2 py-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-mono text-[11px] text-silver">{suggestion.summary}</div>
                <div className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">{suggestion.reason}</div>
              </div>
              <Chip tone={repairSeverityTone(suggestion.severity)}>{titleCase(suggestion.severity)} priority</Chip>
            </div>
            <div className="mt-2 grid gap-1.5 font-mono text-[10px] text-silver-dk sm:grid-cols-2">
              <div><span className="text-silver">Expected effect:</span> {suggestion.expected_effect}</div>
              <div><span className="text-silver">Action:</span> {suggestion.action}</div>
              {suggestion.affected_steps.length > 0 && <div><span className="text-silver">Affected steps:</span> {suggestion.affected_steps.join(', ')}</div>}
              <div><span className="text-silver">Confidence:</span> {titleCase(suggestion.confidence)}</div>
            </div>
            {(suggestion.caveats.length > 0 || suggestion.suggested_action) && (
              <details className="mt-2 rounded border border-border/50 bg-bg2/45 px-2 py-1">
                <summary className="cursor-pointer font-mono text-[10px] text-gold">Caveats and structured action</summary>
                <div className="mt-1 space-y-1 font-mono text-[10px] leading-snug text-silver-dk">
                  {suggestion.caveats.map((caveat) => <div key={caveat}>{caveat}</div>)}
                  {suggestion.suggested_action && (
                    <div>
                      <span className="text-silver">Action type:</span> {titleCase(suggestion.suggested_action.action_type)}
                      {suggestion.suggested_action.facility_name && <span> · {suggestion.suggested_action.facility_name}</span>}
                      {suggestion.suggested_action.from_step != null && <span> · from step {suggestion.suggested_action.from_step}</span>}
                      {suggestion.suggested_action.to_step != null && <span> · to step {suggestion.suggested_action.to_step}</span>}
                      {suggestion.suggested_action.target_step != null && <span> · target step {suggestion.suggested_action.target_step}</span>}
                    </div>
                  )}
                  {suggestion.suggested_action?.notes.map((note) => <div key={note}>{note}</div>)}
                </div>
              </details>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
