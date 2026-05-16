import type { FacilityTemplate, SystemBody } from '@/types/api';

export type StructureLocationFilter = 'all' | 'orbital' | 'surface' | 'both';
export type TemplateLocationKind = 'orbital' | 'surface' | 'both' | 'unknown';

export interface StructurePickerBodyContext {
  status: 'none' | 'known' | 'unknown';
  body: SystemBody | null;
  label: string;
}

export function templateLocationKind(template: FacilityTemplate): TemplateLocationKind {
  const location = (template.allowed_location ?? '').toLowerCase();
  const hasSurface = location.includes('surface');
  const hasOrbital = location.includes('orbit') || location.includes('orbital');

  if (location.includes('both') || (hasSurface && hasOrbital)) return 'both';
  if (hasSurface) return 'surface';
  if (hasOrbital) return 'orbital';
  return 'unknown';
}

export function formatTemplateLocation(template: FacilityTemplate): string {
  const kind = templateLocationKind(template);
  if (kind === 'both') return 'Both';
  if (kind === 'surface') return 'Surface';
  if (kind === 'orbital') return 'Orbital';
  return 'Unknown';
}

export function formatCpGives(template: FacilityTemplate): string {
  return `Y+${template.yellow_cp_generated} G+${template.green_cp_generated}`;
}

export function formatCpNeeds(template: FacilityTemplate): string {
  return `Y${template.yellow_cp_cost} G${template.green_cp_cost}`;
}

export function formatTemplateTier(template: FacilityTemplate): string {
  return template.tier != null ? `Tier ${template.tier}` : 'Unknown';
}

export function formatTemplatePad(template: FacilityTemplate): string {
  return template.pad_size || 'Unknown';
}

export function formatTemplateEconomy(template: FacilityTemplate): string {
  return template.economy || 'Unknown';
}

export function formatTemplateRole(template: FacilityTemplate): string {
  return template.category || 'Unknown';
}

export function formatTemplateConfidence(template: FacilityTemplate): string {
  return template.confidence || 'missing';
}

export function formatTemplatePortSupport(template: FacilityTemplate): string {
  if (template.is_port) return 'Port';
  if (template.is_support_facility) return 'Support';
  return 'Structure';
}

export function getStructurePickerBodyContext(
  bodies: SystemBody[],
  selectedBodyId?: string | number | null,
): StructurePickerBodyContext {
  if (selectedBodyId == null || selectedBodyId === '') {
    return { status: 'none', body: null, label: 'No body selected yet' };
  }

  const body = bodies.find((item) => item.id != null && String(item.id) === String(selectedBodyId)) ?? null;
  if (!body) return { status: 'unknown', body: null, label: 'Unknown body' };
  return { status: 'known', body, label: bodyDisplayName(body) };
}

export function getStructurePickerWarnings(
  template: FacilityTemplate,
  context: StructurePickerBodyContext,
): string[] {
  const warnings = new Set<string>();
  const locationKind = templateLocationKind(template);

  if (context.status === 'none') {
    warnings.add('Needs body: body-specific checks need a body');
  }
  if (context.status === 'unknown') {
    warnings.add('Unknown body: body-specific validity cannot be trusted');
  }
  if (template.confidence === 'estimated') {
    warnings.add('Template uses estimated data');
  }

  if (context.body) {
    if (isBodyMetadataSparse(context.body)) {
      warnings.add('Body metadata incomplete');
    }
    if ((locationKind === 'surface' || locationKind === 'both') && context.body.is_water_world) {
      warnings.add('Check location: surface facility on water world may be invalid');
    }
    if ((locationKind === 'surface' || locationKind === 'both') && context.body.is_landable === false) {
      warnings.add('Check location: surface facility needs suitable landable body');
    }
    if ((locationKind === 'orbital' || locationKind === 'both') && !context.body.body_type && !context.body.subtype) {
      warnings.add('Orbital suitability unclear');
    }
  }

  return Array.from(warnings);
}

export function filterStructureTemplates(
  templates: FacilityTemplate[],
  filter: StructureLocationFilter,
  query: string,
): FacilityTemplate[] {
  const search = query.trim().toLowerCase();
  return templates.filter((template) => (
    locationMatchesFilter(template, filter) && templateMatchesSearch(template, search)
  ));
}

export function locationMatchesFilter(template: FacilityTemplate, filter: StructureLocationFilter): boolean {
  if (filter === 'all') return true;
  const kind = templateLocationKind(template);
  if (filter === 'both') return kind === 'both';
  if (filter === 'orbital') return kind === 'orbital' || kind === 'both';
  if (filter === 'surface') return kind === 'surface' || kind === 'both';
  return true;
}

export function templateMatchesSearch(template: FacilityTemplate, search: string): boolean {
  if (!search) return true;
  const haystack = [
    template.id,
    template.name,
    template.category,
    template.economy,
    template.allowed_location,
    template.pad_size,
    template.confidence,
    template.notes,
  ]
    .filter((value): value is string => typeof value === 'string')
    .join(' ')
    .toLowerCase();
  return haystack.includes(search);
}

function bodyDisplayName(body: SystemBody): string {
  return body.name || (body.id != null ? `Body ${body.id}` : 'Unknown body');
}

function isBodyMetadataSparse(body: SystemBody): boolean {
  return !body.body_type
    && !body.subtype
    && body.is_landable == null
    && !body.is_water_world
    && !body.is_earth_like
    && !body.is_ammonia_world
    && !body.is_terraformable;
}
