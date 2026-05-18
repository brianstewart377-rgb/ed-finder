import { useState } from 'react';
import type { BuildComparisonResult, FacilityCountDelta, NumericDelta, PlacementChange, StringSetChanges } from './types';
import { formatChangeType, formatDeltaValue, formatRiskDirection, formatVerdictLabel } from './comparisonFormatters';

export function OptimiserComparisonPanel({ result }: { result?: BuildComparisonResult | null }) {
  const [expanded, setExpanded] = useState(true);

  if (!result) {
    return (
      <section className="rounded border border-border/45 bg-bg3/20 px-3 py-2" aria-label="Optimiser comparison">
        <h5 className="font-mono text-[10px] uppercase tracking-[0.16em] text-silver-dk">Compare with current plan</h5>
        <p className="mt-1 text-[11px] text-silver-dk">
          Comparison needs a current Build Plan. Add placements or copy a Suggested Build to compare changes.
        </p>
      </section>
    );
  }

  const verdictLabel = formatVerdictLabel(result.recommendation.verdict);

  return (
    <section className="rounded-chunk-lg border border-cyan/30 bg-cyan/5" aria-label="Optimiser comparison">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyan/20 px-3 py-2">
        <div className="min-w-0">
          <h5 className="font-mono text-[10px] uppercase tracking-[0.16em] text-cyan">Compare with current plan</h5>
          <div className="mt-1 text-sm font-semibold text-silver">{verdictLabel}</div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="rounded border border-cyan/40 bg-bg2/80 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-cyan hover:bg-cyan/10"
          aria-expanded={expanded}
        >
          {expanded ? 'Hide comparison' : 'Show comparison'}
        </button>
      </div>

      {expanded && (
        <div className="space-y-3 px-3 py-3">
          <p className="text-[11px] text-silver-dk">
            This comparison is advisory and preview-only. It does not run Simulation Preview, save a build, or commit anything in-game.
          </p>

          <div className="rounded border border-border/45 bg-bg1/40 px-3 py-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">Verdict</div>
            <div className="mt-1 text-sm font-semibold text-silver">{verdictLabel}</div>
            {result.recommendation.reasons.length > 0 && (
              <ul className="mt-1 space-y-1 text-[11px] text-silver-dk">
                {result.recommendation.reasons.map((reason) => <li key={reason}>• {reason}</li>)}
              </ul>
            )}
          </div>

          <ListSection title="Tradeoff summary" items={result.tradeoff_summary} empty="No major placement changes detected." />

          {result.target_archetype_changed && (
            <ListSection
              title="Target archetype"
              items={[`Changes from ${result.before_target_archetype ?? 'unknown'} to ${result.after_target_archetype ?? 'unknown'}.`]}
              empty="Target archetype is unchanged."
            />
          )}

          <FacilityDeltaSection deltas={result.facility_count_deltas} />
          <PlacementDeltaSection result={result} />
          <PreviewDeltaSection result={result} />
          <RankingDeltaSection result={result} />
          <RiskSection result={result} />
          <SetChangeSection title="Warning changes" changes={result.warning_changes} />
          <SetChangeSection title="Assumption changes" changes={result.assumption_changes} />
        </div>
      )}
    </section>
  );
}

function FacilityDeltaSection({ deltas }: { deltas: FacilityCountDelta[] }) {
  if (deltas.length === 0) {
    return <ListSection title="Facility count changes" items={[]} empty="No facility count changes." />;
  }
  return (
    <ListSection
      title="Facility count changes"
      items={deltas.map((delta) => `${delta.facility_template_id}: ${delta.before_count} → ${delta.after_count} (${delta.delta > 0 ? '+' : ''}${delta.delta})`)}
      empty="No facility count changes."
    />
  );
}

function PlacementDeltaSection({ result }: { result: BuildComparisonResult }) {
  const items = [
    ...result.added_facilities.map((change) => placementText(change)),
    ...result.removed_facilities.map((change) => placementText(change)),
    ...result.changed_placements.map((change) => placementText(change)),
  ];
  return <ListSection title="Placement changes" items={items} empty="No major placement changes detected." />;
}

