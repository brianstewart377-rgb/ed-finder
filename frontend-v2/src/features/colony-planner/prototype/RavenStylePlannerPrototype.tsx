import {
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  Layers3,
  LocateFixed,
  Sparkles,
  Target,
  TriangleAlert,
} from 'lucide-react';
import { useMemo, useState, type CSSProperties } from 'react';

type EconomyKind =
  | 'Refinery'
  | 'Industrial'
  | 'Military'
  | 'Tourism'
  | 'Agriculture'
  | 'Extraction'
  | 'High Tech';

type SlotKind = 'empty' | 'planned' | 'projected' | 'invalid' | 'unknown' | 'overflow';
type LaneKind = 'orbital' | 'ground';
type ProjectionMode = 'balanced' | 'security';

interface EconomyContribution {
  kind: EconomyKind;
  value?: number;
  share?: number;
  bonus?: number;
  projected?: boolean;
}

interface EconomyModifier {
  kind: EconomyKind;
  bonus: number;
  source: string;
}

interface StructureEconomyEffect {
  kind: EconomyKind;
  structureBonus: number;
  projected?: boolean;
}

interface StructureEconomySegment {
  kind: EconomyKind;
  share: number;
  bonus: number;
  structureBonus: number;
  bodyBonus: number;
  projected?: boolean;
}

interface EconomyReadout {
  kind: EconomyKind;
  share: number;
  bonus: number;
  projected?: boolean;
}

interface SlotModel {
  id: string;
  kind: SlotKind;
  label?: string;
  economy?: EconomyKind;
  economyEffects?: StructureEconomyEffect[];
  primary?: boolean;
  projection?: ProjectionMode | 'both';
  hint?: string;
}

interface BodyNode {
  id: string;
  name: string;
  bodyClass: string;
  detail: string;
  marker: 'star' | 'gas' | 'rock' | 'ice' | 'earth' | 'belt' | 'moon';
  orbitalSlots: SlotModel[];
  groundSlots: SlotModel[];
  economy: EconomyContribution[];
  economyModifiers?: EconomyModifier[];
  warning?: string;
  primaryCandidate?: boolean;
  children?: BodyNode[];
}

interface FlatBody {
  node: BodyNode;
  depth: number;
  guide: boolean[];
  isLast: boolean;
}

const ECONOMY_COLORS: Record<EconomyKind, string> = {
  Refinery: '#fbbf24',
  Industrial: '#ff7a14',
  Military: '#f87171',
  Tourism: '#a78bfa',
  Agriculture: '#4ade80',
  Extraction: '#c8ccd1',
  'High Tech': '#7dd3fc',
};

const ECONOMY_ABBREVIATIONS: Record<EconomyKind, string> = {
  Refinery: 'Ref',
  Industrial: 'Ind',
  Military: 'Mil',
  Tourism: 'Tour',
  Agriculture: 'Agri',
  Extraction: 'Ext',
  'High Tech': 'HiTech',
};

const DEFAULT_STRUCTURE_BONUS: Record<EconomyKind, number> = {
  Refinery: 140,
  Industrial: 125,
  Military: 120,
  Tourism: 105,
  Agriculture: 110,
  Extraction: 150,
  'High Tech': 115,
};

const STRUCTURE_COMPACT_LABELS: Record<string, string> = {
  'Altshuller Reach Outpost': 'Altshuller',
  'Schoening Data Relay': 'Data Relay',
  'Cornucopia Dodec Starport': 'Dodec',
  'Yamashita Extraction Prospect': 'Extraction',
  'Deneter Agricultural Dome': 'Agri Dome',
  'Dodec Starport': 'Dodec',
  'Dioscory Research Lab': 'Research Lab',
  'Silenius Mining Hub': 'Silenius Mining',
  'Akiyama Refinery Hub': 'Refinery Hub',
  'Kawajiri Industrial Installation': 'Industrial Inst.',
  'Schoening Military Outpost': 'Military Outpost',
  'Kani Tourism Beacon': 'Tourism Beacon',
  'Santos Military Outpost': 'Military Outpost',
  'Babbage High Tech Relay': 'High Tech Relay',
  'Vaucouleurs Survey Port': 'Survey Port',
};

const SYSTEM_STAT_DELTAS = [
  { id: 'population', label: 'Population', value: 18, color: '#4ade80' },
  { id: 'max-population', label: 'Max population', value: 10, color: '#4ade80' },
  { id: 'security', label: 'Security', value: -7.2, color: '#f87171' },
  { id: 'tech-level', label: 'Tech level', value: 18.6, color: '#4ade80' },
  { id: 'wealth', label: 'Wealth', value: 20.25, color: '#4ade80' },
  { id: 'standard-of-living', label: 'Standard of living', value: 30.4, color: '#4ade80' },
  { id: 'development', label: 'Development', value: 27.6, color: '#4ade80' },
  { id: 'logistics-debt', label: 'Logistics debt', value: 0, color: '#9ca3af' },
] as const;

const SYSTEM_ECONOMY_OUTCOME: EconomyReadout[] = [
  { kind: 'Extraction', share: 32, bonus: 720 },
  { kind: 'Refinery', share: 26, bonus: 550 },
  { kind: 'Industrial', share: 18, bonus: 230 },
  { kind: 'High Tech', share: 9, bonus: 150 },
  { kind: 'Military', share: 8, bonus: 120 },
  { kind: 'Agriculture', share: 4, bonus: 90 },
  { kind: 'Tourism', share: 3, bonus: 70 },
];

const MARKER_STYLES: Record<BodyNode['marker'], { fill: string; ring: string; size: string }> = {
  star: { fill: 'radial-gradient(circle at 35% 30%, #ffd18c, #ff9f1a 55%, #9a4d00)', ring: 'rgba(255, 122, 20, 0.58)', size: 'h-9 w-9' },
  gas: { fill: 'radial-gradient(circle at 35% 30%, #ff8fb8, #d9467d 55%, #6d1539)', ring: 'rgba(248, 113, 113, 0.5)', size: 'h-8 w-8' },
  rock: { fill: 'radial-gradient(circle at 35% 30%, #9ca3af, #525861 60%, #22262b)', ring: 'rgba(200, 204, 209, 0.45)', size: 'h-5 w-5' },
  ice: { fill: 'radial-gradient(circle at 35% 30%, #d9f3ff, #7dd3fc 55%, #245d76)', ring: 'rgba(125, 211, 252, 0.5)', size: 'h-5 w-5' },
  earth: { fill: 'radial-gradient(circle at 35% 30%, #98f5c5, #38bdf8 45%, #0f766e 78%)', ring: 'rgba(74, 222, 128, 0.5)', size: 'h-6 w-6' },
  belt: { fill: 'linear-gradient(135deg, #c8ccd1, #606773)', ring: 'rgba(251, 191, 36, 0.45)', size: 'h-4 w-4' },
  moon: { fill: 'radial-gradient(circle at 35% 30%, #d1d5db, #7c8189 60%, #31363d)', ring: 'rgba(200, 204, 209, 0.38)', size: 'h-4 w-4' },
};

