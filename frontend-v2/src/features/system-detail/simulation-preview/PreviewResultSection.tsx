import type { SimulateBuildResponse, SimulationSummary } from '@/types/api';
import { SimulationResult } from './SimulationResult';
import { GhostMetric, Message } from './components';
import { RegionalContextMini } from './panels';
import { buildPreviewResultGuidance } from './previewResultGuidance';

export function PreviewResultSection({
  regional,
  loadingRegional,
  error,
  result,
  isResultStale,
}: {
  regional: SimulationSummary['regional_context'];
  loadingRegional: boolean;
  error: string | null;
  result: SimulateBuildResponse | null;
  isResultStale: boolean;
}) {
  const guidance = buildPreviewResultGuidance(result, isResultStale);

  return (
    <section aria-label="Preview Result" className="rounded-chunk-lg border border-border/60 bg-bg2/30 p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-mono text-[11px] uppercase tracking-[0.18em] text-silver">Preview Result</h4>
          <p className="mt-1 text-[11px] text-silver-dk font-mono leading-snug">
            Simulation Preview is the explicit action/result that scores the current editable Build Plan.
          </p>
        </div>
      </div>
      <div className="space-y-3">
        <Message tone={guidance.tone} title={guidance.title} items={guidance.items} />
        <RegionalContextMini regional={regional} loading={loadingRegional} />
        {error && <Message tone="danger" items={[error]} />}
        {result && isResultStale && (
          <Message
            tone="warn"
            title="Preview result is stale"
            items={['The Build Plan has changed since this preview was run. Run Preview again to refresh the result.']}
          />
        )}
        {result ? (
          <SimulationResult result={result} />
        ) : (
          <div className="min-h-[260px] rounded-chunk-lg border border-border/60 bg-bg3/25 p-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
              Awaiting preview
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <GhostMetric label="Score" />
              <GhostMetric label="Build" />
              <GhostMetric label="Confidence" />
            </div>
            <div className="mt-5 space-y-2">
              <div className="h-3 w-4/5 rounded bg-bg4/70" />
              <div className="h-3 w-2/3 rounded bg-bg4/50" />
              <div className="h-3 w-1/2 rounded bg-bg4/40" />
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
