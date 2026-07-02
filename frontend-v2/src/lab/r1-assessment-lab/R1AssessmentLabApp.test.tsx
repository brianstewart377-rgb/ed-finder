import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import R1AssessmentLabApp from '@/lab/r1-assessment-lab/R1AssessmentLabApp';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function getSelect(label: string) {
  return screen.getByLabelText(label) as HTMLSelectElement;
}

function optionLabels(select: HTMLSelectElement) {
  return Array.from(select.options).map((option) => option.textContent);
}

function scenarioState(mode: 'no_carrier' | 'carrier_available') {
  return screen.getByTestId(`scenario-state-${mode}`).textContent;
}

function planFitState(mode: 'no_carrier' | 'carrier_available') {
  return screen.getByTestId(`plan-fit-state-${mode}`).textContent;
}

function assessmentContent(mode: 'no_carrier' | 'carrier_available') {
  return screen.getByTestId(`assessment-content-${mode}`).textContent;
}

function planFitReasons(mode: 'no_carrier' | 'carrier_available') {
  return screen.getByTestId(`plan-fit-reasons-${mode}`);
}

function setupSideEffectMocks() {
  const fetchSpy = vi.fn();
  const xhrOpenSpy = vi.fn();
  const webSocketSpy = vi.fn();
  const eventSourceSpy = vi.fn();
  const sendBeaconSpy = vi.fn();
  const localStorageSetSpy = vi.spyOn(Object.getPrototypeOf(window.localStorage), 'setItem');
  const sessionStorageSetSpy = vi.spyOn(Object.getPrototypeOf(window.sessionStorage), 'setItem');
  const indexedDbOpenSpy = vi.fn();

  vi.stubGlobal('fetch', fetchSpy);
  vi.stubGlobal('XMLHttpRequest', class {
    open = xhrOpenSpy;
    send = vi.fn();
  });
  vi.stubGlobal('WebSocket', webSocketSpy);
  vi.stubGlobal('EventSource', eventSourceSpy);
  Object.defineProperty(window.navigator, 'sendBeacon', {
    configurable: true,
    value: sendBeaconSpy,
  });
  Object.defineProperty(window, 'indexedDB', {
    configurable: true,
    value: { open: indexedDbOpenSpy },
  });

  return {
    fetchSpy,
    xhrOpenSpy,
    webSocketSpy,
    eventSourceSpy,
    sendBeaconSpy,
    localStorageSetSpy,
    sessionStorageSetSpy,
    indexedDbOpenSpy,
  };
}

function resetSideEffectMocks(mocks: ReturnType<typeof setupSideEffectMocks>) {
  mocks.fetchSpy.mockClear();
  mocks.xhrOpenSpy.mockClear();
  mocks.webSocketSpy.mockClear();
  mocks.eventSourceSpy.mockClear();
  mocks.sendBeaconSpy.mockClear();
  mocks.localStorageSetSpy.mockClear();
  mocks.sessionStorageSetSpy.mockClear();
  mocks.indexedDbOpenSpy.mockClear();
}

function expectNoSideEffects(mocks: ReturnType<typeof setupSideEffectMocks>) {
  expect(mocks.fetchSpy).not.toHaveBeenCalled();
  expect(mocks.xhrOpenSpy).not.toHaveBeenCalled();
  expect(mocks.webSocketSpy).not.toHaveBeenCalled();
  expect(mocks.eventSourceSpy).not.toHaveBeenCalled();
  expect(mocks.sendBeaconSpy).not.toHaveBeenCalled();
  expect(mocks.localStorageSetSpy).not.toHaveBeenCalled();
  expect(mocks.sessionStorageSetSpy).not.toHaveBeenCalled();
  expect(mocks.indexedDbOpenSpy).not.toHaveBeenCalled();
}

