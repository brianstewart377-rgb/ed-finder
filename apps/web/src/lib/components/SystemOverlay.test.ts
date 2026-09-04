import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Id64 } from '$lib/domain/id64';
import SystemOverlay from './SystemOverlay.svelte';

const { mockedPage, mockedGoto } = vi.hoisted(() => ({
  mockedPage: {
    url: new URL('http://localhost/explore?system=42&view=cards#section'),
  },
  mockedGoto: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('$app/state', () => ({ page: mockedPage }));
vi.mock('$app/navigation', () => ({ goto: mockedGoto }));

beforeEach(() => {
  vi.clearAllMocks();
  mockedPage.url = new URL(
    'http://localhost/explore?system=42&view=cards#section',
  );
  document.body.style.overflow = '';
});

afterEach(() => {
  cleanup();
  document.body.style.overflow = '';
});

describe('SystemOverlay', () => {
  it('moves focus into the dialog and contains forward and reverse Tab', async () => {
    render(SystemOverlay, { props: { id64: '42' as Id64 } });

    const dialog = screen.getByRole('dialog', { name: 'System Detail' });
    const close = screen.getByRole('button', { name: 'Close system detail' });
    await waitFor(() => expect(dialog).toHaveFocus());
    expect(document.body.style.overflow).toBe('hidden');

    await fireEvent.keyDown(window, { key: 'Tab' });
    expect(close).toHaveFocus();

    await fireEvent.keyDown(window, { key: 'Tab' });
    expect(close).toHaveFocus();

    await fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
    expect(close).toHaveFocus();
  });

  it('closes on Escape, preserves the host URL, and restores prior focus', async () => {
    const opener = document.createElement('button');
    opener.textContent = 'Open detail';
    document.body.append(opener);
    opener.focus();

    render(SystemOverlay, { props: { id64: '42' as Id64 } });
    await waitFor(() =>
      expect(
        screen.getByRole('dialog', { name: 'System Detail' }),
      ).toHaveFocus(),
    );

    await fireEvent.keyDown(window, { key: 'Escape' });

    expect(mockedGoto).toHaveBeenCalledWith('/explore?view=cards#section', {
      replaceState: true,
      noScroll: true,
    });
    await waitFor(() => expect(opener).toHaveFocus());
    opener.remove();
  });
});
