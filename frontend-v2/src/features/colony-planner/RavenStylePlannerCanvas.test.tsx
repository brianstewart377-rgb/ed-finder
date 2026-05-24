import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FacilityTemplate, SlotPredictionResponse, SystemDetail } from '@/types/api';
import type { TopologyPlanSnapshot, TopologySelectionContext } from './ColonyTopologyRail';
import { RavenPlannerTelemetryPanel, RavenStylePlannerCanvas, buildProjectionComparison, buildRavenPlannerRows } from './RavenStylePlannerCanvas';
import { buildPlanningEconomyLedger } from './planningEconomy';

const system = {
  id64: 123,
  name: 'Real Data System',
  population: 1250000,
  score: 72,
  score_agriculture: 38,
  score_refinery: 83,
  score_industrial: 71,
  score_hightech: 44,
  score_military: 52,
  score_tourism: 29,
  score_extraction: 68,
  economy_suggestion: 'Refinery',
  terraforming_potential: 23,
  body_diversity: 18,
  confidence: 0.82,
  rationale: 'Strong Refinery; dense HMC and rocky body stack with solid slot capacity.',
  bodies: [
    { id: 1, name: 'Real Data System A', body_type: 'Star', subtype: 'K' },
    { id: 2, name: 'Real Data System A 1', body_type: 'Planet', subtype: 'High metal content world', is_landable: true, parent_body_id: 1, distance_from_star: 220 },
    { id: 3, name: 'Real Data System A 2', body_type: 'Planet', subtype: 'Icy body', is_landable: false, parent_body_id: 1, distance_from_star: 330 },
  ],
} as unknown as SystemDetail;