function PreviewDeltaSection({ result }: { result: BuildComparisonResult }) {
  const items = [
    metricText('Final score', result.preview_summary_delta.final_score, ' pts'),
    metricText('Composition', result.preview_summary_delta.composition_score, ' pts'),
    metricText('Buildability', result.preview_summary_delta.buildability_score, ' pts'),
    metricText('Confidence', result.preview_summary_delta.confidence),
  ];
  const allUnknown = Object.values(result.preview_summary_delta).every((delta) => delta.direction === 'unknown');
  return (
    <ListSection
      title="Preview summary deltas"
      items={allUnknown ? [] : items}
      empty="Preview-score deltas are unavailable until both sides have summary data."
    />
  );
}

function RankingDeltaSection({ result }: { result: BuildComparisonResult }) {
  const ranking = result.ranking_delta;
  if (!ranking || ranking.direction === 'unknown') {
    return <ListSection title="Ranking delta" items={[]} empty="Ranking delta is unavailable for the current manual Build Plan." />;
  }
  return (
    <ListSection
      title="Ranking delta"
      items={[
        `Rank: ${ranking.before_rank ?? 'unknown'} → ${ranking.after_rank ?? 'unknown'}`,
        `Rank score: ${ranking.before_rank_score ?? 'unknown'} → ${ranking.after_rank_score ?? 'unknown'} (${ranking.rank_score_delta != null && ranking.rank_score_delta > 0 ? '+' : ''}${ranking.rank_score_delta ?? 'unknown'})`,
        `Tier: ${ranking.before_rank_tier ?? 'unknown'} → ${ranking.after_rank_tier ?? 'unknown'}`,
      ]}
      empty="Ranking delta is unavailable for the current manual Build Plan."
    />
  );
}

function RiskSection({ result }: { result: BuildComparisonResult }) {
  const risk = result.risk_delta;
  const items = [
    `Risk direction: ${formatRiskDirection(risk.risk_direction)}`,
    `Warning count: ${risk.warning_count.before ?? 'unknown'} → ${risk.warning_count.after ?? 'unknown'} (${formatDeltaValue(risk.warning_count)})`,
  ];
  if (risk.cp_negative_changed) {
    items.push(`CP risk: ${risk.before_cp_negative ? 'present' : 'absent'} → ${risk.after_cp_negative ? 'present' : 'absent'}`);
  }
  return <ListSection title="Risk changes" items={items} empty="Risk changes are unavailable." />;
}

function SetChangeSection({ title, changes }: { title: string; changes: StringSetChanges }) {
  const items = [
    changes.added.length > 0 ? `Added: ${changes.added.join('; ')}` : '',
    changes.removed.length > 0 ? `Removed: ${changes.removed.join('; ')}` : '',
    `Shared items: ${changes.shared.length}`,
  ].filter(Boolean);
  return <ListSection title={title} items={items} empty={`No ${title.toLowerCase()}.`} />;
}

function ListSection({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="rounded border border-border/45 bg-bg1/30 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">{title}</div>
      {items.length > 0 ? (
        <ul className="mt-1 space-y-1 text-[11px] text-silver-dk">
          {items.map((item) => <li key={`${title}-${item}`}>• {item}</li>)}
        </ul>
      ) : (
        <p className="mt-1 text-[11px] text-silver-dk">{empty}</p>
      )}
    </div>
  );
}

function placementText(change: PlacementChange): string {
  const body = change.before_body_id !== change.after_body_id
    ? ' body assignment changed'
    : change.after_body_id || change.before_body_id
      ? ' body assigned'
      : ' unassigned';
  const order = change.before_build_order !== change.after_build_order
    ? ` order ${change.before_build_order ?? 'none'} → ${change.after_build_order ?? 'none'}`
    : '';
  return `${change.facility_template_id}: ${formatChangeType(change.change_type)};${body}${order}`;
}

function metricText(label: string, delta: NumericDelta, suffix = ''): string {
  if (delta.direction === 'unknown') return `${label}: unknown`;
  return `${label}: ${delta.before ?? 'unknown'} → ${delta.after ?? 'unknown'} (${formatDeltaValue(delta, suffix)})`;
}
