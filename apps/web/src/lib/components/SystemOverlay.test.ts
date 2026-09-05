import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Id64 } from '$lib/domain/id64';
import { getSystem } from '$lib/api/client';
import { queryClient } from '$lib/api/query';
import SystemOverlayTestHost from './SystemOverlayTestHost.svelte';

const { mockedPage, mockedGoto } = vi.hoisted(() => ({
  mockedPage: {
    url: new URL('http://localhost/explore?system=42&view=cards#section'),
  },
  mockedGoto: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('$app/state', () => ({ page: mockedPage }));
vi.mock('$app/navigation', () => ({ goto: mockedGoto }));
vi.mock('$lib/api/client', async (loadOriginal) => {
  const original = await loadOriginal<typeof import('$lib/api/client')>();
  return { ...original, getSystem: vi.fn() };
});

const mockedGetSystem = vi.mocked(getSystem);

beforeEach(() => {
  vi.clearAllMocks();
  queryClient.clear();
  mockedGetSystem.mockResolvedValue({
    id64: '42' as Id64,
    name: 'Test System',
  });
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
    render(SystemOverlayTestHost, { props: { id64: '42' as Id64 } });

    const dialog = screen.getByRole('dialog', { name: 'System Detail' });
    const close = screen.getByRole('button', { name: 'Close system detail' });
    const finalControl = document.createElement('button');
    finalControl.textContent = 'Last dialog action';
    dialog.append(finalControl);
    await waitFor(() => expect(dialog).toHaveFocus());
    expect(document.body.style.overflow).toBe('hidden');

    await fireEvent.keyDown(window, { key: 'Tab' });
    expect(close).toHaveFocus();

    finalControl.focus();
    await fireEvent.keyDown(window, { key: 'Tab' });
    expect(close).toHaveFocus();

    close.focus();
    await fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
    expect(finalControl).toHaveFocus();
  });

  it('closes on Escape, preserves the host URL, and restores prior focus', async () => {
    const opener = document.createElement('button');
    opener.textContent = 'Open detail';
    document.body.append(opener);
    opener.focus();
    const focusOpener = vi.spyOn(opener, 'focus');

    const { unmount } = render(SystemOverlayTestHost, {
      props: { id64: '42' as Id64 },
    });
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
    expect(focusOpener).toHaveBeenCalledOnce();
    expect(focusOpener).toHaveBeenCalledWith({ preventScroll: true });

    unmount();
    expect(focusOpener).toHaveBeenCalledOnce();
    opener.remove();
  });

  it('restores body scroll and prior focus when host navigation unmounts it', async () => {
    document.body.style.overflow = 'scroll';
    const opener = document.createElement('button');
    opener.textContent = 'Navigate to detail';
    document.body.append(opener);
    opener.focus();

    const { unmount } = render(SystemOverlayTestHost, {
      props: { id64: '42' as Id64 },
    });
    await waitFor(() =>
      expect(
        screen.getByRole('dialog', { name: 'System Detail' }),
      ).toHaveFocus(),
    );
    expect(document.body.style.overflow).toBe('hidden');

    unmount();

    expect(document.body.style.overflow).toBe('scroll');
    expect(opener).toHaveFocus();
    opener.remove();
  });
});
