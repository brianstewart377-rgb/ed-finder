import { useCallback, useEffect, useRef, useState } from 'react';
import {
  applyPreset,
  BODY_SLIDERS,
  type SearchFilters,
  type BodyRange,
} from './useSearch';
import { DualSlider } from '@/components/DualSlider';
import {
  ArrowDownUp,
  Check,
  ChevronRight,
  Factory,
  Footprints,
  Gem,
  Globe2,
  ListChecks,
  MapPin,
  Radar,
  RadioTower,
  RotateCcw,
  Search,
  Star,
} from 'lucide-react';
import { RefSystemPicker } from './RefSystemPicker';
import { hasKnownCoords } from '@/lib/format';
import { Select } from '@/components/ui/Select';
import {
  distanceSummary,
  ECONOMY_OPTIONS,
  rangeGroupSummary,
  SLIDER_GROUPS,
  sortLabel,
  systemProfileSummary,
  type FilterSectionId,
} from './searchFormConfig';
import {
  CheckboxRow,
  FilterWorkspaceHeader,
  QuickPresets,
  RangeRow,
  WorkspaceSection,
} from './SearchFormControls';

export interface SearchFormProps {
  filters: SearchFilters;
  onChange: (patch: Partial<SearchFilters>) => void;
  onSubmit: () => void;
  onReset: () => void;
  loading?: boolean;
  onWorkspaceChange?: (open: boolean) => void;
}

