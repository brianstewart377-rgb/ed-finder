import type { RuntimeBackend, RuntimeEvent } from '../contracts';

export interface RecoverySignal { add(callback: () => void): unknown; removeCallback(callback: () => void): boolean }
export type RecoverySignals = Readonly<{ lost: RecoverySignal; restored: RecoverySignal }>;

/** Injectable mirror of Babylon's cross-backend context observables.
 * WebGL context loss and WebGPU GPUDevice.lost both reach these signals in Babylon 9.
 */
export class ResourceRecoveryBridge {
  private active = false;
  private readonly lost = () => { if (this.active) this.emit({ type: 'RESOURCE_LOST', detail: `${this.backend} device/context lost` }); };
  private readonly restored = () => {
    if (!this.active) return;
    this.rebuildRetainedState();
    this.emit({ type: 'RESOURCE_RECOVERED', detail: `${this.backend} resources rebuilt from retained CPU state` });
  };
  constructor(private readonly signals: RecoverySignals, private readonly backend: RuntimeBackend, private readonly rebuildRetainedState: () => void, private readonly emit: (event: RuntimeEvent) => void) {}
  attach(): void { if (this.active) return; this.active = true; this.signals.lost.add(this.lost); this.signals.restored.add(this.restored); }
  dispose(): void { if (!this.active) return; this.active = false; this.signals.lost.removeCallback(this.lost); this.signals.restored.removeCallback(this.restored); }
}