function emptySlots(prefix: string, count: number): SlotModel[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `${prefix}-empty-${index + 1}`,
    kind: 'empty' as const,
  }));
}

function planned(
  id: string,
  label: string,
  economy: EconomyKind,
  options?: Pick<SlotModel, 'primary' | 'hint' | 'economyEffects'>,
): SlotModel {
  return { id, kind: 'planned', label, economy, ...options };
}

function projected(
  id: string,
  label: string,
  economy: EconomyKind,
  projection: ProjectionMode | 'both' = 'both',
  options?: Pick<SlotModel, 'economyEffects' | 'hint'>,
): SlotModel {
  return { id, kind: 'projected', label, economy, projection, ...options };
}

const MOCK_SYSTEM: BodyNode = {
  id: 'root-star',
  name: 'Praea Eug WV-W b2-2',
  bodyClass: 'K-class primary star',
  detail: 'System root / primary construction anchor',
  marker: 'star',
  orbitalSlots: [
    planned('root-o-1', 'Altshuller Reach Outpost', 'High Tech'),
    projected('root-o-2', 'Schoening Data Relay', 'High Tech', 'balanced'),
  ],
  groundSlots: [],
  economy: [
    { kind: 'High Tech', value: 2 },
    { kind: 'Industrial', value: 1, projected: true },
  ],
  children: [
    {
      id: 'a-1',
      name: 'A 1',
      bodyClass: 'High metal content',
      detail: 'Landable / close support orbit',
      marker: 'rock',
      orbitalSlots: [planned('a1-o-1', 'Cornucopia Dodec Starport', 'Industrial', { primary: true }), ...emptySlots('a1-o', 1)],
      groundSlots: [planned('a1-g-1', 'Yamashita Extraction Prospect', 'Extraction'), ...emptySlots('a1-g', 2)],
      economy: [
        { kind: 'Industrial', value: 3 },
        { kind: 'Extraction', value: 2 },
      ],
      primaryCandidate: true,
      children: [
        {
          id: 'a-1-a',
          name: 'A 1 a',
          bodyClass: 'Rocky moon',
          detail: 'Low gravity surface pads',
          marker: 'moon',
          orbitalSlots: emptySlots('a1a-o', 1),
          groundSlots: [projected('a1a-g-1', 'Deneter Agricultural Dome', 'Agriculture', 'balanced'), ...emptySlots('a1a-g', 2)],
          economy: [{ kind: 'Agriculture', value: 2, projected: true }],
        },
      ],
    },
    {
      id: 'a-2',
      name: 'A 2',
      bodyClass: 'High metal content',
      detail: 'Refinery spine body',
      marker: 'rock',
      orbitalSlots: [planned('a2-o-1', 'Akiyama Refinery Depot', 'Refinery'), planned('a2-o-2', 'Soter Data Relay', 'High Tech')],
      groundSlots: [planned('a2-g-1', 'Akiyama Refinery Hub', 'Refinery'), planned('a2-g-2', 'Ranganathan Resource Mine', 'Extraction'), ...emptySlots('a2-g', 2)],
      economy: [
        { kind: 'Refinery', value: 5 },
        { kind: 'Extraction', value: 2 },
        { kind: 'High Tech', value: 1 },
      ],
      children: [
        {
          id: 'a-2-a',
          name: 'A 2 a',
          bodyClass: 'Icy moon',
          detail: 'Surface logistics reserve',
          marker: 'ice',
          orbitalSlots: emptySlots('a2a-o', 1),
          groundSlots: [planned('a2a-g-1', 'Hamonia Industrial Storage', 'Industrial'), ...emptySlots('a2a-g', 2)],
          economy: [{ kind: 'Industrial', value: 1 }],
        },
        {
          id: 'a-2-b',
          name: 'A 2 b',
          bodyClass: 'Rocky moon',
          detail: 'Projected garrison site',
          marker: 'moon',
          orbitalSlots: emptySlots('a2b-o', 1),
          groundSlots: [projected('a2b-g-1', 'Alastor Military Outpost', 'Military', 'security'), ...emptySlots('a2b-g', 2)],
          economy: [{ kind: 'Military', value: 3, projected: true }],
        },
      ],
    },
    {
      id: 'a-3',
      name: 'A 3',
      bodyClass: 'Class I gas giant',
      detail: 'Moon branch with mixed build pressure',
      marker: 'gas',
      orbitalSlots: [planned('a3-o-1', 'Lynch\'s Paycut Ocellus Starport', 'Tourism'), ...emptySlots('a3-o', 1)],
      groundSlots: [],
      economy: [
        { kind: 'Tourism', value: 2 },
        { kind: 'Military', value: 1, projected: true },
      ],
      children: [
        {
          id: 'a-3-a',
          name: 'A 3 a',
          bodyClass: 'High metal content',
          detail: 'Landable / validated 4 orbital and 5 ground slots',
          marker: 'rock',
          orbitalSlots: [
            planned('a3a-o-1', 'Dodec Starport', 'Industrial', {
              primary: true,
              economyEffects: [
                { kind: 'Industrial', structureBonus: 220 },
                { kind: 'Refinery', structureBonus: 160 },
                { kind: 'High Tech', structureBonus: 80 },
              ],
            }),
            projected('a3a-o-2', 'Dioscory Research Lab', 'High Tech', 'balanced', {
              economyEffects: [
                { kind: 'High Tech', structureBonus: 180, projected: true },
                { kind: 'Industrial', structureBonus: 50, projected: true },
              ],
            }),
            { id: 'a3a-o-3', kind: 'empty' },
            { id: 'a3a-o-4', kind: 'empty' },
          ],
          groundSlots: [
            planned('a3a-g-1', 'Silenius Mining Hub', 'Extraction', {
              economyEffects: [
                { kind: 'Extraction', structureBonus: 240 },
                { kind: 'Refinery', structureBonus: 240 },
                { kind: 'Industrial', structureBonus: 80 },
              ],
            }),
            planned('a3a-g-2', 'Akiyama Refinery Hub', 'Refinery', {
              economyEffects: [
                { kind: 'Refinery', structureBonus: 240 },
                { kind: 'Extraction', structureBonus: 80 },
              ],
            }),
            projected('a3a-g-3', 'Kawajiri Industrial Installation', 'Industrial', 'balanced', {
              economyEffects: [
                { kind: 'Industrial', structureBonus: 180, projected: true },
                { kind: 'Refinery', structureBonus: 80, projected: true },
              ],
            }),
            projected('a3a-g-4', 'Schoening Military Outpost', 'Military', 'both', {
              economyEffects: [
                { kind: 'Military', structureBonus: 150, projected: true },
                { kind: 'Industrial', structureBonus: 40, projected: true },
              ],
            }),
            { id: 'a3a-g-5', kind: 'invalid', label: 'No build' },
          ],
          economy: [
            { kind: 'Extraction', share: 48, bonus: 480 },
            { kind: 'Refinery', share: 31, bonus: 310 },
            { kind: 'Industrial', share: 16, bonus: 100 },
            { kind: 'High Tech', share: 3, bonus: 55, projected: true },
            { kind: 'Military', share: 2, bonus: 60, projected: true },
          ],
          economyModifiers: [
            { kind: 'Extraction', bonus: 480, source: 'Landable high metal content with geo survey pressure' },
            { kind: 'Refinery', bonus: 310, source: 'Refinery spine body and nearby extraction feed' },
            { kind: 'Industrial', bonus: 100, source: 'Primary-port construction logistics' },
            { kind: 'High Tech', bonus: 55, source: 'Research relay adjacency' },
            { kind: 'Military', bonus: 60, source: 'Projected garrison coverage' },
          ],
          primaryCandidate: true,
        },
        {
          id: 'a-3-b',
          name: 'A 3 b',
          bodyClass: 'Icy moon',
          detail: 'Sparse survey data',
          marker: 'ice',
          orbitalSlots: [{ id: 'a3b-o-unknown', kind: 'unknown', label: '?' }],
          groundSlots: [{ id: 'a3b-g-unknown', kind: 'unknown', label: '?' }],
          economy: [],
          warning: 'Unknown slot survey',
        },
      ],
    },
    {
      id: 'a-4',
      name: 'A 4',
      bodyClass: 'Earth-like world',
      detail: 'Tourism and civil services',
      marker: 'earth',
      orbitalSlots: [planned('a4-o-1', 'Compton Sanctuary Coriolis', 'Tourism'), ...emptySlots('a4-o', 1)],
      groundSlots: [projected('a4-g-1', 'Piaget Agricultural Port', 'Agriculture', 'balanced'), ...emptySlots('a4-g', 2)],
      economy: [
        { kind: 'Tourism', value: 4 },
        { kind: 'Agriculture', value: 2, projected: true },
      ],
    },
    {
      id: 'a-5',
      name: 'A 5',
      bodyClass: 'High metal content',
      detail: 'Industrial overflow test body',
      marker: 'rock',
      orbitalSlots: [
        planned('a5-o-1', 'Baynes Gateway', 'Industrial'),
        planned('a5-o-2', 'Sefry Smelter', 'Refinery'),
        { id: 'a5-o-overflow', kind: 'overflow', label: '+1 overflow', economy: 'Industrial' },
      ],
      groundSlots: [planned('a5-g-1', 'Dionysus Foundry', 'Industrial'), ...emptySlots('a5-g', 2)],
      economy: [
        { kind: 'Industrial', value: 4 },
        { kind: 'Refinery', value: 2 },
      ],
      warning: 'One planned orbital structure exceeds known capacity',
      children: [
        {
          id: 'a-5-a',
          name: 'A 5 a',
          bodyClass: 'Rocky moon',
          detail: 'Extraction feeder',
          marker: 'moon',
          orbitalSlots: emptySlots('a5a-o', 1),
          groundSlots: [planned('a5a-g-1', 'Thor Quarry', 'Extraction'), ...emptySlots('a5a-g', 1)],
          economy: [{ kind: 'Extraction', value: 2 }],
        },
        {
          id: 'a-5-b',
          name: 'A 5 b',
          bodyClass: 'Rocky moon',
          detail: 'Projected logistics support',
          marker: 'moon',
          orbitalSlots: emptySlots('a5b-o', 1),
          groundSlots: [projected('a5b-g-1', 'Aletheia Support Hub', 'Industrial', 'balanced'), ...emptySlots('a5b-g', 1)],
          economy: [{ kind: 'Industrial', value: 2, projected: true }],
        },
      ],
    },
    {
      id: 'b-star',
      name: 'B',
      bodyClass: 'M-class companion star',
      detail: 'Secondary branch',
      marker: 'star',
      orbitalSlots: emptySlots('bstar-o', 1),
      groundSlots: [],
      economy: [],
      children: [
        {
          id: 'b-1',
          name: 'B 1',
          bodyClass: 'Metal-rich body',
          detail: 'Unknown orbital count / known surface reserve',
          marker: 'rock',
          orbitalSlots: [{ id: 'b1-o-unknown', kind: 'unknown', label: '?' }],
          groundSlots: [planned('b1-g-1', 'Alastor Security Hub', 'Military'), projected('b1-g-2', 'Pistis Barracks', 'Military', 'security'), ...emptySlots('b1-g', 1)],
          economy: [
            { kind: 'Military', value: 2 },
            { kind: 'Military', value: 2, projected: true },
          ],
          warning: 'Orbital sites unknown',
          children: [
            {
              id: 'b-1-a',
              name: 'B 1 a',
              bodyClass: 'Icy moon',
              detail: 'Reserve body',
              marker: 'ice',
              orbitalSlots: emptySlots('b1a-o', 1),
              groundSlots: emptySlots('b1a-g', 2),
              economy: [],
            },
          ],
        },
        {
          id: 'b-2',
          name: 'B 2',
          bodyClass: 'Ammonia world',
          detail: 'Agriculture / tourism pressure',
          marker: 'earth',
          orbitalSlots: [planned('b2-o-1', 'Victor Papa Visitor Hub', 'Tourism'), ...emptySlots('b2-o', 1)],
          groundSlots: [projected('b2-g-1', 'Deneter Bio Farm', 'Agriculture', 'balanced'), ...emptySlots('b2-g', 2)],
          economy: [
            { kind: 'Tourism', value: 2 },
            { kind: 'Agriculture', value: 3, projected: true },
          ],
          children: [
            {
              id: 'b-2-a',
              name: 'B 2 a',
              bodyClass: 'Rocky moon',
              detail: 'Support reserve',
              marker: 'moon',
              orbitalSlots: emptySlots('b2a-o', 1),
              groundSlots: emptySlots('b2a-g', 1),
              economy: [],
            },
          ],
        },
        {
          id: 'belt-1',
          name: 'B Belt Cluster 1',
          bodyClass: 'Asteroid belt',
          detail: 'Survey incomplete',
          marker: 'belt',
          orbitalSlots: [{ id: 'belt1-o-unknown', kind: 'unknown', label: '?' }],
          groundSlots: [],
          economy: [],
          warning: 'Unknown site count',
        },
      ],
    },
    {
      id: 'c-star',
      name: 'C',
      bodyClass: 'White dwarf tertiary',
      detail: 'Remote high-tech branch',
      marker: 'star',
      orbitalSlots: [projected('cstar-o-1', 'Soter Data Relay', 'High Tech', 'balanced')],
      groundSlots: [],
      economy: [{ kind: 'High Tech', value: 2, projected: true }],
      children: [
        {
          id: 'c-1',
          name: 'C 1',
          bodyClass: 'Icy body',
          detail: 'Remote extraction body',
          marker: 'ice',
          orbitalSlots: emptySlots('c1-o', 1),
          groundSlots: [planned('c1-g-1', 'Erebus Ice Mine', 'Extraction'), ...emptySlots('c1-g', 2)],
          economy: [{ kind: 'Extraction', value: 2 }],
          children: [
            {
              id: 'c-1-a',
              name: 'C 1 a',
              bodyClass: 'Rocky moon',
              detail: 'No planned build',
              marker: 'moon',
              orbitalSlots: emptySlots('c1a-o', 1),
              groundSlots: emptySlots('c1a-g', 2),
              economy: [],
            },
          ],
        },
      ],
    },
  ],
};

