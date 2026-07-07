import type { SimulateBuildResponse } from '@/types/api';
import { Chip } from '../components';
import { purityLabel, purityTone } from '../utils/toneHelpers';

export function InheritedEconomyPanel({ profiles }: { profiles: SimulateBuildResponse['inherited_economies'] }) {
  if (!profiles || profiles.length === 0) return null;
  return (
    <div className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">
        Mixed inheritance
      </div>
      <div className="space-y-3">
        {profiles.map((profile, index) => {
          const rows = Object.entries(profile.weights).sort((a, b) => b[1] - a[1]);
          return (
            <div key={`${profile.source_body_id ?? 'body'}-${index}`} className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-silver">
                <span>{profile.source_body_name || (profile.source_body_id ? `Body ${profile.source_body_id}` : 'Inherited body')}</span>
                <span className={purityTone(profile.purity)}>{purityLabel(profile.purity)} purity</span>
              </div>
              <div className="space-y-1.5">
                {rows.map(([economy, weight]) => (
                  <div key={economy} className="grid grid-cols-[92px_minmax(0,1fr)_44px] items-center gap-2">
                    <span className="truncate font-mono text-[10px] text-silver-dk">{economy}</span>
                    <div className="h-2 overflow-hidden rounded-full border border-border bg-bg4">
                      <div
                        className="h-full rounded-full bg-cyan"
                        style={{ width: `${Math.max(4, Math.min(100, weight * 100))}%` }}
                      />
                    </div>
                    <span className="text-right font-mono text-[10px] text-cyan tabular-nums">{Math.round(weight * 100)}%</span>
                  </div>
                ))}
              </div>
              {profile.modifier_economies.length > 0 && (
                <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
                  {profile.modifier_economies.map((economy) => <Chip key={economy} tone="warn">{economy} modifier</Chip>)}
                </div>
              )}
              {profile.caveats.slice(0, 2).map((caveat) => (
                <div key={caveat} className="rounded border border-gold/30 bg-gold/5 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
                  {caveat}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
