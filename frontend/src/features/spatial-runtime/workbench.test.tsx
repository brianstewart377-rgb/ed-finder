import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SpatialWorkbench } from '../../../spatial-workbench/workbench';

const runtimeHarness = vi.hoisted(() => {
  let resolveInitialization: (backend: 'WEBGPU' | 'WEBGL2') => void = () => undefined;
  return {
    dispatch: vi.fn(),
    initialize: vi.fn(() => new Promise<'WEBGPU' | 'WEBGL2'>((resolve) => { resolveInitialization = resolve; })),
    resolve: (backend: 'WEBGPU' | 'WEBGL2') => resolveInitialization(backend),
  };
});

vi.mock('./babylon/BabylonMapRuntime', () => ({
  BabylonMapRuntime: class {
    initialize = runtimeHarness.initialize;
    dispatch = runtimeHarness.dispatch;
    dispose = vi.fn();
    snapshot = vi.fn(() => ({ camera: null, selection: [] }));
    cancelFlyTo = vi.fn();
    suspend = vi.fn();
    resume = vi.fn();
    pick = vi.fn();
  },
}));

class ResizeObserverStub {
  observe() {}
  disconnect() {}
}

describe('SpatialWorkbench initialization', () => {
  beforeEach(() => {
    runtimeHarness.dispatch.mockClear();
    runtimeHarness.initialize.mockClear();
    vi.stubGlobal('ResizeObserver', ResizeObserverStub);
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
  });

  it('keeps a fixture selection made while engine initialization is pending', async () => {
    render(<SpatialWorkbench />);

    fireEvent.change(screen.getByLabelText('Fixture'), { target: { value: '40000' } });
    runtimeHarness.resolve('WEBGL2');

    await waitFor(() => expect(screen.getByTestId('backend').textContent).toBe('Backend: WEBGL2'));
    expect(screen.getByTestId('workbench-status').textContent).toBe('WEBGL2 renderer ready with 40,000 fixture stars.');

    const sceneLoads = runtimeHarness.dispatch.mock.calls
      .map(([command]) => command)
      .filter((command) => command.type === 'LOAD_SCENE');
    expect(sceneLoads.at(-1).scene.contributions[0].layers[0].targetCount).toBe(40_000);
  });
});
