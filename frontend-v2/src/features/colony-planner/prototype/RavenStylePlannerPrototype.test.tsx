import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RavenStylePlannerPrototype } from './RavenStylePlannerPrototype';

describe('RavenStylePlannerPrototype', () => {
  it('renders a continuous whole-system planner canvas', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.getByTestId('raven-style-continuous-canvas')).toBeTruthy();
    expect(screen.getByText('System tree')).toBeTruthy();
    expect(screen.getByText('Orbital lane')).toBeTruthy();
    expect(screen.getByText('Ground lane')).toBeTruthy();
    expect(screen.queryByText('Attached Structures')).toBeNull();
    expect(screen.queryByText('Facilities and economy')).toBeNull();
  });

  it('renders the reference body with 4 orbital and 5 ground slots', () => {
    render(<RavenStylePlannerPrototype />);

    const row = screen.getByTestId('prototype-body-row-a-3-a');
    expect(within(row).getAllByTestId('a-3-a-orbital-slot')).toHaveLength(4);
    expect(within(row).getAllByTestId('a-3-a-ground-slot')).toHaveLength(5);
  });

  it('renders planned structures directly inside their body slot lanes', () => {
    render(<RavenStylePlannerPrototype />);

    const row = screen.getByTestId('prototype-body-row-a-3-a');
    expect(within(row).getByText('Dodec')).toBeTruthy();
    expect(within(row).getByText('Silenius Mining')).toBeTruthy();
    expect(within(row).getByText('Refinery Hub')).toBeTruthy();
    expect(within(row).queryByTestId('attached-structure')).toBeNull();
  });

  it('renders projected ghost structures and can hide them with the projection toggle', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.getAllByTestId('projected-ghost-structure').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Ghost Industrial Inst.').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Ghost Military Outpost').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /hide projected build/i }));

    expect(screen.queryByTestId('projected-ghost-structure')).toBeNull();
    expect(screen.queryByText('Ghost Industrial Inst.')).toBeNull();
  });

  it('renders per-structure economy bars and the Raven-style stat panel', () => {
    render(<RavenStylePlannerPrototype />);

    const selectedBodyRow = screen.getByTestId('prototype-body-row-a-3-a');
    const structureSlots = within(selectedBodyRow).getAllByTestId('structure-slot-pill');

    expect(structureSlots).toHaveLength(6);
    expect(within(selectedBodyRow).getAllByTestId('structure-economy-micro-bar')).toHaveLength(6);
    expect(screen.getByTestId('raven-style-stat-panel')).toBeTruthy();
    expect(screen.getByText('Planning Telemetry')).toBeTruthy();
    expect(screen.getByText('Economy mix and strength')).toBeTruthy();
  });

  it('keeps full structure names and combined economy values available from slot titles', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.getByTitle(/Silenius Mining Hub.*Status: Planned.*Extraction 50% share \/ \+720% bonus.*Refinery 38% share \/ \+550% bonus/)).toBeTruthy();
    expect(screen.getByTitle(/Kawajiri Industrial Installation.*Status: Projected.*Refinery 58% share \/ \+390% bonus.*Industrial 42% share \/ \+280% bonus/)).toBeTruthy();
  });

  it('shows expanded structure rows only in Detailed Rows mode', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.queryByTestId('expanded-structure-list')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /detailed rows/i }));

    expect(screen.getAllByTestId('expanded-structure-list').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('expanded-structure-row').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Silenius Mining Hub').length).toBeGreaterThan(0);
  });

  it('renders structure economy micro-bars with large bonus values', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.getAllByTestId('structure-economy-micro-bar').length).toBeGreaterThan(10);
    expect(screen.getAllByText(/\+720%/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\+550%/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Ext 50%/).length).toBeGreaterThan(0);
  });

  it('renders selected structure economy as combined body and structure context', () => {
    render(<RavenStylePlannerPrototype />);

    const detailRows = screen.getAllByTestId('structure-economy-detail');
    expect(detailRows.length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Silenius Mining Hub/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Extraction 50% share \| \+720%/)).toBeTruthy();
    expect(screen.getByText(/Refinery 38% share \| \+550%/)).toBeTruthy();
    expect(screen.getByText(/\+240% structure \/ \+480% body/)).toBeTruthy();
  });

  it('renders economy share and bonus magnitude as distinct semantics', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.getByText('Bar = share. Number = bonus strength.')).toBeTruthy();
    expect(screen.getByText(/32% \| \+720%/)).toBeTruthy();

    const structureBar = screen.getAllByTestId('structure-economy-micro-bar')[0];
    expect(structureBar.getAttribute('title')).toContain('Share = relative economy mix');
    expect(structureBar.getAttribute('title')).toContain('Bonus = combined structure + body strength');
  });

  it('uses the widened telemetry panel layout', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.getByTestId('prototype-planner-layout').getAttribute('data-layout')).toBe('wide-telemetry');
    expect(screen.getByTestId('raven-style-stat-panel').getAttribute('data-layout')).toBe('wide-telemetry');
    expect(screen.getByTestId('prototype-planner-layout').className).toContain('32rem');
  });

  it('renders zero-centered system stat bars', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.getAllByTestId('zero-centered-stat-bar')).toHaveLength(8);
    expect(screen.getByTestId('stat-security-zero-axis')).toBeTruthy();
  });

  it('extends negative stat values left from the zero axis', () => {
    render(<RavenStylePlannerPrototype />);

    const negative = screen.getByTestId('stat-security-negative') as HTMLElement;
    const positive = screen.getByTestId('stat-security-positive') as HTMLElement;

    expect(negative.style.width).not.toBe('0%');
    expect(positive.style.width).toBe('0%');
    expect(negative.dataset.tone).toBe('negative-red');
    expect(negative.style.backgroundColor).toBe('rgb(248, 113, 113)');
  });

  it('extends positive stat values right from the zero axis', () => {
    render(<RavenStylePlannerPrototype />);

    const negative = screen.getByTestId('stat-tech-level-negative') as HTMLElement;
    const positive = screen.getByTestId('stat-tech-level-positive') as HTMLElement;

    expect(negative.style.width).toBe('0%');
    expect(positive.style.width).not.toBe('0%');
    expect(positive.dataset.tone).toBe('positive-green');
    expect(positive.style.backgroundColor).toBe('rgb(74, 222, 128)');
  });

  it('renders neutral stat values without positive or negative fill', () => {
    render(<RavenStylePlannerPrototype />);

    const neutralRow = screen.getAllByTestId('zero-centered-stat-bar').find((row) => row.getAttribute('data-stat-id') === 'logistics-debt');
    expect(neutralRow?.getAttribute('data-direction')).toBe('neutral');
    expect(screen.getByTestId('stat-logistics-debt-negative').style.width).toBe('0%');
    expect(screen.getByTestId('stat-logistics-debt-positive').style.width).toBe('0%');
  });

  it('keeps the prototype warning to one concise label', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.getAllByText('Prototype - visual direction, not live planner data')).toHaveLength(1);
    expect(screen.queryByText('Static mock data only')).toBeNull();
    expect(screen.queryByText('Not wired to live planner data')).toBeNull();
  });

  it('does not render the current live planner card/grid components', () => {
    render(<RavenStylePlannerPrototype />);

    expect(screen.queryByTestId('whole-system-colony-planner')).toBeNull();
    expect(screen.queryByTestId('workspace-planner-content')).toBeNull();
    expect(screen.queryByTestId('body-slot-planner')).toBeNull();
    expect(screen.queryByTestId('body-slot-graph')).toBeNull();
  });
});