export function SearchForm({
  filters,
  onChange,
  onSubmit,
  onReset,
  loading,
  onWorkspaceChange,
}: SearchFormProps) {
  const [referencePending, setReferencePending] = useState(false);
  const [activeSection, setActiveSection] = useState<FilterSectionId | null>(null);
  const triggerRefs = useRef<Partial<Record<FilterSectionId, HTMLButtonElement | null>>>({});

  const openSection = (section: FilterSectionId) => {
    setActiveSection(section);
    onWorkspaceChange?.(true);
  };

  const closeSection = useCallback(() => {
    const previous = activeSection;
    setActiveSection(null);
    onWorkspaceChange?.(false);
    if (previous) triggerRefs.current[previous]?.focus();
  }, [activeSection, onWorkspaceChange]);

  useEffect(() => {
    if (!activeSection) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeSection();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [activeSection, closeSection]);

  const sliderGroups = SLIDER_GROUPS.map((group) => ({
    ...group,
    sliders: BODY_SLIDERS.filter((slider) => group.keys.some((key) => key === slider.key)),
  }));

  const navigationItems: {
    id: FilterSectionId;
    index: string;
    label: string;
    summary: string;
    iconName: string;
    icon: React.ReactNode;
  }[] = [
    {
      id: 'reference',
      index: '01',
      label: 'Origin system',
      summary: `Distances measured from ${filters.refName}`,
      iconName: 'origin',
      icon: <MapPin size={18} strokeWidth={1.8} />,
    },
    {
      id: 'presets',
      index: '02',
      label: 'Search profiles',
      summary: 'Ready-made searches for common goals',
      iconName: 'profiles',
      icon: <ListChecks size={18} strokeWidth={1.8} />,
    },
    {
      id: 'distance',
      index: '03',
      label: 'Range & results',
      summary: distanceSummary(filters),
      iconName: 'range',
      icon: <Radar size={18} strokeWidth={1.8} />,
    },
    {
      id: 'system',
      index: '04',
      label: 'Settlement & economy',
      summary: systemProfileSummary(filters),
      iconName: 'system',
      icon: <Factory size={18} strokeWidth={1.8} />,
    },
    ...sliderGroups.map((group, index) => {
      const groupIcons = {
        'high-value': <Gem size={18} strokeWidth={1.8} />,
        stars: <Star size={18} strokeWidth={1.8} />,
        landable: <Footprints size={18} strokeWidth={1.8} />,
        planetary: <Globe2 size={18} strokeWidth={1.8} />,
        signals: <RadioTower size={18} strokeWidth={1.8} />,
      };
      return {
        id: group.id,
        index: String(index + 5).padStart(2, '0'),
        label: group.shortLabel,
        summary: rangeGroupSummary(filters, group.keys, group.summary),
        iconName: group.id,
        icon: groupIcons[group.id],
      };
    }),
    {
      id: 'sort',
      index: '10',
      label: 'Sort results',
      summary: sortLabel(filters.sortBy),
      iconName: 'sort',
      icon: <ArrowDownUp size={18} strokeWidth={1.8} />,
    },
  ];

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      className="finder-filter-console"
      data-testid="search-form"
      data-workspace-open={activeSection ? 'true' : 'false'}
    >
      <div className="finder-filter-array">
        <div className="finder-filter-array__heading">
          <span>Search filters</span>
        </div>

        <nav className="finder-filter-array__modules" aria-label="Search filter categories">
          {navigationItems.map((item) => {
            const active = activeSection === item.id;
            return (
              <button
                key={item.id}
                ref={(node) => {
                  triggerRefs.current[item.id] = node;
                }}
                type="button"
                onClick={() => active ? closeSection() : openSection(item.id)}
                className="finder-filter-module"
                data-active={active ? 'true' : 'false'}
                data-testid={`filter-module-${item.id}`}
                aria-expanded={active}
                aria-controls={active ? 'finder-filter-workspace' : undefined}
              >
                <span className="finder-filter-module__index">{item.index}</span>
                <span
                  className="finder-filter-module__icon"
                  data-icon={item.iconName}
                  aria-hidden
                >
                  {item.icon}
                </span>
                <span className="finder-filter-module__copy">
                  <strong>{item.label}</strong>
                  <small>{item.summary}</small>
                </span>
                <ChevronRight className="finder-filter-module__chevron" size={15} aria-hidden />
              </button>
            );
          })}
        </nav>

        <div className="finder-filter-array__actions">
          <button
            type="submit"
            disabled={loading || referencePending}
            data-testid="search-submit"
            className="finder-search-action"
          >
            <Search size={17} aria-hidden />
            <span>{loading ? 'Scanning…' : referencePending ? 'Pick reference' : 'Run search'}</span>
          </button>
          <button
            type="button"
            onClick={onReset}
            data-testid="search-reset"
            className="finder-reset-action"
          >
            <RotateCcw size={14} aria-hidden />
            Reset
          </button>
        </div>
      </div>

      {activeSection && (
        <section
          id="finder-filter-workspace"
          className="finder-filter-workspace"
          data-testid="filter-workspace"
          aria-labelledby="finder-filter-workspace-title"
        >
          <FilterWorkspaceHeader
            section={activeSection}
            items={navigationItems}
            onClose={closeSection}
          />

          <div className="finder-filter-workspace__body">
            {activeSection === 'reference' && (
              <WorkspaceSection
                title="Choose where the scan begins"
                description="Choose the system distances should be measured from. Start typing and select a matching system."
              >
                <div className="finder-control-block">
                  <RefSystemPicker
                    value={filters.refName}
                    onPendingSelectionChange={setReferencePending}
                    onPick={(hit) => {
                      if (!hasKnownCoords(hit, hit.id64)) return;
                      onChange({
                        refName: hit.name,
                        refCoords: { x: hit.x, y: hit.y, z: hit.z },
                      });
                    }}
                  />
                  <p
                    className={referencePending ? 'finder-control-note finder-control-note--attention' : 'finder-control-note'}
                    data-testid="reference-system-status"
                  >
                    {referencePending
                      ? 'Pick a system from autocomplete to update the active reference.'
                      : `${filters.refName} is the current distance reference.`}
                  </p>
                </div>
              </WorkspaceSection>
            )}

            {activeSection === 'presets' && (
              <WorkspaceSection
                eyebrow="Prepared searches"
                title="Choose a starting profile"
                description="Start with a ready-made search for a common colony or exploration goal. You can change any filter afterwards."
              >
                <QuickPresets
                  onPick={(id) => onChange(applyPreset(filters, id) as Partial<SearchFilters>)}
                />
              </WorkspaceSection>
            )}

            {activeSection === 'distance' && (
              <WorkspaceSection
                eyebrow="Range and result limit"
                title="Define the search area"
                description="Choose how far from the origin to search and the maximum number of systems to show."
              >
                <div className="finder-control-grid">
                  <RangeRow
                    label="Minimum distance"
                    unit="LY"
                    min={0}
                    max={2000}
                    value={filters.minDistance}
                    onChange={(value) => onChange({ minDistance: Math.min(value, filters.maxDistance) })}
                  />
                  <RangeRow
                    label="Maximum distance"
                    unit="LY"
                    min={0}
                    max={2000}
                    value={filters.maxDistance}
                    onChange={(value) => onChange({ maxDistance: Math.max(value, filters.minDistance) })}
                  />
                  <RangeRow
                    label="Results per scan"
                    min={5}
                    max={500}
                    step={5}
                    value={filters.size}
                    onChange={(value) => onChange({ size: value })}
                  />
                  <CheckboxRow
                    label="Ignore distance and scan galaxy-wide"
                    checked={filters.galaxyWide}
                    onChange={(checked) => onChange({ galaxyWide: checked })}
                  />
                </div>
              </WorkspaceSection>
            )}

            {activeSection === 'system' && (
              <WorkspaceSection
                eyebrow="Settlement and economy"
                title="Choose the system context"
                description="Choose whether systems are inhabited, which economy they have, and how promising they must be for development."
              >
                <div className="finder-control-grid finder-control-grid--two">
                  <Select
                    label="Colony status"
                    value={filters.populated}
                    onChange={(value) => onChange({ populated: value as SearchFilters['populated'] })}
                    options={[
                      { value: 'any', label: 'Any' },
                      { value: 'populated', label: 'Inhabited only' },
                      { value: 'uninhabited', label: 'Non-colonised only' },
                    ]}
                  />
                  <Select
                    label="Primary economy"
                    value={filters.economy}
                    onChange={(value) => onChange({ economy: value })}
                    options={ECONOMY_OPTIONS}
                  />
                  <div className="finder-control-grid__wide">
                    <RangeRow
                      label="Minimum development score"
                      description="This 0–100 colony-development ranking filters out systems below the chosen value. Higher values return fewer, stronger candidates; 0 applies no minimum."
                      min={0}
                      max={100}
                      value={filters.minDevelopmentScore}
                      onChange={(value) => onChange({ minDevelopmentScore: value })}
                    />
                  </div>
                </div>
                <div className="finder-evidence-note">
                  <strong>Development score is a triage signal.</strong>
                  <span>Inspect and Colony Planner remain authoritative for evidence-backed planning decisions.</span>
                  <a href="#search-tuning" data-testid="open-search-tuning-link">
                    Open development tuning
                  </a>
                </div>
              </WorkspaceSection>
            )}

            {sliderGroups.map((group) => activeSection === group.id && (
              <WorkspaceSection
                key={group.id}
                eyebrow="Body composition"
                title={group.label}
                description={`${group.description} Adjust a range only when you want that body type to narrow the results.`}
              >
                <div className="finder-body-slider-grid">
                  {group.sliders.map((body) => {
                    const range = filters.bodyRanges[body.key] ?? { min: 0, max: body.max };
                    return (
                      <DualSlider
                        key={body.key}
                        label={body.label}
                        color={body.color}
                        min={0}
                        max={body.max}
                        value={range}
                        onChange={(nextRange: BodyRange) => onChange({
                          bodyRanges: { ...filters.bodyRanges, [body.key]: nextRange },
                        })}
                        testid={`body-slider-${body.key}`}
                      />
                    );
                  })}
                </div>
              </WorkspaceSection>
            ))}

            {activeSection === 'sort' && (
              <WorkspaceSection
                eyebrow="Result ordering"
                title="Choose which matches appear first"
                description="Choose which matching systems appear first. This does not change which systems qualify."
              >
                <div className="finder-control-block">
                  <Select
                    label="Order results by"
                    value={filters.sortBy}
                    onChange={(value) => onChange({ sortBy: value as SearchFilters['sortBy'] })}
                    options={[
                      { value: 'development', label: 'Development first' },
                      { value: 'distance', label: 'Distance nearest' },
                      { value: 'population', label: 'Population highest' },
                    ]}
                  />
                </div>
              </WorkspaceSection>
            )}
          </div>

          <div className="finder-filter-workspace__footer">
            <span>Changes apply immediately to this search setup</span>
            <button type="button" onClick={closeSection} data-testid="filter-workspace-done">
              <Check size={15} aria-hidden />
              Done
            </button>
          </div>
        </section>
      )}
    </form>
  );
}
