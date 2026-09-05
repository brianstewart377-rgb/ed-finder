import type {
  SpatialRendererBackend,
  SpatialRuntime,
  SpatialRuntimeStatus,
  SpatialRuntimeStatusListener,
  SpatialViewport,
} from './contracts';

export interface SpatialBackendSession {
  readonly backend: SpatialRendererBackend;
  resize(viewport: SpatialViewport): void;
  render(): void;
  dispose(): void;
}

export interface SpatialBackendCandidates {
  createWebGpu(): Promise<SpatialBackendSession | null>;
  createWebGl2(): SpatialBackendSession | null;
}

const safeDispose = (session: SpatialBackendSession | null): void => {
  try {
    session?.dispose();
  } catch {
    // Disposal must remain best-effort and must never surface during teardown.
  }
};

export function createManagedSpatialRuntime(
  candidates: SpatialBackendCandidates,
  onStatus: SpatialRuntimeStatusListener,
): SpatialRuntime {
  let status: SpatialRuntimeStatus = { state: 'created' };
  let session: SpatialBackendSession | null = null;
  let pendingStart: Promise<SpatialRuntimeStatus> | null = null;
  let pendingViewport: SpatialViewport | null = null;

  const publish = (next: SpatialRuntimeStatus): SpatialRuntimeStatus => {
    status = next;
    onStatus(next);
    return next;
  };

  const fail = (
    failure: 'INITIALIZATION_FAILED' | 'RUNTIME_FAILED',
  ): SpatialRuntimeStatus => {
    safeDispose(session);
    session = null;
    return publish({ state: 'failed', failure });
  };

  // Status can change while an awaited backend initialization is pending.
  const wasDisposed = (): boolean => status.state === 'disposed';

  const start = (): Promise<SpatialRuntimeStatus> => {
    if (status.state === 'disposed' || status.state === 'ready') {
      return Promise.resolve(status);
    }
    if (status.state === 'failed') {
      return Promise.resolve(status);
    }
    if (pendingStart) return pendingStart;

    publish({ state: 'starting' });
    pendingStart = (async () => {
      let candidate: SpatialBackendSession | null = null;

      try {
        candidate = await candidates.createWebGpu();
      } catch {
        // WebGPU initialization failure deterministically selects WebGL2.
      }

      if (wasDisposed()) {
        safeDispose(candidate);
        return status;
      }

      if (!candidate) {
        try {
          candidate = candidates.createWebGl2();
        } catch {
          return fail('INITIALIZATION_FAILED');
        }
      }

      if (wasDisposed()) {
        safeDispose(candidate);
        return status;
      }

      if (!candidate) {
        return publish({ state: 'failed', failure: 'BACKEND_UNAVAILABLE' });
      }

      session = candidate;
      try {
        if (pendingViewport) session.resize(pendingViewport);
        session.render();
      } catch {
        return fail('INITIALIZATION_FAILED');
      }

      return publish({ state: 'ready', backend: session.backend });
    })();

    return pendingStart;
  };

  return {
    getStatus: () => status,
    start,
    resize(viewport) {
      if (status.state === 'disposed' || status.state === 'failed') return;
      pendingViewport = viewport;
      if (!session) return;
      try {
        session.resize(viewport);
        session.render();
      } catch {
        fail('RUNTIME_FAILED');
      }
    },
    dispose() {
      if (status.state === 'disposed') return;
      safeDispose(session);
      session = null;
      publish({ state: 'disposed' });
    },
  };
}