describe('R1AssessmentLabApp', () => {
  it('renders the exact five labelled selects, defaults, options, and persistent disclosures', () => {
    render(<R1AssessmentLabApp />);

    const selects = screen.getAllByRole('combobox');
    expect(selects).toHaveLength(5);
    expect(selects.map((select) => select.getAttribute('id'))).toEqual([
      'r1-fixture-select',
      'r1-lens-kind-select',
      'r1-lens-value-select',
      'r1-carrier-mode-select',
      'r1-strategy-select',
    ]);

    const fixture = getSelect('Fixture');
    const lensKind = getSelect('Lens kind');
    const lensValue = getSelect('Lens value');
    const carrierMode = getSelect('Carrier mode');
    const strategy = getSelect('Strategy');

    expect(fixture.value).toBe('compact_sufficient_case');
    expect(lensKind.value).toBe('role');
    expect(lensValue.value).toBe('expedition-lead');
    expect(carrierMode.value).toBe('no_carrier');
    expect(strategy.value).toBe('baseline_local_strategy');

    expect(optionLabels(fixture)).toEqual([
      'compact_sufficient_case',
      'incomplete_evidence_case',
      'contradictory_allocation_case',
      'fake_flexibility_case',
      'remote_materials_carrier_case',
    ]);
    expect(optionLabels(lensKind)).toEqual(['role', 'question']);
    expect(optionLabels(lensValue)).toEqual(['expedition-lead', 'logistics-reviewer']);
    expect(optionLabels(carrierMode)).toEqual(['no_carrier', 'carrier_available', 'compare_both']);
    expect(optionLabels(strategy)).toEqual(['baseline_local_strategy', 'remote_logistics_strategy']);

    expect(screen.getByText('R1 Assessment Laboratory')).toBeTruthy();
    expect(screen.getByText('DEV only — reconstruction shell')).toBeTruthy();
    expect(screen.getByText('R1 Lab — DEV-only fixture-backed reconstruction.')).toBeTruthy();
    expect(screen.getByText('R1 Lab — historic evaluator recovery is not claimed.')).toBeTruthy();
    expect(screen.getByText('R1 Lab — no production scoring or live system advice.')).toBeTruthy();
    expect(screen.getByText('R1 Lab — Lens context only: changing it does not alter fixture outcomes, requirement outcomes, conditions, assessment state, or ordering in Stage 3B.')).toBeTruthy();
    expect(screen.getByText('R1 Lab — Lens labels are local presentation context, not rebuilt role or question semantics.')).toBeTruthy();
    expect(screen.getByText('Template: r1_assessment_programme / core_assessment_template / r1-contract-v1 (fixed for Stage 3B)')).toBeTruthy();
    expect(screen.getByText('Strategy is explicit local DEV-lab context only. It provides no selection guidance, comparison, or automatic choice.')).toBeTruthy();

    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.queryByRole('radio')).toBeNull();
    expect(document.querySelector('textarea')).toBeNull();
  });

  it('keeps role and question modes exclusive and resets Lens value to the mode default', () => {
    render(<R1AssessmentLabApp />);

    const lensKind = getSelect('Lens kind');
    const lensValue = getSelect('Lens value');

    fireEvent.change(lensKind, { target: { value: 'question' } });
    expect(lensKind.value).toBe('question');
    expect(lensValue.value).toBe('baseline-assessment');
    expect(optionLabels(lensValue)).toEqual(['baseline-assessment', 'carrier-sensitivity-check']);

    fireEvent.change(lensValue, { target: { value: 'carrier-sensitivity-check' } });
    expect(lensValue.value).toBe('carrier-sensitivity-check');

    fireEvent.change(lensKind, { target: { value: 'role' } });
    expect(lensKind.value).toBe('role');
    expect(lensValue.value).toBe('expedition-lead');
    expect(optionLabels(lensValue)).toEqual(['expedition-lead', 'logistics-reviewer']);
  });

  it('renders the exact assessment state coverage combinations and compare_both ordering', () => {
    const { container } = render(<R1AssessmentLabApp />);

    const fixture = getSelect('Fixture');
    const carrierMode = getSelect('Carrier mode');

    expect(scenarioState('no_carrier')).toContain('supported');

    fireEvent.change(fixture, { target: { value: 'incomplete_evidence_case' } });
    fireEvent.change(carrierMode, { target: { value: 'no_carrier' } });
    expect(scenarioState('no_carrier')).toContain('not_assessable');

    fireEvent.change(fixture, { target: { value: 'contradictory_allocation_case' } });
    expect(scenarioState('no_carrier')).toContain('not_assessable');

    fireEvent.change(fixture, { target: { value: 'fake_flexibility_case' } });
    expect(scenarioState('no_carrier')).toContain('not_supported');

    fireEvent.change(fixture, { target: { value: 'remote_materials_carrier_case' } });
    fireEvent.change(carrierMode, { target: { value: 'no_carrier' } });
    expect(scenarioState('no_carrier')).toContain('conditionally_supported');

    fireEvent.change(carrierMode, { target: { value: 'carrier_available' } });
    expect(scenarioState('carrier_available')).toContain('supported');

    fireEvent.change(carrierMode, { target: { value: 'compare_both' } });
    const scenarioSections = Array.from(container.querySelectorAll('section[data-testid^="scenario-"]'))
      .map((section) => section.getAttribute('data-testid'));
    expect(screen.getByText('Carrier scenario comparison')).toBeTruthy();
    expect(scenarioSections).toEqual(['scenario-no_carrier', 'scenario-carrier_available']);
  });

  it('renders the exact Strategy selector behavior and changes only Plan Fit presentation when strategy changes', () => {
    render(<R1AssessmentLabApp />);

    const fixture = getSelect('Fixture');
    const carrierMode = getSelect('Carrier mode');
    const strategy = getSelect('Strategy');

    fireEvent.change(fixture, { target: { value: 'remote_materials_carrier_case' } });
    fireEvent.change(carrierMode, { target: { value: 'compare_both' } });

    const assessmentNoCarrierBefore = assessmentContent('no_carrier');
    const assessmentCarrierAvailableBefore = assessmentContent('carrier_available');
    const noCarrierReasonsBefore = planFitReasons('no_carrier').textContent ?? '';
    const carrierAvailableReasonsBefore = planFitReasons('carrier_available').textContent ?? '';

    fireEvent.change(strategy, { target: { value: 'remote_logistics_strategy' } });

    expect(assessmentContent('no_carrier')).toBe(assessmentNoCarrierBefore);
    expect(assessmentContent('carrier_available')).toBe(assessmentCarrierAvailableBefore);

    expect(planFitReasons('no_carrier').textContent).not.toBe(noCarrierReasonsBefore);
    expect(planFitReasons('no_carrier').textContent).toContain('dependency:remote_logistics');

    expect(planFitReasons('carrier_available').textContent).toBe(carrierAvailableReasonsBefore);
    expect(planFitReasons('carrier_available').textContent).not.toContain('dependency:remote_logistics');
  });

  it('renders No structured conditions. for condition-free scenarios and shows requirement trace and frozen evidence/provenance', () => {
    render(<R1AssessmentLabApp />);
    const scenario = screen.getByTestId('scenario-no_carrier');
    const scoped = within(scenario);
    const tables = scoped.getAllByRole('table');
    const requirementTraceTable = tables[0];
    const frozenEvidenceTable = tables[1];

    expect(screen.getByText('No structured conditions.')).toBeTruthy();
    expect(scoped.getByText('Requirement trace')).toBeTruthy();
    expect(scoped.getByText('Frozen evidence and provenance')).toBeTruthy();

    const requirementRow = within(requirementTraceTable).getByText('foundation_evidence').closest('tr');
    if (!requirementRow) throw new Error('foundation_evidence row not found');
    const requirementRowScope = within(requirementRow);
    expect(requirementRowScope.getByText('foundation_evidence')).toBeTruthy();
    expect(requirementRowScope.getByText('met')).toBeTruthy();
    expect(requirementRowScope.getByText('compact-foundation')).toBeTruthy();

    const evidenceRow = within(frozenEvidenceTable).getByText('compact-foundation').closest('tr');
    if (!evidenceRow) throw new Error('compact-foundation evidence row not found');
    const evidenceRowScope = within(evidenceRow);
    expect(evidenceRowScope.getByText('compact-foundation')).toBeTruthy();
    expect(evidenceRowScope.getByText('foundation-evidence')).toBeTruthy();
    expect(evidenceRowScope.getByText('known')).toBeTruthy();
    expect(evidenceRowScope.getByText('compact_sufficient_case')).toBeTruthy();
    expect(evidenceRowScope.getByText('v1')).toBeTruthy();
  });

  it('keeps assessment and Plan Fit scenario content unchanged when only lens context changes', () => {
    render(<R1AssessmentLabApp />);

    const fixture = getSelect('Fixture');
    const carrierMode = getSelect('Carrier mode');
    const strategy = getSelect('Strategy');
    const lensKind = getSelect('Lens kind');
    const lensValue = getSelect('Lens value');

    fireEvent.change(fixture, { target: { value: 'remote_materials_carrier_case' } });
    fireEvent.change(carrierMode, { target: { value: 'compare_both' } });
    fireEvent.change(strategy, { target: { value: 'remote_logistics_strategy' } });

    const beforeNoCarrier = screen.getByTestId('scenario-no_carrier').textContent;
    const beforeCarrierAvailable = screen.getByTestId('scenario-carrier_available').textContent;
    const beforeOrder = screen.getAllByTestId(/scenario-(no_carrier|carrier_available)/).map((element) => element.getAttribute('data-testid'));
    expect(screen.getByTestId('selected-lens-context').textContent).toContain('role / expedition-lead');

    fireEvent.change(lensKind, { target: { value: 'question' } });
    fireEvent.change(lensValue, { target: { value: 'carrier-sensitivity-check' } });

    expect(screen.getByTestId('selected-lens-context').textContent).toContain('question / carrier-sensitivity-check');
    expect(screen.getByTestId('scenario-no_carrier').textContent).toBe(beforeNoCarrier);
    expect(screen.getByTestId('scenario-carrier_available').textContent).toBe(beforeCarrierAvailable);
    expect(screen.getAllByTestId(/scenario-(no_carrier|carrier_available)/).map((element) => element.getAttribute('data-testid')))
      .toEqual(beforeOrder);
  });

  it('renders the remote no_carrier Plan Fit reason with all required fields and the required logistics fields', () => {
    render(<R1AssessmentLabApp />);

    fireEvent.change(getSelect('Fixture'), { target: { value: 'remote_materials_carrier_case' } });
    fireEvent.change(getSelect('Carrier mode'), { target: { value: 'compare_both' } });
    fireEvent.change(getSelect('Strategy'), { target: { value: 'remote_logistics_strategy' } });

    const reasonsTable = planFitReasons('no_carrier');
    const scoped = within(reasonsTable);

    expect(scoped.getByText('reasonId')).toBeTruthy();
    expect(scoped.getByText('reasonKind')).toBeTruthy();
    expect(scoped.getByText('summary')).toBeTruthy();
    expect(scoped.getByText('blocking')).toBeTruthy();
    expect(scoped.getByText('relatedRequirementIds')).toBeTruthy();
    expect(scoped.getByText('relatedEvidenceIds')).toBeTruthy();

    const row = scoped.getByText('dependency:remote_logistics').closest('tr');
    if (!row) throw new Error('dependency:remote_logistics reason row not found');
    const rowScope = within(row);
    expect(rowScope.getByText('dependency:remote_logistics')).toBeTruthy();
    expect(rowScope.getByText('logistics_dependency')).toBeTruthy();
    expect(rowScope.getByText('false')).toBeTruthy();
    expect(rowScope.getByText('remote_logistics')).toBeTruthy();

    const evidenceCell = rowScope.getAllByRole('cell')[5].textContent ?? '';
    expect(evidenceCell).not.toBe('[]');

    expect(planFitReasons('carrier_available').textContent).not.toContain('dependency:remote_logistics');
  });

  it('renders the exact remote compare_both Assessment and Plan Fit pairing for remote_logistics_strategy', () => {
    render(<R1AssessmentLabApp />);

    fireEvent.change(getSelect('Fixture'), { target: { value: 'remote_materials_carrier_case' } });
    fireEvent.change(getSelect('Carrier mode'), { target: { value: 'compare_both' } });
    fireEvent.change(getSelect('Strategy'), { target: { value: 'remote_logistics_strategy' } });

    expect(screen.getAllByTestId(/scenario-(no_carrier|carrier_available)/).map((element) => element.getAttribute('data-testid')))
      .toEqual(['scenario-no_carrier', 'scenario-carrier_available']);

    expect(scenarioState('no_carrier')).toContain('conditionally_supported');
    expect(planFitState('no_carrier')).toContain('provisional_plan_fit');
    expect(screen.getByTestId('scenario-no_carrier').textContent).toContain('dependency:remote_logistics');

    expect(scenarioState('carrier_available')).toContain('supported');
    expect(planFitState('carrier_available')).toContain('provisional_plan_fit');
    expect(screen.getByTestId('scenario-carrier_available').textContent).not.toContain('dependency:remote_logistics');
  });

  it('does not perform network or persistence activity after each separate control change', () => {
    const mocks = setupSideEffectMocks();

    render(<R1AssessmentLabApp />);

    resetSideEffectMocks(mocks);
    fireEvent.change(getSelect('Fixture'), { target: { value: 'remote_materials_carrier_case' } });
    expectNoSideEffects(mocks);

    resetSideEffectMocks(mocks);
    fireEvent.change(getSelect('Lens kind'), { target: { value: 'question' } });
    expectNoSideEffects(mocks);

    resetSideEffectMocks(mocks);
    fireEvent.change(getSelect('Lens value'), { target: { value: 'carrier-sensitivity-check' } });
    expectNoSideEffects(mocks);

    resetSideEffectMocks(mocks);
    fireEvent.change(getSelect('Carrier mode'), { target: { value: 'compare_both' } });
    expectNoSideEffects(mocks);

    resetSideEffectMocks(mocks);
    fireEvent.change(getSelect('Strategy'), { target: { value: 'remote_logistics_strategy' } });
    expectNoSideEffects(mocks);
  });

  it('renders no forbidden language in the DOM', () => {
    const { container } = render(<R1AssessmentLabApp />);
    const text = container.textContent?.toLowerCase() ?? '';

    for (const term of ['score', 'rank', 'best', 'recommend', 'preference', 'winner', 'desirability', 'report', 'export', 'download']) {
      expect(text.includes(term)).toBe(false);
    }
  });
});