const templates: FacilityTemplate[] = [
  {
    id: 'dodec_starport',
    display_name: 'Dodec Starport',
    name: 'Fallback Dodec',
    category: 'port',
    tier: 3,
    economy: 'Industrial',
    is_port: true,
    is_support_facility: false,
    allowed_location: 'orbital',
    pad_size: 'large',
    confidence: 'confirmed',
    notes: null,
    yellow_cp_generated: 480,
    green_cp_generated: 240,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
    stat_effects: {
      population: 72,
      max_population: 10,
      security: -20.9,
      tech_level: 18.6,
      wealth: 20.25,
      standard_of_living: 30.4,
      development_level: 27.6,
    },
  } as FacilityTemplate & { display_name: string },
  {
    id: 'surface_refinery',
    name: 'Surface Refinery Hub',
    category: 'support',
    tier: 1,
    economy: 'Refinery',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'medium',
    confidence: 'confirmed',
    notes: null,
    yellow_cp_generated: 300,
    green_cp_generated: 250,
    yellow_cp_cost: 1,
    green_cp_cost: 0,
  },
  {
    id: 'no_metadata',
    name: 'No Metadata Facility',
    category: 'support',
    tier: 1,
    economy: null,
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface',
    pad_size: 'medium',
    confidence: 'estimated',
    notes: null,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
  {
    id: 'contextual_station',
    name: 'Contextual Station',
    category: 'port',
    tier: 2,
    economy: null,
    is_port: true,
    is_support_facility: false,
    allowed_location: 'orbital',
    pad_size: 'large',
    confidence: 'observed',
    notes: null,
    yellow_cp_generated: 4,
    green_cp_generated: 1,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
  {
    id: 'research_station',
    name: 'Research Station',
    category: 'hightech',
    tier: 2,
    economy: 'HighTech',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'orbital',
    pad_size: null,
    confidence: 'observed',
    notes: null,
    prerequisites: [{ description: 'Settlement - Research Bio' }],
    yellow_cp_generated: 2,
    green_cp_generated: 1,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
  {
    id: 'flexible_support',
    name: 'Flexible Support Array',
    category: 'support',
    tier: 1,
    economy: 'HighTech',
    is_port: false,
    is_support_facility: true,
    allowed_location: 'surface_or_orbit',
    pad_size: null,
    confidence: 'estimated',
    notes: null,
    yellow_cp_generated: 1,
    green_cp_generated: 0,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
  },
];

const slotPredictions: SlotPredictionResponse = {
  system_id64: 123,
  data_source: 'eddn',
  body_count: 2,
  predicted_orbital_slots_total: 2,
  predicted_ground_slots_total: 2,
  prediction_status: 'predicted',
  prediction_version: 'validated-slot-v1',
  confidence_label: 'validated',
  disclaimer: 'Predicted slots.',
  validation_note: 'Validated.',
  required_input_missing: [],
  predictions: [
    {
      system_address: 123,
      body_id: 2,
      body_name: 'Real Data System A 1',
      predicted_orbital_slots: 2,
      predicted_ground_slots: 2,
      prediction_status: 'predicted',
      reasons: [],
    },
  ],
};

const snapshot: TopologyPlanSnapshot = {
  placements: [
    { facility_template_id: 'dodec_starport', local_body_id: '2', is_primary_port: true, build_order: 1 },
    { facility_template_id: 'surface_refinery', local_body_id: '2', build_order: 2 },
    { facility_template_id: 'no_metadata', local_body_id: '3', build_order: 3 },
  ],
  templates,
  targetArchetype: 'refinery_industrial',
  slotPredictions,
  projection: {
    candidateId: 'candidate-1',
    label: 'Candidate 1',
    placements: [
      { facility_template_id: 'surface_refinery', local_body_id: '2', build_order: 4 },
    ],
  },
};

describe('RavenStylePlannerCanvas real data adapter', () => {
  it('renders user-facing build map copy and concise slot disclaimer', () => {
    render(<RavenStylePlannerCanvas system={system} snapshot={snapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    expect(screen.getByText('System Build Map')).toBeTruthy();
    expect(screen.getByText('Plan structures directly into predicted orbital and surface slots.')).toBeTruthy();
    expect(screen.queryByText('Whole-System Build Canvas')).toBeNull();
    expect(screen.queryByText(/Real bodies, validated slot predictions/i)).toBeNull();
  });

  it('maps real bodies, slot predictions, placements, projections, and economy metadata into rows', () => {
    const rows = buildRavenPlannerRows(system, snapshot);
    const body = rows.find((row) => row.id === '2');
    const missingPredictionBody = rows.find((row) => row.id === '3');

    expect(body?.displayName).toBe('Real Data System A 1');
    expect(body?.orbitalCapacity).toBe(2);
    expect(body?.groundCapacity).toBe(2);
    expect(body?.orbitalSlots[0].fullName).toBe('Dodec Starport');
    expect(body?.orbitalSlots[0].economySegments[0]).toEqual(expect.objectContaining({ economy: 'Industrial', strength: 720 }));
    expect(body?.groundSlots[0].fullName).toBe('Surface Refinery Hub');
    expect(body?.groundSlots[1].kind).toBe('projected');
    expect(missingPredictionBody?.orbitalSlots[0].kind).toBe('unknown');
    expect(missingPredictionBody?.groundSlots[1].title).toContain('No economy metadata');
  });

  it('excludes Barycentre and Null entries from the real system tree rows', () => {
    const rows = buildRavenPlannerRows({
      ...system,
      bodies: [
        ...(system.bodies ?? []),
        { id: 90, name: 'Real Data System Barycentre', body_type: 'Barycentre', subtype: 'Barycentre' },
        { id: 91, name: 'Null Body', body_type: 'Planet', subtype: 'Null' },
      ],
    } as unknown as SystemDetail, {
      ...snapshot,
      placements: [],
      projection: null,
      slotPredictions: null,
    });

    expect(rows.find((row) => row.id === '90')).toBeUndefined();
    expect(rows.find((row) => row.id === '91')).toBeUndefined();
    expect(rows.map((row) => row.displayName).join(' ')).not.toMatch(/Barycentre|Null Body/i);
  });

  it('renders real planner lanes without static mock bodies or attached-structure column', () => {
    render(<RavenStylePlannerCanvas system={system} snapshot={snapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    expect(screen.getByTestId('raven-real-planner-canvas')).toBeTruthy();
    expect(screen.getByTestId('raven-real-body-row-2')).toBeTruthy();
    expect(screen.getByText('Dodec')).toBeTruthy();
    expect(screen.getByText('Refinery Hub')).toBeTruthy();
    expect(screen.getByText('Ghost Refinery Hub')).toBeTruthy();
    expect(screen.getAllByTestId('raven-structure-economy-micro-bar').length).toBeGreaterThan(0);
    expect(screen.getByTitle(/Dodec Starport.*Industrial 100% share.*\+720 CP strength/)).toBeTruthy();
    expect(screen.queryByText('Praea Eug WV-W b2-2')).toBeNull();
    expect(screen.queryByText('Attached Structures')).toBeNull();
    expect(screen.queryByText('Facilities and economy')).toBeNull();
  });

  it('keeps lane display strict and leaves dual-location placements unassigned until a lane is known', () => {
    const flexibleSnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      placements: [
        { facility_template_id: 'flexible_support', local_body_id: '2', build_order: 1 },
      ],
      projection: null,
    };

    const unassignedRow = buildRavenPlannerRows(system, flexibleSnapshot).find((row) => row.id === '2');
    expect(unassignedRow?.orbitalSlots.some((slot) => slot.fullName === 'Flexible Support Array')).toBe(false);
    expect(unassignedRow?.groundSlots.some((slot) => slot.fullName === 'Flexible Support Array')).toBe(false);
    expect(unassignedRow?.unassignedSlots[0]).toEqual(expect.objectContaining({ fullName: 'Flexible Support Array' }));

    const orbitalRow = buildRavenPlannerRows(system, {
      ...flexibleSnapshot,
      placementLaneHints: { 0: 'orbital' },
    }).find((row) => row.id === '2');
    expect(orbitalRow?.orbitalSlots[0]).toEqual(expect.objectContaining({ fullName: 'Flexible Support Array' }));
    expect(orbitalRow?.groundSlots.some((slot) => slot.fullName === 'Flexible Support Array')).toBe(false);

    const surfaceRow = buildRavenPlannerRows(system, {
      ...flexibleSnapshot,
      placementLaneHints: { 0: 'surface' },
    }).find((row) => row.id === '2');
    expect(surfaceRow?.groundSlots[0]).toEqual(expect.objectContaining({ fullName: 'Flexible Support Array' }));
    expect(surfaceRow?.orbitalSlots.some((slot) => slot.fullName === 'Flexible Support Array')).toBe(false);
  });

  it('renders zero-slot lanes compactly without fake empty slot boxes or add targets', () => {
    const zeroSlotSnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      placements: [],
      projection: null,
      slotPredictions: {
        ...slotPredictions,
        predictions: [
          {
            ...slotPredictions.predictions[0],
            predicted_orbital_slots: 0,
            predicted_ground_slots: 0,
          },
        ],
      },
    };
    const rows = buildRavenPlannerRows(system, zeroSlotSnapshot);
    const row = rows.find((candidate) => candidate.id === '2');

    expect(row?.orbitalSlots).toHaveLength(0);
    expect(row?.groundSlots).toHaveLength(0);

    render(
      <RavenStylePlannerCanvas
        system={system}
        snapshot={zeroSlotSnapshot}
        selection={{ type: 'body', bodyId: '2' }}
        onSelect={vi.fn()}
        onRequestAddStructure={vi.fn()}
      />,
    );

    expect(screen.queryByTestId('2-orbital-slot-0')).toBeNull();
    expect(screen.queryByTestId('2-ground-slot-0')).toBeNull();
    expect(screen.getByTestId('2-orbital-compact-state').textContent).toContain('No orbital slots');
    expect(screen.getByTestId('2-ground-compact-state').textContent).toContain('No surface slots');
    expect(screen.queryByTestId('2-orbital-add')).toBeNull();
    expect(screen.queryByTestId('2-ground-add')).toBeNull();
  });

  it('highlights selected bodies without rendering an inline body planner', () => {
    render(
      <RavenStylePlannerCanvas
        system={system}
        snapshot={snapshot}
        selection={{ type: 'body', bodyId: '2' }}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByTestId('raven-real-body-row-2').getAttribute('data-selected')).toBe('true');
    expect(screen.queryByTestId('raven-inline-body-expansion-2')).toBeNull();
    expect(screen.queryByTestId('selected-body-planner-canvas')).toBeNull();
  });

  it('selects planned and projected structures from the main canvas', () => {
    const onSelect = vi.fn();
    render(<RavenStylePlannerCanvas system={system} snapshot={snapshot} selection={{ type: 'system' }} onSelect={onSelect} />);

    fireEvent.click(screen.getByTestId('2-orbital-slot-0'));
    expect(onSelect).toHaveBeenCalledWith({ type: 'placement', placementIndex: 0 });

    fireEvent.click(screen.getByTestId('2-ground-slot-1'));
    expect(onSelect).toHaveBeenCalledWith({ type: 'projected-placement', placementIndex: 0 });
  });

  it('requests lane-aware adds from one row add control per selected lane', () => {
    const onRequestAddStructure = vi.fn();
    render(
      <RavenStylePlannerCanvas
        system={system}
        snapshot={{
          ...snapshot,
          projection: null,
          placements: [
            { facility_template_id: 'dodec_starport', local_body_id: '2', is_primary_port: true, build_order: 1 },
          ],
        }}
        selection={{ type: 'body', bodyId: '2' }}
        onSelect={vi.fn()}
        onRequestAddStructure={onRequestAddStructure}
      />,
    );

    fireEvent.click(screen.getByTestId('2-orbital-add'));
    expect(onRequestAddStructure).toHaveBeenCalledWith('2', 'orbital');

    fireEvent.click(screen.getByTestId('2-ground-add'));
    expect(onRequestAddStructure).toHaveBeenCalledWith('2', 'surface');

    expect(onRequestAddStructure).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('button', { name: /from empty slot/i })).toBeNull();
    expect(screen.getByTestId('2-orbital-slot-1').tagName.toLowerCase()).toBe('span');
  });

  it('keeps passive display slots from presenting button or hover affordances', () => {
    render(<RavenStylePlannerCanvas system={system} snapshot={{ ...snapshot, placements: [], projection: null }} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    const unknownSlot = screen.getByTestId('3-orbital-slot-0');
    expect(unknownSlot.tagName.toLowerCase()).toBe('span');
    expect(unknownSlot.className).not.toContain('hover:-translate-y');
  });

  it('shows disabled surface lane reasons directly in the canvas', () => {
    const onRequestAddStructure = vi.fn();
    render(<RavenStylePlannerCanvas system={system} snapshot={{ ...snapshot, placements: [], projection: null }} selection={{ type: 'body', bodyId: '3' }} onSelect={vi.fn()} onRequestAddStructure={onRequestAddStructure} />);

    expect(screen.getByTestId('3-ground-disabled-reason').textContent).toContain('Surface limited: non-landable body.');
    expect((screen.getByTestId('3-ground-add') as HTMLButtonElement).disabled).toBe(true);
  });

  it('renders contextual station economy and prerequisite warnings on added structures', () => {
    const contextualSnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      placements: [
        { facility_template_id: 'contextual_station', local_body_id: '2', is_primary_port: true, build_order: 1 },
        { facility_template_id: 'research_station', local_body_id: '2', build_order: 2 },
      ],
      projection: null,
    };

    render(<RavenStylePlannerCanvas system={system} snapshot={contextualSnapshot} selection={{ type: 'placement', placementIndex: 0 }} onSelect={vi.fn()} />);

    expect(screen.getByTestId('raven-contextual-economy-chip')).toBeTruthy();
    expect(screen.getByTitle(/Contextual - inherits from body\/system plan/i)).toBeTruthy();
    expect(screen.getByTestId('raven-prerequisite-warning-chip')).toBeTruthy();
  });

  it('renders unpadded lane capacity chips and drops dot indicators on body rows (17N.1e)', () => {
    render(<RavenStylePlannerCanvas system={system} snapshot={snapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    const orbitBadge = screen.getByTestId('2-orbital-capacity-badge');
    const surfaceBadge = screen.getByTestId('2-ground-capacity-badge');
    expect(orbitBadge.dataset.capacity).toBe('2');
    expect(surfaceBadge.dataset.capacity).toBe('2');
    expect(orbitBadge.textContent).toMatch(/Orbit\s*2/);
    expect(orbitBadge.textContent).not.toMatch(/0\s*2/);
    expect(surfaceBadge.textContent).toMatch(/Surface\s*2/);

    expect(screen.queryByTestId('raven-body-slot-indicators-2')).toBeNull();
    const bodyChip = screen.getByTestId('raven-body-capacity-2');
    expect(within(bodyChip).getByTestId('raven-body-capacity-2-orbital').dataset.capacity).toBe('2');
    expect(within(bodyChip).getByTestId('raven-body-capacity-2-ground').dataset.capacity).toBe('2');
  });

  it('shows passive empty slot boxes on unselected bodies instead of dot fallback (17N.1e)', () => {
    const emptySnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      placements: [],
      projection: null,
    };
    render(<RavenStylePlannerCanvas system={system} snapshot={emptySnapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    const orbital0 = screen.getByTestId('2-orbital-slot-0');
    const orbital1 = screen.getByTestId('2-orbital-slot-1');
    expect(orbital0.tagName.toLowerCase()).toBe('span');
    expect(orbital1.tagName.toLowerCase()).toBe('span');
    expect(screen.queryByTestId('2-orbital-compact-state')).toBeNull();
  });

  it('infers an inherited baseline economy bar for contextual stations placed over a body (17N.1e)', () => {
    const baselineSnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      placements: [
        { facility_template_id: 'contextual_station', local_body_id: '2', is_primary_port: true, build_order: 1 },
      ],
      projection: null,
    };

    render(<RavenStylePlannerCanvas system={system} snapshot={baselineSnapshot} selection={{ type: 'placement', placementIndex: 0 }} onSelect={vi.fn()} />);

    expect(screen.getByTestId('raven-structure-economy-micro-bar')).toBeTruthy();
    // Inherited baseline must be qualitative — never synthetic % values.
    expect(screen.queryAllByTitle(/Refinery \d+% share/i)).toHaveLength(0);
    expect(screen.getAllByTitle(/Inherited baseline economies:.*Refinery/i).length).toBeGreaterThan(0);
    expect(screen.getAllByTitle(/Baseline \(inherited\): .* run Preview/i).length).toBeGreaterThan(0);
    expect(screen.getAllByTitle(/Contextual - inherits from body\/system plan/i).length).toBeGreaterThan(0);
  });

  it('does not surface slot/lane wording from prerequisites as a structure warning (17N.1e)', () => {
    const slotPrereqTemplates: FacilityTemplate[] = [
      ...templates,
      {
        id: 'orbital_lab_with_slot_prereq',
        name: 'Slot-Required Lab',
        category: 'hightech',
        tier: 2,
        economy: 'HighTech',
        is_port: false,
        is_support_facility: true,
        allowed_location: 'orbital',
        pad_size: null,
        confidence: 'observed',
        notes: null,
        prerequisites: [{ description: 'Orbital slot available' }],
        yellow_cp_generated: 1,
        green_cp_generated: 0,
        yellow_cp_cost: 0,
        green_cp_cost: 0,
      } as FacilityTemplate,
    ];
    const slotPrereqSnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      templates: slotPrereqTemplates,
      placements: [
        { facility_template_id: 'orbital_lab_with_slot_prereq', local_body_id: '2', build_order: 1 },
      ],
      projection: null,
    };

    const rows = buildRavenPlannerRows(system, slotPrereqSnapshot);
    const body = rows.find((row) => row.id === '2');
    expect(body?.orbitalSlots[0].warningLabels).toEqual([]);
    expect(body?.orbitalSlots[0].title ?? '').not.toMatch(/orbital slot/i);
  });

  it('flags lane capacity overflow with capacity-exceeded warning copy (17N.1e)', () => {
    const overflowSnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      placements: [
        { facility_template_id: 'dodec_starport', local_body_id: '2', build_order: 1 },
        { facility_template_id: 'dodec_starport', local_body_id: '2', build_order: 2 },
        { facility_template_id: 'dodec_starport', local_body_id: '2', build_order: 3 },
      ],
      projection: null,
    };
    const rows = buildRavenPlannerRows(system, overflowSnapshot);
    const body = rows.find((row) => row.id === '2');
    const overflowSlot = body?.orbitalSlots.find((slot) => slot.kind === 'overflow');
    expect(overflowSlot?.title).toMatch(/Orbital capacity exceeded/i);
    expect(body?.warningCount ?? 0).toBeGreaterThan(0);
  });

  it('does not render visible PLAN or CTX labels on main canvas structure boxes (17N.1f)', () => {
    const contextualSnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      placements: [
        { facility_template_id: 'contextual_station', local_body_id: '2', is_primary_port: true, build_order: 1 },
        { facility_template_id: 'research_station', local_body_id: '2', build_order: 2 },
      ],
      projection: null,
    };
    render(<RavenStylePlannerCanvas system={system} snapshot={contextualSnapshot} selection={{ type: 'placement', placementIndex: 0 }} onSelect={vi.fn()} />);

    const allSlotPills = screen.getAllByTestId('raven-structure-slot-pill');
    allSlotPills.forEach((pill) => {
      expect(pill.textContent).not.toContain('PLAN');
      expect(pill.textContent).not.toContain('CTX');
    });

    const structureBoxes = screen.getAllByTestId(/^2-(orbital|ground)-slot-\d+$/);
    structureBoxes.forEach((box) => {
      const visibleText = box.textContent ?? '';
      expect(visibleText).not.toMatch(/\bPLAN\b/);
      expect(visibleText).not.toMatch(/\bCTX\b/);
    });

    expect(screen.getByTestId('raven-contextual-economy-chip')).toBeTruthy();
    expect(screen.getByTestId('raven-prerequisite-warning-chip')).toBeTruthy();
    expect(screen.getByTestId('raven-contextual-economy-chip').className).toContain('sr-only');
    expect(screen.getByTestId('raven-prerequisite-warning-chip').className).toContain('sr-only');
  });

  it('renders economy micro-bars at a readable thickness and preserves tooltip (17N.1f)', () => {
    render(<RavenStylePlannerCanvas system={system} snapshot={snapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    const bars = screen.getAllByTestId('raven-structure-economy-micro-bar');
    expect(bars.length).toBeGreaterThan(0);
    bars.forEach((bar) => {
      expect(bar.className).toContain('h-2');
      expect(bar.className).not.toContain('h-1 ');
      expect(bar.getAttribute('title') ?? '').not.toBe('');
    });
  });

  it('renders lane chips with visually balanced label and count at readable size (17N.1f)', () => {
    render(<RavenStylePlannerCanvas system={system} snapshot={snapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    const badge = screen.getByTestId('2-orbital-capacity-badge');
    expect(badge.textContent).toMatch(/Orbit\s*2/);
    const label = badge.querySelector('[class*="font-semibold"]');
    const count = badge.querySelector('[class*="font-bold"]');
    expect(label).toBeTruthy();
    expect(count).toBeTruthy();
  });

  it('shows prominent selected row highlight and Add controls at readable size (17N.1f)', () => {
    render(
      <RavenStylePlannerCanvas
        system={system}
        snapshot={{ ...snapshot, placements: [], projection: null }}
        selection={{ type: 'body', bodyId: '2' }}
        onSelect={vi.fn()}
        onRequestAddStructure={vi.fn()}
      />,
    );

    const selectedRow = screen.getByTestId('raven-real-body-row-2');
    expect(selectedRow.getAttribute('data-selected')).toBe('true');

    const addOrbit = screen.getByTestId('2-orbital-add');
    expect(addOrbit.className).toContain('font-semibold');
    expect(addOrbit.textContent).toContain('Add Orbit');

    const emptySlot = screen.getByTestId('2-orbital-slot-0');
    expect(emptySlot.tagName.toLowerCase()).toBe('span');
    expect(emptySlot.className).not.toContain('cursor-pointer');
  });

  it('uses readable contrast classes for body names and structure labels (17N.1f)', () => {
    render(<RavenStylePlannerCanvas system={system} snapshot={snapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    const bodyButton = screen.getByTestId('topology-body-button-2');
    const bodyName = bodyButton.querySelector('[class*="text-silver-lt"]');
    expect(bodyName).toBeTruthy();
    expect(bodyName?.textContent).toContain('A 1');
  });

  it('matches projected structures to large numeric system body ids', () => {
    const exactBodyId = '1044927859400806427';
    const roundedBodyId = String(Number(exactBodyId));
    const largeSystem = {
      ...system,
      bodies: [
        { id: Number(exactBodyId), name: 'Real Data System A 1 a', body_type: 'Planet', subtype: 'Rocky body', is_landable: true, distance_from_star: 440 },
      ],
    } as unknown as SystemDetail;
    const largeSnapshot: TopologyPlanSnapshot = {
      ...snapshot,
      placements: [],
      slotPredictions: {
        ...slotPredictions,
        predictions: [
          {
            ...slotPredictions.predictions[0],
            body_id: Number(exactBodyId),
            body_name: 'Real Data System A 1 a',
            predicted_orbital_slots: 1,
            predicted_ground_slots: 2,
          },
        ],
      },
      projection: {
        candidateId: 'large-id-candidate',
        label: 'Large id candidate',
        placements: [
          { facility_template_id: 'surface_refinery', local_body_id: exactBodyId, build_order: 1 },
        ],
      },
    };

    const rows = buildRavenPlannerRows(largeSystem, largeSnapshot);
    const row = rows.find((candidate) => candidate.id === roundedBodyId);

    expect(row?.projected).toBe(true);
    expect(row?.groundSlots[0]).toEqual(expect.objectContaining({ kind: 'projected', projectionIndex: 0 }));

    render(<RavenStylePlannerCanvas system={largeSystem} snapshot={largeSnapshot} selection={{ type: 'system' }} onSelect={vi.fn()} />);

    expect(screen.getByTestId(`raven-real-body-row-${roundedBodyId}`).getAttribute('data-projected')).toBe('true');
    expect(screen.getByText('Ghost Refinery Hub')).toBeTruthy();
  });

  it('summarises selected projection comparison against the current Build Plan', () => {
    const ledger = buildPlanningEconomyLedger({
      placements: snapshot.placements,
      projectedPlacements: snapshot.projection?.placements ?? [],
      templates,
    });
    const comparison = buildProjectionComparison(system, snapshot, ledger);

    expect(comparison.hasProjection).toBe(true);
    expect(comparison.plannedBodyCount).toBe(2);
    expect(comparison.projectedBodyCount).toBe(1);
    expect(comparison.sharedBodyCount).toBe(1);
    expect(comparison.projectedGroundCount).toBe(1);
    expect(comparison.economyDeltas.find((entry) => entry.economy === 'Refinery')).toEqual(expect.objectContaining({ planned: 1, projected: 1 }));
  });

  it('renders exact BGS telemetry deltas with positive and negative zero-centered bars from live planner state', () => {
    const ledger = buildPlanningEconomyLedger({
      placements: snapshot.placements,
      projectedPlacements: snapshot.projection?.placements ?? [],
      templates,
    });
    const selectedContext: TopologySelectionContext = {
      label: 'Real Data System A 1',
      kind: 'Planet',
      placementCount: 2,
      warningCount: 1,
      architectStatus: 'not recorded',
      detail: 'Body selected for planning.',
    };

    render(
      <RavenPlannerTelemetryPanel
        system={system}
        snapshot={snapshot}
        economyLedger={ledger}
        selectedContext={selectedContext}
        selection={{ type: 'body', bodyId: '2' }}
      />,
    );

    expect(screen.getByTestId('raven-real-telemetry-panel')).toBeTruthy();
    expect(screen.getByText('Max population')).toBeTruthy();
    expect(screen.getByText('Standard of living')).toBeTruthy();
    expect(screen.getByText('Development level')).toBeTruthy();
    expect(screen.getByTestId('raven-stat-population-positive').dataset.tone).toBe('positive-green');
    expect(screen.getByTestId('raven-stat-security-negative').dataset.tone).toBe('negative-red');
    expect(screen.getByTestId('raven-stat-security-negative').style.width).not.toBe('0%');
    expect(screen.getByText('+72')).toBeTruthy();
    expect(screen.getByText('-20.9')).toBeTruthy();
    expect(screen.getByTestId('raven-rating-profile-card')).toBeTruthy();
    expect(screen.getByTestId('raven-rating-overall-score').textContent).toContain('72');
    expect(screen.getByTestId('raven-rating-economy-breakdown')).toBeTruthy();
    expect(screen.getByTestId('raven-rating-axis-refinery').textContent).toContain('83');
    expect(screen.getByText(/High 82%/)).toBeTruthy();
    expect(screen.getByTestId('raven-rating-rationale').textContent).toContain('Strong Refinery');
    expect(within(screen.getByTestId('raven-telemetry-economy-ledger')).getByText(/Ind/i)).toBeTruthy();
    expect(screen.getByTestId('raven-projection-comparison')).toBeTruthy();
    expect(screen.getByTestId('projection-comparison-bodies')).toBeTruthy();
    fireEvent.click(screen.getByTestId('projection-comparison-economy-toggle'));
    expect(screen.getByTestId('projection-comparison-economy')).toBeTruthy();
    fireEvent.click(screen.getByTestId('projection-comparison-slots-toggle'));
    expect(screen.getByTestId('projection-comparison-slots')).toBeTruthy();
  });
});
