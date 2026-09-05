import { describe, expect, it, vi } from 'vitest';

import type { SpatialRendererBackend, SpatialViewport } from './contracts';
import {
  createManagedSpatialRuntime,
  type SpatialBackendSession,
} from './lifecycle';

const viewport: SpatialViewport = { width: 640, height: 360, dpr: 2 };

const createSession = (backend: SpatialRendererBackend) => ({
  backend,
  resize: vi.fn(),
  render: vi.fn(),
  dispose: vi.fn(),
});

describe('renderer-neutral spatial runtime lifecycle', () => {
  it('prefers WebGPU, applies a pending resize, and disposes once', async () => {
    const webGpu = createSession('WEBGPU');
    const createWebGl2 = vi.fn();
    const statuses = vi.fn();
    const runtime = createManagedSpatialRuntime(
      {
        createWebGpu: vi.fn().mockResolvedValue(webGpu),
        createWebGl2,
      },
      statuses,
    );

    runtime.resize(viewport);
    await expect(runtime.start()).resolves.toEqual({
      state: 'ready',
      backend: 'WEBGPU',
    });
    await runtime.start();

    expect(createWebGl2).not.toHaveBeenCalled();
    expect(webGpu.resize).toHaveBeenCalledOnce();
    expect(webGpu.resize).toHaveBeenCalledWith(viewport);
    expect(webGpu.render).toHaveBeenCalledOnce();
    expect(statuses.mock.calls.map(([status]) => status.state)).toEqual([
      'starting',
      'ready',
    ]);

    runtime.dispose();
    runtime.dispose();
    expect(webGpu.dispose).toHaveBeenCalledOnce();
    expect(runtime.getStatus()).toEqual({ state: 'disposed' });
  });

  it('falls back to WebGL2 after a WebGPU initialization failure', async () => {
    const webGl2 = createSession('WEBGL2');
    const runtime = createManagedSpatialRuntime(
      {
        createWebGpu: vi.fn().mockRejectedValue(new Error('device lost')),
        createWebGl2: vi.fn().mockReturnValue(webGl2),
      },
      vi.fn(),
    );

    await expect(runtime.start()).resolves.toEqual({
      state: 'ready',
      backend: 'WEBGL2',
    });
    expect(webGl2.render).toHaveBeenCalledOnce();
  });

  it('reports only a bounded failure when no supported backend exists', async () => {
    const statuses = vi.fn();
    const runtime = createManagedSpatialRuntime(
      {
        createWebGpu: vi.fn().mockResolvedValue(null),
        createWebGl2: vi.fn().mockReturnValue(null),
      },
      statuses,
    );

    await expect(runtime.start()).resolves.toEqual({
      state: 'failed',
      failure: 'BACKEND_UNAVAILABLE',
    });
    expect(statuses).toHaveBeenLastCalledWith({
      state: 'failed',
      failure: 'BACKEND_UNAVAILABLE',
    });
  });

  it('disposes a backend that resolves after the runtime was disposed', async () => {
    let resolveWebGpu!: (session: SpatialBackendSession) => void;
    const lateSession = createSession('WEBGPU');
    const createWebGpu = vi.fn(
      () =>
        new Promise<SpatialBackendSession>((resolve) => {
          resolveWebGpu = resolve;
        }),
    );
    const statuses = vi.fn();
    const runtime = createManagedSpatialRuntime(
      { createWebGpu, createWebGl2: vi.fn() },
      statuses,
    );

    const start = runtime.start();
    runtime.dispose();
    resolveWebGpu(lateSession);

    await expect(start).resolves.toEqual({ state: 'disposed' });
    expect(lateSession.dispose).toHaveBeenCalledOnce();
    expect(lateSession.render).not.toHaveBeenCalled();
    expect(statuses).not.toHaveBeenCalledWith(
      expect.objectContaining({ state: 'ready' }),
    );
  });

  it('contains resize failures and releases the active backend', async () => {
    const webGl2 = createSession('WEBGL2');
    webGl2.resize.mockImplementation(() => {
      throw new Error('context lost');
    });
    const runtime = createManagedSpatialRuntime(
      {
        createWebGpu: vi.fn().mockResolvedValue(null),
        createWebGl2: vi.fn().mockReturnValue(webGl2),
      },
      vi.fn(),
    );

    await runtime.start();
    runtime.resize(viewport);

    expect(runtime.getStatus()).toEqual({
      state: 'failed',
      failure: 'RUNTIME_FAILED',
    });
    expect(webGl2.dispose).toHaveBeenCalledOnce();
  });
});
