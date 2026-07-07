import type { SimulateBuildResponse } from '@/types/api';
import { Chip } from '../components';
import { standardLabel, titleCase } from '../utils/formatters';
import { confidenceLevelTone, levelTone } from '../utils/toneHelpers';

export function DataConfidencePanel({ result }: { result: SimulateBuildResponse }) {
  const qualityRows = Object.entries(result.data_quality ?? {});
  const signals = result.confidence_signals ?? [];
  if (qualityRows.length === 0 && signals.length === 0) return null;
  return (
    <details className="rounded-chunk-lg border border-cyan/25 bg-cyan/5 p-3">
      <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.18em] text-cyan">
        Data Confidence
      </summary>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {qualityRows.map(([area, level]) => (
          <Chip key={area} tone={levelTone(level)}>{titleCase(area)}: {standardLabel(level)}</Chip>
        ))}
      </div>
      {signals.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {signals.slice(0, 5).map((signal) => (
            <div key={`${signal.area}-${signal.reason}`} className="rounded border border-border/60 bg-bg3/45 px-2 py-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10px]">
                <span className="text-silver">{titleCase(signal.area)}</span>
                <span className={confidenceLevelTone(signal.level)}>{standardLabel(signal.level)}</span>
              </div>
              <p className="mt-1 text-[10px] leading-snug text-silver-dk">{signal.reason}</p>
            </div>
          ))}
        </div>
      )}
    </details>
  );
}
