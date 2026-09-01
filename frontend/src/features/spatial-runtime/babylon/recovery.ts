import type { RuntimeBackend, RuntimeEvent } from '../contracts';

export interface RecoverySignal { add(callback: () => void): unknown; removeCallback(callback: () => void): boolean }
export type RecoverySignals = Readonly<{ lost: RecoverySignal; restored: RecoverySignal }>;

/** Injectable bridge for Babylon's engine loss/restoration observables.
 * WebGL supplies both signals; WebGPU device-loss coverage is capability- and
 * engine-dependent, with the explicit rebuild command retained as fallback.
 */
export class ResourceRecoveryBridge {
  private active = false;
  private lostAt: number | null = null;
  private readonly lost = () => { if (this.active) { this.lostAt = performance.now(); this.emit({ type: 'RESOURCE_LOST', detail: `${this.backend} device/context lost` }); } };
  private readonly restored = () => {
    if (!this.active) return;
    this.rebuildRetainedState();
    const latencyMs = this.lostAt === null ? 0 : performance.now() - this.lostAt;
    this.emit({ type: 'RECOVERY_RESULT', outcome: 'RECOVERED', detail: `${this.backend} resources rebuilt from retained CPU state`, latencyMs });
  };
  constructor(private readonly signals: RecoverySignals, private readonly backend: RuntimeBackend, private readonly rebuildRetainedState: () => void, private readonly emit: (event: RuntimeEvent) => void) {}
  attach(): void { if (this.active) return; this.active = true; this.signals.lost.add(this.lost); this.signals.restored.add(this.restored); }
  dispose(): void { if (!this.active) return; this.active = false; this.signals.lost.removeCallback(this.lost); this.signals.restored.removeCallback(this.restored); }
}
