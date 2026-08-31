import { describe, expect, it } from 'vitest';
import type { RuntimeBackend, RuntimeEvent } from '../contracts';
import { ResourceRecoveryBridge, type RecoverySignal } from './recovery';

class Signal implements RecoverySignal {
  callbacks = new Set<() => void>(); add(callback: () => void) { this.callbacks.add(callback); }
  removeCallback(callback: () => void) { return this.callbacks.delete(callback); }
  fire() { for (const callback of this.callbacks) callback(); }
}

describe.each<RuntimeBackend>(['WEBGL2', 'WEBGPU'])('deterministic %s recovery harness', (backend) => {
  it('retains CPU state across loss/recovery and cleans up listeners', () => {
    const lost = new Signal(); const restored = new Signal(); const events: RuntimeEvent[] = [];
    const retained = { revision: 4, target: { kind: 'system' as const, systemId64: '10477373803' } }; let rebuilt: typeof retained | null = null;
    const bridge = new ResourceRecoveryBridge({ lost, restored }, backend, () => { rebuilt = retained; }, (event) => events.push(event));
    bridge.attach(); lost.fire(); restored.fire();
    expect(events.map((event) => event.type)).toEqual(['RESOURCE_LOST', 'RESOURCE_RECOVERED']);
    expect(rebuilt).toBe(retained); expect(lost.callbacks.size).toBe(1); expect(restored.callbacks.size).toBe(1);
    bridge.dispose(); expect(lost.callbacks.size).toBe(0); expect(restored.callbacks.size).toBe(0);
    lost.fire(); restored.fire(); expect(events).toHaveLength(2); expect(rebuilt).toBe(retained);
  });
});
