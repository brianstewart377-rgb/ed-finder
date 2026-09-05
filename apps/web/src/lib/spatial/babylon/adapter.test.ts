import { describe, expect, it, vi } from 'vitest';

import type { SpatialBackendSession } from '../lifecycle';
import {
  createBabylonSpatialRuntime,
  type BabylonRuntimeDependencies,
} from './adapter';

const createSession = (backend: 'WEBGPU' | 'WEBGL2') =>
  ({
    backend,
    resize: vi.fn(),
    render: vi.fn(),
    dispose: vi.fn(),
  }) satisfies SpatialBackendSession;

describe('Babylon spatial adapter boundary', () => {
  it('uses a fresh canvas for WebGL2 after WebGPU initialization fails', async () => {
    const original = document.createElement('canvas');
    const replacement = document.createElement('canvas');
    const webGl2 = createSession('WEBGL2');
    const dependencies: BabylonRuntimeDependencies = {
      createWebGpu: vi
        .fn()
        .mockRejectedValue(new Error('initialization failed')),
      createWebGl2: vi.fn().mockReturnValue(webGl2),
      replaceCanvas: vi.fn().mockReturnValue(replacement),
    };
    const runtime = createBabylonSpatialRuntime(
      original,
      vi.fn(),
      dependencies,
    );

    await expect(runtime.start()).resolves.toEqual({
      state: 'ready',
      backend: 'WEBGL2',
    });

    expect(dependencies.replaceCanvas).toHaveBeenCalledWith(original);
    expect(dependencies.createWebGl2).toHaveBeenCalledWith(replacement);
  });

  it('keeps the original canvas when WebGPU is simply unsupported', async () => {
    const original = document.createElement('canvas');
    const webGl2 = createSession('WEBGL2');
    const dependencies: BabylonRuntimeDependencies = {
      createWebGpu: vi.fn().mockResolvedValue(null),
      createWebGl2: vi.fn().mockReturnValue(webGl2),
      replaceCanvas: vi.fn(),
    };
    const runtime = createBabylonSpatialRuntime(
      original,
      vi.fn(),
      dependencies,
    );

    await runtime.start();

    expect(dependencies.replaceCanvas).not.toHaveBeenCalled();
    expect(dependencies.createWebGl2).toHaveBeenCalledWith(original);
  });
});
