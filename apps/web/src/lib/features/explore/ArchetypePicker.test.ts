import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import axe from 'axe-core';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ArchetypePicker from './ArchetypePicker.svelte';
import {
  ANY_ARCHETYPE_DESCRIPTION,
  ARCHETYPES,
  type ArchetypeKey,
} from './archetypes';

afterEach(cleanup);

function picker(archetype: 'any' | ArchetypeKey = 'any') {
  const onArchetypeChange = vi.fn();
  const onMinimumTierChange = vi.fn();
  const result = render(ArchetypePicker, {
    archetype,
    minimumTier: archetype === 'any' ? null : 'B',
    onArchetypeChange,
    onMinimumTierChange,
  });
  return { ...result, onArchetypeChange, onMinimumTierChange };
}

describe('native archetype picker', () => {
  it('names the group and all nine radios only by their short labels', () => {
    picker();
    expect(
      screen.getByRole('group', { name: 'Colony archetype' }),
    ).toHaveProperty('tagName', 'FIELDSET');
    const choices = [
      { label: 'Any', description: ANY_ARCHETYPE_DESCRIPTION },
      ...ARCHETYPES,
    ];
    expect(screen.getAllByRole('radio')).toHaveLength(9);
    for (const choice of choices) {
      const radio = screen.getByRole('radio', {
        name: choice.label,
      });
      expect(radio).toHaveAccessibleDescription(choice.description);
      const description = document.getElementById(
        radio.getAttribute('aria-describedby')!,
      );
      expect(description).toHaveTextContent(choice.description);
      expect(description?.closest('label')).toBeNull();
      expect(screen.getAllByText(choice.description)).toHaveLength(1);
    }
    expect(screen.getByRole('radio', { name: 'Any' })).toBeChecked();
    expect(screen.queryByLabelText('Minimum tier')).not.toBeInTheDocument();
  });

  it('uses one native radio group and leaves its keyboard progression to the platform', async () => {
    const { onArchetypeChange, rerender } = picker();
    const radios = screen.getAllByRole('radio') as HTMLInputElement[];
    expect(new Set(radios.map((radio) => radio.name)).size).toBe(1);
    expect(radios.every((radio) => radio.type === 'radio')).toBe(true);
    expect(radios.every((radio) => !radio.hasAttribute('tabindex'))).toBe(true);
    const first = radios[0];
    first.focus();
    expect(await fireEvent.keyDown(first, { key: 'ArrowRight' })).toBe(true);
    // jsdom does not implement the browser's radio arrow-key default action.
    // Deliver its native change result and verify the controlled commit.
    await fireEvent.click(radios[1]);
    expect(onArchetypeChange).toHaveBeenCalledExactlyOnceWith('paradise');
    await rerender({ archetype: 'paradise', minimumTier: 'B' });
    expect(radios[1]).toBeChecked();
    expect(first).not.toBeChecked();
  });

  it('shows only B, A and S minimum tiers for a selected archetype', async () => {
    const { onMinimumTierChange } = picker('manufacturing_hub');
    const select = screen.getByRole('combobox', { name: 'Minimum tier' });
    expect(select).toHaveValue('B');
    expect(
      screen.getAllByRole('option').map((option) => option.textContent),
    ).toEqual(['Tier B', 'Tier A', 'Tier S']);
    await fireEvent.change(select, { target: { value: 'A' } });
    expect(onMinimumTierChange).toHaveBeenCalledExactlyOnceWith('A');
  });

  it('keeps native controls and descriptions accessible', async () => {
    const { container } = picker('flexible');
    expect(
      (
        await axe.run(container, {
          rules: { 'color-contrast': { enabled: false } },
        })
      ).violations,
    ).toEqual([]);
  });
});
