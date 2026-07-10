import { buildCockpitIntelligence } from './cockpitIntelligence';
import type { ReviewPreviewStatus } from './ReviewWorkflowRail';
import type { FacilityTemplate, SimulateBuildPlacement, SystemBody } from '@/types/api';

export function CockpitIntelligencePanel({
  placements,
  templates,
  bodies,
  previewStatus,
  observedFactsCount,
  exportBlockerCount = 0,
}: {
  placements: SimulateBuildPlacement[];
  templates: FacilityTemplate[];
  bodies: SystemBody[];
  previewStatus: ReviewPreviewStatus;
  observedFactsCount: number;
  exportBlockerCount?: number;
}) {
  const snapshot = buildCockpitIntelligence({
    placements,
    templates,
    bodies,
    previewStatus,
    observedFactsCount,
    exportBlockerCount,
  });

  return (
    <section
      data-testid="cockpit-intelligence-panel"
      className="border-b border-border/60 bg-[linear-gradient(180deg,rgba(251,146,60,0.08),rgba(15,23,42,0.12))] px-4 py-3"
    >
      <div className="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-display text-xs tracking-[0.14em] text-orange">Facility intelligence</span>
            <span className="rounded border border-cyan/30 bg-cyan/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-cyan">
              {snapshot.postureLabel}
            </span>
          </div>
          <p
            data-testid="cockpit-intelligence-posture"
            className="text-sm leading-relaxed text-silver-dk"
          >
            {snapshot.postureDetail}
          </p>
          <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
            <MetricChip label="Main station candidates" value={String(snapshot.mainStationCandidates.length)} tone={snapshot.mainStationCandidates.length === 1 ? 'good' : snapshot.mainStationCandidates.length === 0 ? 'warn' : 'neutral'} />
            <MetricChip label="Support bodies" value={String(snapshot.supportBodies.length)} />
            <MetricChip label="Role-confident bodies" value={String(snapshot.confidentRoleBodies)} tone={snapshot.confidentRoleBodies > 0 ? 'good' : 'neutral'} />
            <MetricChip label="Warnings" value={String(snapshot.warningCount)} tone={snapshot.warningCount > 0 ? 'warn' : 'good'} />
            <MetricChip label="Conflicts" value={String(snapshot.conflictCount)} tone={snapshot.conflictCount > 0 ? 'warn' : 'good'} />
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <FactBlock
              title="Role anchors"
              testId="cockpit-intelligence-role-anchors"
              items={[
                snapshot.mainStationCandidates.length > 0
                  ? `Main station candidates: ${snapshot.mainStationCandidates.join(', ')}`
                  : 'No clear main station candidate yet.',
                snapshot.supportBodies.length > 0
                  ? `Support bodies: ${snapshot.supportBodies.join(', ')}`
                  : 'Support-body split not visible yet.',
              ]}
            />
            <FactBlock
              title="Facility pressure"
              testId="cockpit-intelligence-facility-pressure"
              items={snapshot.facilityPressure.length > 0 ? snapshot.facilityPressure : ['No facility mix visible yet.']}
            />
          </div>
        </div>
        <div className="rounded-chunk-lg border border-border/60 bg-bg2/45 p-3">
          <div className="font-display text-xs tracking-[0.14em] text-cyan">Explainable next actions</div>
          <div className="mt-2 space-y-2" data-testid="cockpit-intelligence-next-actions">
            {snapshot.nextActions.map((action) => (
              <div key={action.id} className="rounded border border-border/55 bg-bg3/35 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={actionToneClass(action.tone)}>{action.tone === 'good' ? 'ready' : action.tone === 'warn' ? 'review' : 'next'}</span>
                  <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-silver">{action.label}</span>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-silver-dk">{action.reason}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricChip({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  tone?: 'good' | 'warn' | 'neutral';
}) {
  const className = tone === 'good'
    ? 'border-green/35 bg-green/10 text-green'
    : tone === 'warn'
      ? 'border-gold/35 bg-gold/10 text-gold'
      : 'border-border/60 bg-bg3/35 text-silver-dk';

  return (
    <span className={`rounded border px-2 py-1 ${className}`}>
      {label}: {value}
    </span>
  );
}

function FactBlock({
  title,
  items,
  testId,
}: {
  title: string;
  items: string[];
  testId: string;
}) {
  return (
    <div className="rounded border border-border/55 bg-bg3/35 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-cyan">{title}</div>
      <ul className="mt-2 space-y-1 text-[11px] leading-relaxed text-silver-dk" data-testid={testId}>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function actionToneClass(tone: 'good' | 'warn' | 'neutral') {
  if (tone === 'good') return 'rounded border border-green/35 bg-green/10 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.12em] text-green';
  if (tone === 'warn') return 'rounded border border-gold/35 bg-gold/10 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.12em] text-gold';
  return 'rounded border border-cyan/30 bg-cyan/10 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.12em] text-cyan';
}
