import type {
  EvidenceRecord,
  EvidenceSystemFocusArea,
  EvidenceSystemSummaryResponse,
} from '@/types/api';
import { formatEvidenceSourceList, formatTimestamp } from '@/lib/format';
import { SemanticStatusBadge, type SemanticStatusTone } from '@/components/SemanticStatusBadge';
import { Section } from './SystemDetailSectionShell';

export function SystemEvidenceSection({
  summary,
  loading,
  error,
  onRetry,
}: {
  summary: EvidenceSystemSummaryResponse | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (loading) {
    return (
      <Section title="Evidence">
        <div className="premium-subpanel px-4 py-5">
          <div className="flex flex-wrap items-center gap-2">
            <SemanticStatusBadge label="Loading" tone="loading" />
            <span className="text-sm text-silver">Loading evidence posture for this system.</span>
          </div>
        </div>
      </Section>
    );
  }

  if (error) {
    return (
      <Section title="Evidence">
        <div className="rounded-chunk-lg border border-red/50 bg-[linear-gradient(180deg,rgba(248,113,113,0.12),rgba(127,29,29,0.16))] p-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <SemanticStatusBadge label="Unavailable" tone="unavailable" />
            <span className="font-semibold text-red">Evidence detail is unavailable right now.</span>
          </div>
          <p className="mt-2 text-silver">
            Canonical system detail is still available, but the trust-layer explanation could not be loaded.
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="btn-metal mt-3 text-xs font-mono font-bold"
          >
            Retry
          </button>
        </div>
      </Section>
    );
  }

  if (!summary) return null;

  const activeRecords = summary.records ?? [];
  const focusAreas = summary.focus_areas ?? [];
  const posture = evidenceSurfacePosture(summary);

  return (
    <Section title="Evidence">
      <div data-testid="system-detail-evidence-section" className="space-y-3">
        <div className="rounded-chunk-lg border border-border bg-bg3/45 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-2">
              <SemanticStatusBadge label={posture.label} tone={posture.tone} />
              <p className="max-w-3xl text-sm leading-relaxed text-silver">
                {posture.summary}
              </p>
            </div>
            <div className="flex flex-wrap gap-2 text-[11px] font-mono">
              <CountChip label="Observed facts" value={summary.observed_fact_count} />
              <CountChip label="Active records" value={summary.imported_record_count} />
              <CountChip label="Derived features" value={summary.derived_feature_count} />
              <CountChip label="Open proposals" value={summary.open_rule_proposal_count} />
            </div>
          </div>
        </div>

        {focusAreas.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {focusAreas.map((focusArea) => (
              <FocusAreaCard key={focusArea.key} focusArea={focusArea} />
            ))}
          </div>
        ) : null}

        {activeRecords.length > 0 ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {activeRecords.map((record) => {
              const observedAt = formatTimestamp(record.observed_at ?? record.collected_at ?? null);
              const expiresAt = formatTimestamp(record.expires_at);
              const sourceLabel = formatEvidenceSourceList([record.source_name]) ?? record.source_name;
              return (
                <article
                  key={record.evidence_key}
                  data-testid={`system-evidence-record-${record.evidence_key}`}
                  className="rounded-chunk-lg border border-border bg-bg3/40 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
                        {humanizeEvidenceLabel(record.evidence_type)}
                      </p>
                      <p className="mt-1 text-sm font-semibold text-text">
                        {record.summary?.trim() || 'Active evidence record linked for this system.'}
                      </p>
                    </div>
                    <SemanticStatusBadge
                      label={recordLifecycleLabel(record)}
                      tone={recordLifecycleTone(record)}
                    />
                  </div>
                  <dl className="mt-3 grid gap-x-4 gap-y-2 text-[11px] sm:grid-cols-2">
                    <EvidenceMetaRow label="Source" value={sourceLabel} />
                    <EvidenceMetaRow label="Subject" value={recordSubjectLabel(record)} />
                    <EvidenceMetaRow label="Observed" value={observedAt ?? 'Unknown'} />
                    <EvidenceMetaRow label="Confidence" value={humanizeEvidenceLabel(record.confidence)} />
                    <EvidenceMetaRow label="Origin" value={humanizeEvidenceLabel(record.origin)} />
                    {expiresAt ? <EvidenceMetaRow label="Expires" value={expiresAt} /> : null}
                  </dl>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="rounded-chunk-lg border border-border bg-bg3/35 p-4 text-sm text-silver">
            No active evidence records are linked yet. Canonical system detail remains the answer surface while evidence promotion catches up.
          </div>
        )}

        {summary.derived_features.length > 0 ? (
          <div className="rounded-chunk-lg border border-border bg-bg3/35 p-4">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
              Derived features
            </p>
            <ul className="mt-3 space-y-2 text-sm text-silver">
              {summary.derived_features.map((feature) => (
                <li key={feature.feature_key}>
                  <span className="font-semibold text-text">{humanizeEvidenceLabel(feature.feature_name)}:</span>{' '}
                  {feature.summary?.trim() || 'Derived evidence feature available for review.'}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {summary.open_rule_proposals.length > 0 ? (
          <div className="rounded-chunk-lg border border-border bg-bg3/35 p-4">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
              Open evidence proposals
            </p>
            <ul className="mt-3 space-y-2 text-sm text-silver">
              {summary.open_rule_proposals.map((proposal) => (
                <li key={proposal.proposal_key}>
                  <span className="font-semibold text-text">{humanizeEvidenceLabel(proposal.proposal_type)}:</span>{' '}
                  {proposal.summary}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Section>
  );
}

function CountChip({ label, value }: { label: string; value: number }) {
  return (
    <span className="rounded-full border border-border bg-bg4 px-2.5 py-1 text-silver">
      {label}: <span className="text-text">{value}</span>
    </span>
  );
}

function FocusAreaCard({ focusArea }: { focusArea: EvidenceSystemFocusArea }) {
  const badge = focusAreaBadge(focusArea.posture);
  return (
    <article
      data-testid={`system-evidence-focus-${focusArea.key}`}
      className="rounded-chunk-lg border border-border bg-bg3/40 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
            {focusArea.label}
          </p>
          {focusArea.evidence_type ? (
            <p className="mt-1 text-[11px] text-text-dim">
              {humanizeEvidenceLabel(focusArea.evidence_type)}
            </p>
          ) : null}
        </div>
        <SemanticStatusBadge label={badge.label} tone={badge.tone} />
      </div>
      <p className="mt-3 text-sm leading-relaxed text-silver">
        {focusArea.summary}
      </p>
    </article>
  );
}

function EvidenceMetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/40 pb-1">
      <dt className="font-mono uppercase tracking-[0.14em] text-silver-dk">{label}</dt>
      <dd className="text-right font-mono text-text">{value}</dd>
    </div>
  );
}

function evidenceSurfacePosture(
  summary: EvidenceSystemSummaryResponse,
): { label: string; tone: SemanticStatusTone; summary: string } {
  if (summary.imported_record_count > 0) {
    return {
      label: 'Active evidence linked',
      tone: 'available',
      summary: 'These active evidence records explain the current trust posture for this system without changing canonical detail directly.',
    };
  }
  if ((summary.focus_areas ?? []).some((focusArea) => focusArea.posture === 'canonical_present')) {
    return {
      label: 'Canonical data linked',
      tone: 'canonical',
      summary: 'Important system facts are already present in canonical app data here, even where lifecycle-managed evidence promotion has not caught up yet.',
    };
  }
  if (summary.observed_fact_count > 0) {
    return {
      label: 'Observation log only',
      tone: 'observed',
      summary: 'Raw observations exist for this system, but no active lifecycle-managed evidence record is linked yet.',
    };
  }
  return {
    label: 'No evidence linked',
    tone: 'unknown',
    summary: 'No observed, promoted, or canonical fallback evidence is currently linked for this system.',
  };
}

function focusAreaBadge(posture: string): { label: string; tone: SemanticStatusTone } {
  if (posture === 'evidence_linked') {
    return { label: 'Evidence linked', tone: 'available' };
  }
  if (posture === 'canonical_present') {
    return { label: 'Canonical present', tone: 'canonical' };
  }
  if (posture === 'observed_only') {
    return { label: 'Observed only', tone: 'observed' };
  }
  return { label: 'Missing', tone: 'unknown' };
}

function recordLifecycleTone(record: EvidenceRecord): SemanticStatusTone {
  if (record.record_status === 'quarantined') return 'needs_review';
  if (record.record_status === 'rejected') return 'blocked';
  if (record.record_status !== 'active') return 'caution';
  if (record.freshness_status === 'stale' || record.freshness_status === 'expired') return 'stale';
  if (record.freshness_status === 'unknown') return 'unknown';
  return 'available';
}

function recordLifecycleLabel(record: EvidenceRecord): string {
  return `${humanizeEvidenceLabel(record.record_status)} / ${humanizeEvidenceLabel(record.freshness_status)}`;
}

function recordSubjectLabel(record: EvidenceRecord): string {
  const subjectType = humanizeEvidenceLabel(record.subject_type);
  if (!record.subject_id) return subjectType;
  return `${subjectType} ${record.subject_id}`;
}

function humanizeEvidenceLabel(value?: string | null): string {
  const source = value?.trim();
  if (!source) return 'Unknown';
  return source
    .split('_')
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ');
}
