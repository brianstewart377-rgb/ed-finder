import type { OptimiserCandidate } from '@/types/api';
import { strategyLabel } from './optimiserUtils';

export interface SuggestedBuildPresentation {
  category: string;
  purpose: string;
  reason: string;
  tradeoff: string;
  nextAction: string;
  tags: string[];
}

const TAG_LABELS: Record<string, string> = {
  balanced: 'Balanced spread',
  body_diversity: 'Uses multiple bodies',
  primary_port: 'Includes a port anchor',
  main_station: 'Main station candidate',
  industrial: 'Industrial pressure',
  refinery: 'Refinery pressure',
  extraction: 'Extraction support',
  tourism: 'Tourism pressure',
  agriculture: 'Agriculture pressure',
  military: 'Security pressure',
  security: 'Security pressure',
  support_body: 'Support body coverage',
};

export function filterUsefulSuggestedBuilds(candidates: OptimiserCandidate[]): OptimiserCandidate[] {
  const seen = new Set<string>();
  const useful: OptimiserCandidate[] = [];

  for (const candidate of candidates) {
    if (isTrivialSuggestedBuild(candidate)) continue;
    const signature = candidateSignature(candidate);
    if (seen.has(signature)) continue;
    seen.add(signature);
    useful.push(candidate);
  }

  return useful;
}

export function isTrivialSuggestedBuild(candidate: OptimiserCandidate): boolean {
  if (candidate.placements.length <= 1) return true;
  if (isColonyShipOnly(candidate)) return true;
  if (isColonyShipAndGenericStation(candidate)) return true;
  return !hasClearSuggestedBuildPurpose(candidate);
}

export function suggestedBuildPresentation(candidate: OptimiserCandidate): SuggestedBuildPresentation {
  const text = candidateText(candidate);
  const category = suggestedBuildCategory(candidate);
  const reason = candidate.rationale[0]
    ?? `This ${strategyLabel(candidate.strategy).toLowerCase()} plan matches the current target better than a blank plan.`;
  const warningCount = candidate.warnings.length + (candidate.preview_summary?.warnings_count ?? 0);
  const tradeoff = warningCount > 0
    ? `Review ${warningCount} warning${warningCount === 1 ? '' : 's'} before relying on this plan.`
    : candidate.placements.length >= 5
      ? 'Broader coverage means more placements to validate before committing materials.'
      : 'Focused starter plan; it may need support bodies after more system data is available.';

  return {
    category,
    purpose: purposeForCategory(category),
    reason,
    tradeoff,
    nextAction: 'Review in Workspace, then load deliberately if it fits the current Build Plan.',
    tags: translateSuggestedBuildTags(candidate.tags, text),
  };
}

export function translateSuggestedBuildTags(tags: string[], text = ''): string[] {
  const translated = tags
    .map((tag) => TAG_LABELS[tag] ?? humanizeTag(tag))
    .filter((tag) => tag.length > 0);
  const unique = Array.from(new Set(translated));
  if (unique.length > 0) return unique;
  if (text.includes('agriculture')) return ['Agriculture pressure'];
  if (text.includes('tourism')) return ['Tourism pressure'];
  if (text.includes('industrial') || text.includes('refinery')) return ['Industrial pressure'];
  if (text.includes('military') || text.includes('security')) return ['Security pressure'];
  return ['Workspace candidate'];
}

function isColonyShipOnly(candidate: OptimiserCandidate) {
  return candidate.placements.length > 0
    && candidate.placements.every((placement) => placement.facility_template_id.toLowerCase().includes('colony_ship'));
}

function isColonyShipAndGenericStation(candidate: OptimiserCandidate) {
  if (candidate.placements.length !== 2) return false;
  const ids = candidate.placements.map((placement) => placement.facility_template_id.toLowerCase());
  return ids.some((id) => id.includes('colony_ship'))
    && ids.some((id) => id.includes('generic') || id.includes('station') || id.includes('outpost'));
}

function hasClearSuggestedBuildPurpose(candidate: OptimiserCandidate) {
  const text = candidateText(candidate);
  if (candidate.rationale.some((item) => item.trim().length > 0)) return true;
  return [
    'primary',
    'port',
    'main',
    'industrial',
    'refinery',
    'tourism',
    'agriculture',
    'military',
    'security',
    'balanced',
    'support',
    'body',
  ].some((term) => text.includes(term));
}

function suggestedBuildCategory(candidate: OptimiserCandidate) {
  const text = candidateText(candidate);
  const hasPrimaryPort = candidate.placements.some((placement) => placement.is_primary_port);
  const bodyCount = new Set(candidate.placements.map((placement) => placement.local_body_id ?? 'unassigned')).size;

  if (text.includes('primary') || (hasPrimaryPort && candidate.placements.length <= 3)) return 'Primary-port starter';
  if (text.includes('main station') || (hasPrimaryPort && candidate.placements.length > 3)) return 'Main station candidate';
  if (text.includes('industrial') || text.includes('refinery') || text.includes('extraction')) return 'Industrial/refinery starter';
  if (text.includes('tourism') || text.includes('agriculture')) return 'Tourism/agriculture starter';
  if (text.includes('military') || text.includes('security')) return 'Military/security stabiliser';
  if (text.includes('support') || bodyCount > 1) return 'Support-body plan';
  return 'Balanced expansion';
}

function purposeForCategory(category: string) {
  switch (category) {
    case 'Primary-port starter':
      return 'Establish a conservative port anchor before expanding the plan.';
    case 'Main station candidate':
      return 'Evaluate whether this body can carry the main station role.';
    case 'Industrial/refinery starter':
      return 'Seed industrial, refinery, or extraction pressure with supporting placements.';
    case 'Tourism/agriculture starter':
      return 'Start a lighter civilian economy plan around tourism or agriculture pressure.';
    case 'Military/security stabiliser':
      return 'Add security-oriented support without claiming a final colony role.';
    case 'Support-body plan':
      return 'Use additional bodies to support the main colony plan.';
    default:
      return 'Build a balanced starter plan that can be adjusted in the workspace.';
  }
}

function candidateText(candidate: OptimiserCandidate) {
  return [
    candidate.label,
    candidate.target_archetype,
    candidate.strategy,
    ...candidate.tags,
    ...candidate.rationale,
    ...candidate.warnings,
    ...candidate.assumptions,
    ...candidate.placements.map((placement) => placement.facility_template_id),
  ].join(' ').toLowerCase();
}

function candidateSignature(candidate: OptimiserCandidate) {
  return candidate.placements
    .map((placement) => [
      placement.facility_template_id,
      placement.local_body_id ?? '',
      placement.is_primary_port ? 'primary' : '',
    ].join('@'))
    .sort()
    .join('|');
}

function humanizeTag(tag: string) {
  return tag
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}
