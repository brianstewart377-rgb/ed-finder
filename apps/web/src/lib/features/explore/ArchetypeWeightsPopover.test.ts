import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import axe from 'axe-core';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ArchetypeWeightsPopover from './ArchetypeWeightsPopover.svelte';
import { ARCHETYPE_KEYS, archetypeLabel } from './archetypes';
import { DEFAULT_ARCHETYPE_WEIGHTS } from './ranking-state';

afterEach(cleanup);

const singleParadise = Object.fromEntries(
  ARCHETYPE_KEYS.map((key) => [key, key === 'paradise' ? 100 : 0]),
);

function popover(weights: Readonly<Record<string, number>> = {}) {
  const onapply = vi.fn();
  const onopen = vi.fn();
  const result = render(ArchetypeWeightsPopover, {
    weights,
    profiles: [
      {
        id: 'paradise',
        label: 'Paradise World',
        description: 'Paradise only',
        weights: singleParadise,
      },
    ],
    onapply,
    onopen,
  });
  return { ...result, onapply, onopen };
}

async function open() {
  const trigger = screen.getByRole('button', {
    name: /^(Weights|Custom weights)$/,
  });
  await fireEvent.click(trigger);
  return trigger;
}

describe('custom archetype weights popover', () => {
  it('opens a named nonmodal dialog with eight labelled percentage sliders', async () => {
    const { onopen } = popover();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    const trigger = await open();
    const dialog = screen.getByRole('dialog', {
      name: 'Custom archetype weights',
    });
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(trigger).toHaveAttribute('aria-controls', dialog.id);
    expect(dialog).toHaveAttribute('aria-modal', 'false');
    expect(dialog).toHaveFocus();
    expect(onopen).toHaveBeenCalledOnce();
    expect(screen.getAllByRole('slider')).toHaveLength(8);
    for (const key of ARCHETYPE_KEYS) {
      const slider = screen.getByRole('slider', { name: archetypeLabel(key)! });
      expect(slider).toHaveAttribute('min', '0');
      expect(slider).toHaveAttribute('max', '100');
      expect(slider).toHaveAttribute('step', '5');
      expect(slider).toHaveValue('100');
      expect(slider).toHaveAttribute('aria-valuetext', '100%');
      expect(slider.parentElement?.querySelector('output')).toHaveTextContent(
        '100%',
      );
    }
  });

  it('keeps slider edits local until Apply commits the full vector once', async () => {
    const { onapply } = popover();
    const trigger = await open();
    const slider = screen.getByRole('slider', { name: 'Mining Hub' });
    for (const value of ['95', '80', '35'])
      await fireEvent.input(slider, { target: { value } });
    expect(onapply).not.toHaveBeenCalled();
    expect(slider.parentElement?.querySelector('output')).toHaveTextContent(
      '35%',
    );
    await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    expect(onapply).toHaveBeenCalledExactlyOnceWith({
      ...DEFAULT_ARCHETYPE_WEIGHTS,
      mining_hub: 35,
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it.each(['Escape', 'Close weights', 'Cancel', 'outside', 'trigger'])(
    'closes with %s, discards drafts and returns focus',
    async (method) => {
      const { onapply } = popover(singleParadise);
      const trigger = await open();
      await fireEvent.input(
        screen.getByRole('slider', { name: 'Paradise World' }),
        { target: { value: '40' } },
      );
      if (method === 'Escape')
        await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
      else if (method === 'outside') await fireEvent.click(document.body);
      else if (method === 'trigger') await fireEvent.click(trigger);
      else await fireEvent.click(screen.getByRole('button', { name: method }));
      expect(onapply).not.toHaveBeenCalled();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(trigger).toHaveFocus();
      expect(trigger).toHaveAttribute('aria-expanded', 'false');
      await open();
      expect(
        screen.getByRole('slider', { name: 'Paradise World' }),
      ).toHaveValue('100');
      expect(screen.getByRole('slider', { name: 'Mining Hub' })).toHaveValue(
        '0',
      );
    },
  );

  it('disables Apply with an explanation for all zero and resets only the draft', async () => {
    const { onapply } = popover(singleParadise);
    await open();
    await fireEvent.input(
      screen.getByRole('slider', { name: 'Paradise World' }),
      { target: { value: '0' } },
    );
    const apply = screen.getByRole('button', { name: 'Apply' });
    expect(apply).toBeDisabled();
    expect(apply).toHaveAccessibleDescription(
      'Set at least one weight above 0% to apply.',
    );
    await fireEvent.click(apply);
    expect(onapply).not.toHaveBeenCalled();
    await fireEvent.click(
      screen.getByRole('button', { name: 'Reset to default' }),
    );
    expect(
      screen
        .getAllByRole('slider')
        .every((slider) => (slider as HTMLInputElement).value === '100'),
    ).toBe(true);
    expect(apply).toBeEnabled();
    expect(onapply).not.toHaveBeenCalled();
    await fireEvent.click(apply);
    expect(onapply).toHaveBeenCalledExactlyOnceWith(DEFAULT_ARCHETYPE_WEIGHTS);
  });

  it('uses API presets as drafts and retains manual editing when presets fail', async () => {
    const { onapply, rerender } = popover();
    await open();
    await fireEvent.click(
      screen.getByRole('button', { name: 'Paradise World' }),
    );
    expect(screen.getByRole('slider', { name: 'Mining Hub' })).toHaveValue('0');
    expect(onapply).not.toHaveBeenCalled();
    await rerender({ profiles: [], profilesLoading: true });
    expect(screen.getByText('Loading presets…')).toHaveAttribute(
      'role',
      'status',
    );
    await rerender({ profilesLoading: false, profilesError: true });
    expect(screen.getByText(/Presets are unavailable/)).toHaveAttribute(
      'role',
      'status',
    );
    expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled();
    await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
    expect(onapply).toHaveBeenCalledExactlyOnceWith(singleParadise);
  });

  it('hydrates committed URL weights on each opening without resetting an active draft', async () => {
    const { rerender } = popover(singleParadise);
    expect(
      screen.getByRole('button', { name: 'Custom weights' }),
    ).toBeInTheDocument();
    await open();
    await fireEvent.input(
      screen.getByRole('slider', { name: 'Paradise World' }),
      { target: { value: '40' } },
    );
    await rerender({ weights: DEFAULT_ARCHETYPE_WEIGHTS });
    expect(screen.getByRole('slider', { name: 'Paradise World' })).toHaveValue(
      '40',
    );
    await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await open();
    expect(screen.getByRole('slider', { name: 'Paradise World' })).toHaveValue(
      '100',
    );
    expect(screen.getByRole('slider', { name: 'Mining Hub' })).toHaveValue(
      '100',
    );
    await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await rerender({ weights: {} });
    expect(screen.getByRole('button', { name: 'Weights' })).toBeInTheDocument();
  });

  it('passes axe with the dialog open', async () => {
    const { container } = popover();
    await open();
    expect(
      (
        await axe.run(container, {
          rules: { 'color-contrast': { enabled: false } },
        })
      ).violations,
    ).toEqual([]);
  });
});