export function RavenStylePlannerPrototype() {
  const [selectedBodyId, setSelectedBodyId] = useState('a-3-a');
  const [showProjection, setShowProjection] = useState(true);
  const [detailedRows, setDetailedRows] = useState(false);
  const [projectionMode, setProjectionMode] = useState<ProjectionMode>('balanced');
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());

  const visibleBodies = useMemo(() => flattenBodies(MOCK_SYSTEM, collapsedIds), [collapsedIds]);
  const selectedBody = useMemo(() => findBody(MOCK_SYSTEM, selectedBodyId) ?? MOCK_SYSTEM, [selectedBodyId]);
  const selectedStructures = useMemo(
    () => collectVisibleStructures(selectedBody, showProjection, projectionMode),
    [projectionMode, selectedBody, showProjection],
  );

  const toggleCollapse = (id: string) => {
    setCollapsedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <section
      aria-label="Static Raven-style colony planner prototype"
      data-testid="raven-style-planner-prototype"
      className="space-y-3"
    >
      <header className="flex flex-col gap-3 border-b border-orange/20 bg-bg1/60 px-3 py-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
            Prototype - visual direction, not live planner data
          </div>
          <h1 className="mt-2 truncate font-display text-2xl text-orange">
            Colony Build Canvas
          </h1>
          <p className="mt-1 font-mono text-xs text-silver-dk">
            Praea Eug WV-W b2-2 / topology, slots, facility economy, calculator telemetry.
          </p>
        </div>
        <PrototypeControls
          showProjection={showProjection}
          detailedRows={detailedRows}
          projectionMode={projectionMode}
          onProjectionToggle={() => setShowProjection((value) => !value)}
          onDetailToggle={() => setDetailedRows((value) => !value)}
          onProjectionModeChange={setProjectionMode}
        />
      </header>

      <div
        data-testid="prototype-planner-layout"
        data-layout="wide-telemetry"
        className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_32rem] 2xl:grid-cols-[minmax(0,1fr)_36rem]"
      >
        <main
          aria-label="Continuous whole-system planner canvas"
          data-testid="raven-style-continuous-canvas"
          className="min-w-0 overflow-x-auto rounded-chunk-lg border border-orange/30 bg-bg1/85 shadow-metal"
        >
          <div className="min-w-[980px]">
            <CanvasColumnHeader />
            <div className="divide-y divide-border/45">
              {visibleBodies.map((body) => (
                <CanvasBodyRow
                  key={body.node.id}
                  body={body}
                  selected={body.node.id === selectedBodyId}
                  collapsed={collapsedIds.has(body.node.id)}
                  detailed={detailedRows}
                  showProjection={showProjection}
                  projectionMode={projectionMode}
                  onSelect={() => setSelectedBodyId(body.node.id)}
                  onToggleCollapse={() => toggleCollapse(body.node.id)}
                />
              ))}
            </div>
          </div>
        </main>

        <aside
          data-testid="raven-style-stat-panel"
          data-layout="wide-telemetry"
          className="sticky top-24 self-start rounded-chunk border border-cyan/25 bg-bg2/95 p-3 xl:max-h-[calc(100vh-8rem)] xl:overflow-y-auto"
        >
          <div className="flex items-center gap-2 border-b border-border/45 pb-2">
            <div className="grid h-8 w-8 place-items-center rounded border border-orange/35 bg-orange/10 text-orange">
              <Target size={17} />
            </div>
            <div>
              <h2 className="font-display text-sm text-orange">Planning Telemetry</h2>
              <p className="font-mono text-[10px] text-silver-dk">System calculator</p>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 border-b border-border/35 pb-3">
            <TelemetryMetric label="System score" value="60" />
            <TelemetryMetric label="Population" value="1.11B" />
            <TelemetryMetric label="Planned haul" value="664k U" />
            <TelemetryMetric label="Build staged" value="11 / 28" />
          </div>

          <div className="mt-4 space-y-2">
            {SYSTEM_STAT_DELTAS.map((stat) => (
              <ZeroCenteredStatBar
                key={stat.id}
                id={stat.id}
                label={stat.label}
                value={stat.value}
                color={stat.color}
              />
            ))}
          </div>

          <div className="mt-4 border-t border-border/70 pt-3">
            <h3 className="font-mono text-[11px] uppercase tracking-[0.12em] text-cyan">Economy mix and strength</h3>
            <p className="mt-1 font-mono text-[10px] text-silver-dk">Bar = share. Number = bonus strength.</p>
            <div className="mt-2 space-y-2">
              {SYSTEM_ECONOMY_OUTCOME.map((item) => (
                <EconomyOutcomeRow key={item.kind} item={item} />
              ))}
            </div>
          </div>

          <div className="mt-4 border-t border-border/35 pt-3">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-orange">
              <Sparkles size={14} />
              Active projection
            </div>
            <p className="mt-1 font-mono text-[11px] leading-relaxed text-silver-dk">
              {projectionMode === 'balanced'
                ? 'Balanced ghosts: industry, agriculture, relay, support.'
                : 'Security ghosts: garrison and stabiliser sites.'}
            </p>
          </div>

          <div className="mt-4 border-t border-cyan/25 pt-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">Selected body</div>
            <div className="mt-1 font-display text-base text-silver">{selectedBody.name}</div>
            <div className="mt-1 font-mono text-[11px] text-silver-dk">{selectedBody.bodyClass}</div>
            <div className="mt-3 space-y-2 border-t border-cyan/15 pt-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-cyan">Body economy</div>
              <div className="space-y-1.5">
                {normalizeEconomyReadouts(selectedBody.economy, showProjection).map((item) => (
                  <EconomyOutcomeRow key={item.kind} item={item} compact />
                ))}
              </div>
            </div>
            <div className="mt-3 space-y-2 border-t border-cyan/15 pt-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-cyan">Selected structures</div>
              {selectedStructures.length > 0 ? selectedStructures.map((slot) => (
                <StructureEconomyDetailRow key={slot.id} slot={slot} body={selectedBody} />
              )) : (
                <div className="font-mono text-[11px] text-silver-dk">No visible structures in this prototype state.</div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}

function PrototypeControls({
  showProjection,
  detailedRows,
  projectionMode,
  onProjectionToggle,
  onDetailToggle,
  onProjectionModeChange,
}: {
  showProjection: boolean;
  detailedRows: boolean;
  projectionMode: ProjectionMode;
  onProjectionToggle: () => void;
  onDetailToggle: () => void;
  onProjectionModeChange: (mode: ProjectionMode) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        onClick={onProjectionToggle}
        className="inline-flex items-center gap-2 rounded-chunk-sm border border-cyan/40 bg-cyan/10 px-3 py-2 font-mono text-xs font-bold uppercase tracking-[0.12em] text-cyan hover:border-cyan hover:bg-cyan/15"
      >
        {showProjection ? <EyeOff size={14} /> : <Eye size={14} />}
        {showProjection ? 'Hide projected build' : 'Show projected build'}
      </button>
      <button
        type="button"
        onClick={onDetailToggle}
        className="inline-flex items-center gap-2 rounded-chunk-sm border border-border bg-bg3/70 px-3 py-2 font-mono text-xs font-bold uppercase tracking-[0.12em] text-silver hover:border-orange/50 hover:text-orange"
      >
        <Layers3 size={14} />
        {detailedRows ? 'Compact rows' : 'Detailed rows'}
      </button>
      <div className="inline-flex overflow-hidden rounded-chunk-sm border border-border bg-bg3/70">
        {(['balanced', 'security'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => onProjectionModeChange(mode)}
            className={[
              'px-3 py-2 font-mono text-xs font-bold uppercase tracking-[0.12em]',
              projectionMode === mode
                ? 'bg-orange/20 text-orange'
                : 'text-silver-dk hover:bg-bg4/70 hover:text-silver',
            ].join(' ')}
          >
            {mode === 'balanced' ? 'Balanced projection' : 'Security projection'}
          </button>
        ))}
      </div>
    </div>
  );
}

