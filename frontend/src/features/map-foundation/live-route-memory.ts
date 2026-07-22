export const LIVE_ROUTE_HEAP_BUDGET_BYTES = 256 * 1_048_576;

export type LiveRouteHeapMeasurement = {
  supported: boolean;
  budgetBytes: number;
  sampleCount: number;
  samplesBytes: number[];
  minBytes: number | null;
  maxBytes: number | null;
  spreadBytes: number | null;
  withinBudget: boolean | null;
};

export type LiveRouteMapSnapshot = {
  renderer: 'r3f';
  routeFlagEnabled: true;
  surfaceKind: 'ready' | 'empty' | 'error';
  finderSystemCount: number;
  finderResponseTruncated: boolean;
  heatmapCellCount: number;
  heatmapSourceTruncated: boolean;
  aggregateHullCount: number;
  timelinePointCount: number;
  estimatedOverlayBufferBytes: number;
  overlayBufferWithinBudget: boolean;
  regionGeometryExposed: boolean;
  regionGeometryVisible: boolean;
  regionLabelCount: number;
  regionBoundaryCount: number;
  regionPositionBytes: number;
  heapBudgetBytes: number;
};

type ChromiumMemoryPerformance = Performance & {
  memory?: { usedJSHeapSize?: number };
};

function usedHeapBytes(): number | null {
  const value = (performance as ChromiumMemoryPerformance).memory?.usedJSHeapSize;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export async function measureLiveRouteHeap(
  sampleCount = 5,
  settleMs = 100,
): Promise<LiveRouteHeapMeasurement> {
  if (!Number.isInteger(sampleCount) || sampleCount < 1) {
    throw new Error('heap sample count must be a positive integer');
  }
  const samplesBytes: number[] = [];
  for (let index = 0; index < sampleCount; index += 1) {
    if (index > 0 && settleMs > 0) {
      await new Promise((resolve) => window.setTimeout(resolve, settleMs));
    }
    const sample = usedHeapBytes();
    if (sample == null) break;
    samplesBytes.push(sample);
  }
  const supported = samplesBytes.length === sampleCount;
  const minBytes = supported ? Math.min(...samplesBytes) : null;
  const maxBytes = supported ? Math.max(...samplesBytes) : null;
  return {
    supported,
    budgetBytes: LIVE_ROUTE_HEAP_BUDGET_BYTES,
    sampleCount: samplesBytes.length,
    samplesBytes,
    minBytes,
    maxBytes,
    spreadBytes: minBytes != null && maxBytes != null ? maxBytes - minBytes : null,
    withinBudget: maxBytes == null ? null : maxBytes <= LIVE_ROUTE_HEAP_BUDGET_BYTES,
  };
}

declare global {
  interface Window {
    __stage26eProductionMap?: {
      snapshot: () => LiveRouteMapSnapshot;
      measureHeap: (sampleCount?: number) => Promise<LiveRouteHeapMeasurement>;
    };
  }
}