function CanvasColumnHeader() {
  const gridStyle: CSSProperties = {
    gridTemplateColumns: '280px minmax(320px,1fr) minmax(360px,1.08fr)',
  };

  return (
    <div
      className="grid border-b border-orange/30 bg-bg2/85 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk"
      style={gridStyle}
    >
      <div className="text-cyan">System tree</div>
      <div>Orbital lane</div>
      <div>Ground lane</div>
    </div>
  );
}

function CanvasBodyRow({
  body,
  selected,
  collapsed,
  detailed,
  showProjection,
  projectionMode,
  onSelect,
  onToggleCollapse,
}: {
  body: FlatBody;
  selected: boolean;
  collapsed: boolean;
  detailed: boolean;
  showProjection: boolean;
  projectionMode: ProjectionMode;
  onSelect: () => void;
  onToggleCollapse: () => void;
}) {
  const { node } = body;
  const structures = collectVisibleStructures(node, showProjection, projectionMode);
  const gridStyle: CSSProperties = {
    gridTemplateColumns: '280px minmax(320px,1fr) minmax(360px,1.08fr)',
  };

  return (
    <div
      data-testid={`prototype-body-row-${node.id}`}
      className={[
        'transition-colors',
        selected ? 'bg-orange/10 shadow-[inset_3px_0_0_rgba(255,122,20,0.95)]' : 'bg-transparent hover:bg-bg3/35',
      ].join(' ')}
    >
      <div
        className={[
          'grid items-stretch px-3',
          detailed ? 'min-h-[76px] py-2' : 'min-h-[58px] py-1.5',
        ].join(' ')}
        style={gridStyle}
      >
        <TreeCell
          body={body}
          selected={selected}
          collapsed={collapsed}
          detailed={detailed}
          onSelect={onSelect}
          onToggleCollapse={onToggleCollapse}
        />
        <SlotLane body={node} lane="orbital" slots={node.orbitalSlots} showProjection={showProjection} projectionMode={projectionMode} />
        <SlotLane body={node} lane="ground" slots={node.groundSlots} showProjection={showProjection} projectionMode={projectionMode} />
      </div>
      {detailed && structures.length > 0 && (
        <DetailedStructureList body={node} structures={structures} />
      )}
    </div>
  );
}

function TreeCell({
  body,
  selected,
  collapsed,
  detailed,
  onSelect,
  onToggleCollapse,
}: {
  body: FlatBody;
  selected: boolean;
  collapsed: boolean;
  detailed: boolean;
  onSelect: () => void;
  onToggleCollapse: () => void;
}) {
  const { node, depth, guide, isLast } = body;
  const markerLeft = 18 + depth * 30;
  const hasChildren = Boolean(node.children?.length);
  const markerStyle = MARKER_STYLES[node.marker];

  return (
    <div className="relative min-h-full">
      {guide.map((continues, index) => continues && (
        <span
          key={index}
          aria-hidden
          className="absolute bottom-[-0.5rem] top-[-0.5rem] w-px bg-cyan/35"
          style={{ left: 18 + index * 30 }}
        />
      ))}
      {depth > 0 && (
        <>
          <span
            aria-hidden
            className="absolute top-[-0.5rem] h-[calc(50%+0.5rem)] w-px bg-cyan/45"
            style={{ left: markerLeft }}
          />
          {!isLast && (
            <span
              aria-hidden
              className="absolute bottom-[-0.5rem] top-1/2 w-px bg-cyan/45"
              style={{ left: markerLeft }}
            />
          )}
          <span
            aria-hidden
            className="absolute top-1/2 h-px bg-cyan/45"
            style={{ left: markerLeft - 30, width: 30 }}
          />
        </>
      )}

      {hasChildren && (
        <button
          type="button"
          onClick={onToggleCollapse}
          aria-label={`${collapsed ? 'Expand' : 'Collapse'} ${node.name}`}
          className="absolute top-1/2 z-10 grid h-5 w-5 -translate-y-1/2 place-items-center rounded border border-border bg-bg2 text-silver hover:border-orange/50 hover:text-orange"
          style={{ left: markerLeft - 10 }}
        >
          {collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
        </button>
      )}

      <button
        type="button"
        onClick={onSelect}
        data-testid={`prototype-body-select-${node.id}`}
        className="absolute inset-y-0 right-1 z-10 flex items-center rounded-chunk-sm border border-transparent text-left hover:border-cyan/35 focus:outline-none focus-visible:border-orange"
        style={{ left: markerLeft + 4 }}
      >
        <span
          aria-hidden
          className={[
            'mr-3 shrink-0 rounded-full border shadow-[0_0_18px_-6px_currentColor]',
            markerStyle.size,
            selected ? 'ring-2 ring-orange/70' : '',
          ].join(' ')}
          style={{ background: markerStyle.fill, borderColor: markerStyle.ring, color: markerStyle.ring }}
        />
        <span className="min-w-0">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate font-display text-sm text-silver">{node.name}</span>
            {node.primaryCandidate && (
              <span className="inline-flex items-center gap-1 rounded border border-gold/40 bg-gold/10 px-1.5 py-0.5 font-mono text-[9px] uppercase text-gold">
                <LocateFixed size={10} />
                Primary
              </span>
            )}
            {node.warning && (
              <span title={node.warning} className="text-gold">
                <TriangleAlert size={14} />
              </span>
            )}
          </span>
          <span className="mt-1 block truncate font-mono text-[11px] text-silver-dk">{node.bodyClass}</span>
          {detailed && <span className="mt-0.5 block truncate font-mono text-[10px] text-text-dim">{node.detail}</span>}
        </span>
      </button>
    </div>
  );
}

function SlotLane({
  body,
  lane,
  slots,
  showProjection,
  projectionMode,
}: {
  body: BodyNode;
  lane: LaneKind;
  slots: SlotModel[];
  showProjection: boolean;
  projectionMode: ProjectionMode;
}) {
  const visibleSlots = slots.map((slot) => normalizeSlot(slot, showProjection, projectionMode));
  const knownCount = slots.length === 0 ? '0' : slots.every((slot) => slot.kind === 'unknown') ? '?' : String(slots.filter((slot) => slot.kind !== 'overflow').length);

  return (
    <div data-testid={`${body.id}-${lane}-lane`} className="flex min-w-0 items-center gap-2 pr-2">
      <span className="w-9 shrink-0 font-mono text-[10px] uppercase tracking-[0.1em] text-cyan">
        {lane === 'orbital' ? `O${knownCount}` : `G${knownCount}`}
      </span>
      <div className="flex min-w-0 flex-wrap gap-1.5">
        {visibleSlots.length === 0 ? (
          <span className="rounded border border-border/70 bg-bg2 px-2 py-1 font-mono text-[10px] uppercase text-silver-2">None</span>
        ) : visibleSlots.map((slot) => (
          <SlotBox key={slot.id} slot={slot} body={body} lane={lane} />
        ))}
      </div>
    </div>
  );
}

function SlotBox({ slot, body, lane }: { slot: SlotModel; body: BodyNode; lane: LaneKind }) {
  const color = slot.economy ? ECONOMY_COLORS[slot.economy] : undefined;
  const commonTestId = `${body.id}-${lane}-slot`;
  const economyProfile = getStructureEconomyProfile(slot, body);
  const isStructureSlot = Boolean(slot.label && (slot.kind === 'planned' || slot.kind === 'projected' || slot.kind === 'overflow'));
  const compactLabel = formatSlotCompactLabel(slot);
  const title = formatSlotTitle(slot, body, lane, economyProfile);
  const statusLabel = slot.kind === 'projected' ? 'PROJ' : slot.kind === 'planned' ? 'PLAN' : slot.kind === 'overflow' ? 'OVER' : '';
  const slotStyle: CSSProperties = {};
  if (slot.kind === 'planned' && color) {
    slotStyle.borderColor = color;
    slotStyle.background = `linear-gradient(180deg, ${color}24, rgba(18,20,24,0.9))`;
  }
  if (slot.kind === 'projected' && color) {
    slotStyle.borderColor = color;
    slotStyle.background = `linear-gradient(180deg, ${color}1f, rgba(18,20,24,0.48))`;
  }
  if (slot.kind === 'invalid') {
    slotStyle.background = 'repeating-linear-gradient(135deg, rgba(248,113,113,0.18) 0 6px, rgba(18,20,24,0.72) 6px 12px)';
  }

  return (
    <span
      data-testid={commonTestId}
      title={title}
      className={[
        'group/slot relative flex overflow-hidden rounded border px-1.5 text-center font-mono text-[10px] font-bold uppercase leading-tight tracking-[0.03em] transition',
        isStructureSlot
          ? 'h-10 min-w-[92px] max-w-[136px] items-start justify-center pb-2.5 pt-3'
          : 'h-8 min-w-[72px] max-w-[108px] items-center justify-center',
        'hover:-translate-y-0.5 hover:border-orange-lt hover:shadow-brand-glow',
        slot.kind === 'empty' && 'border-border/70 bg-bg2/75 text-silver-2',
        slot.kind === 'planned' && 'text-silver',
        slot.kind === 'projected' && 'border-dashed text-cyan opacity-75',
        slot.kind === 'unknown' && 'border-dashed border-gold/65 bg-gold/10 text-gold',
        slot.kind === 'invalid' && 'border-red/50 text-red',
        slot.kind === 'overflow' && 'border-orange bg-orange/20 text-orange-lt',
      ].filter(Boolean).join(' ')}
      style={slotStyle}
    >
      {slot.kind === 'projected' && <span data-testid="projected-ghost-structure" className="sr-only">{slot.label}</span>}
      {slot.primary && (
        <span className="absolute left-1 top-1 h-1.5 w-1.5 rounded-full bg-gold shadow-[0_0_8px_rgba(251,191,36,0.8)]" />
      )}
      {statusLabel && (
        <span className={slot.kind === 'projected' ? 'absolute right-1 top-0.5 text-[7px] text-cyan' : 'absolute right-1 top-0.5 text-[7px] text-silver-dk'}>
          {statusLabel}
        </span>
      )}
      <span data-testid={isStructureSlot ? 'structure-slot-pill' : undefined} className="max-w-full truncate">
        {compactLabel}
      </span>
      {economyProfile.length > 0 && <StructureEconomyMicroBar profile={economyProfile} variant="slot" />}
    </span>
  );
}

function DetailedStructureList({
  body,
  structures,
}: {
  body: BodyNode;
  structures: SlotModel[];
}) {
  const gridStyle: CSSProperties = {
    gridTemplateColumns: '280px minmax(0,1fr)',
  };

  return (
    <div className="grid border-t border-cyan/10 px-3 pb-2 pt-1.5" style={gridStyle}>
      <div />
      <div data-testid="expanded-structure-list" className="space-y-1.5">
        {structures.map((slot) => {
          const economyProfile = getStructureEconomyProfile(slot, body);
          const color = economyProfile[0]?.kind ? ECONOMY_COLORS[economyProfile[0].kind] : slot.economy ? ECONOMY_COLORS[slot.economy] : '#c8ccd1';
          const title = formatSlotTitle(slot, body, slot.id.includes('-o-') ? 'orbital' : 'ground', economyProfile);
          return (
            <div
              key={slot.id}
              data-testid="expanded-structure-row"
              title={title}
              className={[
                'grid grid-cols-[minmax(160px,0.9fr)_auto_minmax(240px,1.25fr)] items-center gap-2 rounded-sm bg-bg2/45 px-2 py-1',
                slot.kind === 'projected' ? 'text-cyan opacity-75' : 'text-silver',
              ].join(' ')}
            >
              <div className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.08em]">
                <span className="h-2 w-2 shrink-0 rounded-sm" style={{ backgroundColor: color }} />
                <span className="truncate">{slot.kind === 'projected' ? 'ghost ' : ''}{slot.label}</span>
              </div>
              <span className={slot.kind === 'projected' ? 'justify-self-end font-mono text-[9px] uppercase text-cyan' : 'justify-self-end font-mono text-[9px] uppercase text-silver-dk'}>
                {slot.kind === 'projected' ? 'projected' : slot.kind === 'overflow' ? 'overflow' : 'planned'}
              </span>
              <StructureEconomyMicroBar profile={economyProfile} variant="row" />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StructureEconomyMicroBar({
  profile,
  variant,
}: {
  profile: StructureEconomySegment[];
  variant: 'slot' | 'row' | 'detail';
}) {
  if (profile.length === 0) return null;

  const totalShare = Math.max(1, profile.reduce((sum, item) => sum + item.share, 0));
  const title = [
    'Share = relative economy mix. Bonus = combined structure + body strength.',
    profile.map((item) => `${item.kind} ${item.share}% share | ${formatBonus(item.bonus)} bonus`).join(' / '),
  ].join(' ');

  if (variant === 'slot') {
    return (
      <span
        data-testid="structure-economy-micro-bar"
        aria-label={title}
        title={title}
        className="absolute inset-x-0 bottom-0 flex h-1 overflow-hidden bg-bg4/80"
      >
        {profile.map((item) => (
          <span
            key={item.kind}
            className={item.projected ? 'opacity-60' : ''}
            style={{
              width: `${(item.share / totalShare) * 100}%`,
              backgroundColor: ECONOMY_COLORS[item.kind],
            }}
          />
        ))}
      </span>
    );
  }

  return (
    <div
      data-testid="structure-economy-micro-bar"
      aria-label={title}
      title={title}
      className={variant === 'detail' ? 'mt-2' : 'mt-1'}
    >
      <div className="grid grid-cols-[minmax(68px,1fr)_auto] items-center gap-2">
        <div className="flex h-1.5 overflow-hidden rounded-sm bg-bg4/85">
          {profile.map((item) => (
            <span
              key={item.kind}
              className={item.projected ? 'opacity-60' : ''}
              style={{
                width: `${(item.share / totalShare) * 100}%`,
                backgroundColor: ECONOMY_COLORS[item.kind],
              }}
            />
          ))}
        </div>
        <div className="truncate text-right font-mono text-[9px] uppercase tracking-[0.06em] text-silver">
          {profile.slice(0, variant === 'detail' ? 3 : 2).map((item) => `${ECONOMY_ABBREVIATIONS[item.kind]} ${item.share}%`).join(' / ')}
        </div>
      </div>
      <div className="mt-1 flex min-w-0 flex-wrap gap-x-2 gap-y-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-silver-dk">
        {profile.slice(0, variant === 'detail' ? 3 : 2).map((item) => (
          <span key={item.kind} className="whitespace-nowrap">
            {ECONOMY_ABBREVIATIONS[item.kind]} bonus {formatBonus(item.bonus)}
          </span>
        ))}
      </div>
    </div>
  );
}

function StructureEconomyDetailRow({ slot, body }: { slot: SlotModel; body: BodyNode }) {
  const profile = getStructureEconomyProfile(slot, body);

  return (
    <div
      data-testid="structure-economy-detail"
      className={[
        'rounded-chunk-sm border p-2',
        slot.kind === 'projected' ? 'border-cyan/25 bg-cyan/10' : 'border-border/70 bg-bg3/55',
      ].join(' ')}
    >
      <div className="flex min-w-0 items-center justify-between gap-2 font-mono text-[11px]">
        <span className={slot.kind === 'projected' ? 'truncate text-cyan' : 'truncate text-silver'}>
          {slot.kind === 'projected' ? 'ghost ' : ''}{slot.label}
        </span>
        <span className="shrink-0 text-silver-dk">{slot.kind === 'projected' ? 'projected' : 'placed'}</span>
      </div>
      <StructureEconomyMicroBar profile={profile} variant="detail" />
      <div className="mt-2 space-y-1">
        {profile.slice(0, 3).map((item) => (
          <div key={item.kind} className="grid grid-cols-[1fr_auto] gap-2 font-mono text-[10px] leading-snug">
            <span className="text-silver">
              {item.kind} {item.share}% share | {formatBonus(item.bonus)}
            </span>
            <span className="text-right text-silver-dk">
              {formatBonus(item.structureBonus)} structure / {formatBonus(item.bodyBonus)} body
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TelemetryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-2 font-mono">
      <div className="truncate text-[9px] uppercase tracking-[0.12em] text-silver-dk">{label}</div>
      <div className="text-right font-display text-sm text-silver">{value}</div>
    </div>
  );
}

function ZeroCenteredStatBar({
  id,
  label,
  value,
  color,
}: {
  id: string;
  label: string;
  value: number;
  color: string;
}) {
  const direction = value < 0 ? 'negative' : value > 0 ? 'positive' : 'neutral';
  const halfWidth = value === 0 ? 0 : Math.max(5, Math.min(50, (Math.abs(value) / 32) * 50));

  return (
    <div
      data-testid="zero-centered-stat-bar"
      data-stat-id={id}
      data-direction={direction}
      className="grid grid-cols-[6.5rem_1fr_3.3rem] items-center gap-2 font-mono text-[11px]"
    >
      <span className="truncate text-silver-dk">{label}</span>
      <span className="relative h-4 overflow-hidden rounded-sm border border-border/60 bg-bg4/80 shadow-inner-soft">
        <span
          data-testid={`stat-${id}-zero-axis`}
          aria-hidden
          className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-silver/55"
        />
        <span
          data-testid={`stat-${id}-negative`}
          data-tone="negative-red"
          aria-hidden
          className="absolute right-1/2 top-1/2 h-2 -translate-y-1/2 rounded-l-sm"
          style={{
            width: direction === 'negative' ? `${halfWidth}%` : '0%',
            backgroundColor: '#f87171',
            boxShadow: direction === 'negative' ? '0 0 10px rgba(248,113,113,0.35)' : undefined,
          }}
        />
        <span
          data-testid={`stat-${id}-positive`}
          data-tone="positive-green"
          aria-hidden
          className="absolute left-1/2 top-1/2 h-2 -translate-y-1/2 rounded-r-sm"
          style={{
            width: direction === 'positive' ? `${halfWidth}%` : '0%',
            backgroundColor: color,
            boxShadow: direction === 'positive' ? `0 0 10px ${color}55` : undefined,
          }}
        />
      </span>
      <span className={direction === 'negative' ? 'text-right text-red' : 'text-right text-silver'}>
        {formatSignedStat(value)}
      </span>
    </div>
  );
}

function EconomyOutcomeRow({ item, compact = false }: { item: EconomyReadout; compact?: boolean }) {
  return (
    <div
      data-testid="economy-outcome-row"
      title={`${item.kind}: ${item.share}% share; ${formatBonus(item.bonus)} bonus strength`}
      className={compact ? 'grid grid-cols-[4.7rem_1fr_4.8rem] items-center gap-2 font-mono text-[10px]' : 'grid grid-cols-[5.5rem_1fr_5.4rem] items-center gap-2 font-mono text-[10px]'}
    >
      <span className="truncate text-silver-dk">{item.kind}</span>
      <span className="h-2 overflow-hidden rounded-sm bg-bg4">
        <span
          className="block h-full"
          style={{
            width: `${Math.min(100, item.share)}%`,
            backgroundColor: ECONOMY_COLORS[item.kind],
          }}
        />
      </span>
      <span className="text-right text-silver">
        {item.share}% | {formatBonus(item.bonus)}
      </span>
    </div>
  );
}

function normalizeEconomyReadouts(contributions: EconomyContribution[], showProjection: boolean): EconomyReadout[] {
  const visible = contributions.filter((item) => showProjection || !item.projected);
  const hasExplicitShare = visible.some((item) => item.share !== undefined);
  const totalValue = Math.max(1, visible.reduce((sum, item) => sum + (item.value ?? 0), 0));

  return visible
    .map((item) => {
      const value = item.value ?? 0;
      const share = item.share ?? (hasExplicitShare ? value : Math.round((value / totalValue) * 100));
      const bonus = item.bonus ?? Math.round(value * 100);

      return {
        kind: item.kind,
        share,
        bonus,
        projected: item.projected,
      };
    })
    .sort((left, right) => right.share - left.share);
}

function getStructureEconomyProfile(slot: SlotModel, body: BodyNode): StructureEconomySegment[] {
  if (!slot.label || slot.kind === 'empty' || slot.kind === 'unknown' || slot.kind === 'invalid') {
    return [];
  }

  const effects = slot.economyEffects ?? (slot.economy ? [{
    kind: slot.economy,
    structureBonus: DEFAULT_STRUCTURE_BONUS[slot.economy],
  }] : []);

  const modifierByKind = new Map((body.economyModifiers ?? []).map((modifier) => [modifier.kind, modifier]));
  const raw = effects.map((effect) => {
    const bodyBonus = modifierByKind.get(effect.kind)?.bonus ?? 0;

    return {
      kind: effect.kind,
      structureBonus: effect.structureBonus,
      bodyBonus,
      bonus: effect.structureBonus + bodyBonus,
      projected: slot.kind === 'projected' || effect.projected,
    };
  }).filter((item) => item.bonus > 0);
  const total = Math.max(1, raw.reduce((sum, item) => sum + item.bonus, 0));

  return raw
    .map((item) => ({
      ...item,
      share: Math.max(1, Math.round((item.bonus / total) * 100)),
    }))
    .sort((left, right) => right.bonus - left.bonus);
}

function formatBonus(value: number): string {
  return `${value >= 0 ? '+' : ''}${value}%`;
}

function formatSignedStat(value: number): string {
  return `${value > 0 ? '+' : ''}${value}`;
}

function formatSlotCompactLabel(slot: SlotModel): string {
  if (slot.kind === 'empty') return '';
  if (slot.kind === 'unknown') return slot.label ?? '?';
  if (slot.kind === 'invalid') return slot.label ?? 'No build';
  if (slot.kind === 'overflow') return slot.label ?? '+1 overflow';

  const label = slot.label ?? '?';
  const compact = STRUCTURE_COMPACT_LABELS[label] ?? compactStructureLabel(label);
  return slot.kind === 'projected' ? `Ghost ${compact}` : compact;
}

function compactStructureLabel(label: string): string {
  const words = label.split(/\s+/).filter(Boolean);
  if (words.length <= 2) return label;

  const facilityIndex = words.findIndex((word) => [
    'Starport',
    'Hub',
    'Outpost',
    'Lab',
    'Installation',
    'Dome',
    'Relay',
    'Prospect',
    'Beacon',
    'Port',
  ].includes(word));

  if (facilityIndex > 0) {
    return `${words[facilityIndex - 1]} ${words[facilityIndex]}`;
  }

  return words.slice(0, 2).join(' ');
}

function formatSlotTitle(
  slot: SlotModel,
  body: BodyNode,
  lane: LaneKind,
  profile: StructureEconomySegment[],
): string {
  const label = slot.label ?? (slot.kind === 'empty' ? 'Empty slot' : 'Unknown slot');
  const status = slot.kind === 'projected'
    ? 'Projected'
    : slot.kind === 'planned'
      ? 'Planned'
      : slot.kind === 'overflow'
        ? 'Overflow'
        : slot.kind === 'invalid'
          ? 'Unavailable'
          : slot.kind === 'unknown'
            ? 'Unknown'
            : 'Empty';
  const economy = profile.length > 0
    ? profile.slice(0, 3).map((item) => (
      `${item.kind} ${item.share}% share / ${formatBonus(item.bonus)} bonus (${formatBonus(item.structureBonus)} structure, ${formatBonus(item.bodyBonus)} body)`
    )).join(' | ')
    : 'No economy contribution';

  return `${label} | Body: ${body.name} | Lane: ${lane} | Status: ${status} | Economy: ${economy}${slot.hint ? ` | ${slot.hint}` : ''}`;
}

function normalizeSlot(slot: SlotModel, showProjection: boolean, projectionMode: ProjectionMode): SlotModel {
  if (slot.kind !== 'projected') return slot;
  const modeMatches = slot.projection === 'both' || slot.projection === projectionMode;
  if (showProjection && modeMatches) return slot;
  return { id: slot.id, kind: 'empty' };
}

function collectVisibleStructures(
  body: BodyNode,
  showProjection: boolean,
  projectionMode: ProjectionMode,
): SlotModel[] {
  return [...body.orbitalSlots, ...body.groundSlots]
    .map((slot) => normalizeSlot(slot, showProjection, projectionMode))
    .filter((slot) => slot.label && (slot.kind === 'planned' || slot.kind === 'projected' || slot.kind === 'overflow'));
}

function flattenBodies(root: BodyNode, collapsedIds: Set<string>): FlatBody[] {
  const rows: FlatBody[] = [];

  const visit = (node: BodyNode, depth: number, guide: boolean[], isLast: boolean) => {
    rows.push({ node, depth, guide, isLast });
    if (collapsedIds.has(node.id)) return;
    node.children?.forEach((child, index, siblings) => {
      visit(child, depth + 1, [...guide, !isLast], index === siblings.length - 1);
    });
  };

  visit(root, 0, [], true);
  return rows;
}

function findBody(root: BodyNode, id: string): BodyNode | null {
  if (root.id === id) return root;
  for (const child of root.children ?? []) {
    const found = findBody(child, id);
    if (found) return found;
  }
  return null;
}
