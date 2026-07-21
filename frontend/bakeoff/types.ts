import type { RendererCandidateId } from '../../artifacts/map-foundation/stage-26b/map-renderer-adapter';
import type { DatasetSize } from '../../artifacts/map-foundation/stage-26b/map-bakeoff-scenarios';
import type { SystemRecord } from '../../artifacts/map-foundation/stage-26b/map-scene-contract';

export type RegionLabel = { id: number; name: string; position: [number, number, number] };
export type RegionBoundary = { source: [number, number, number]; target: [number, number, number] };
export type RegionLayerData = { labels: RegionLabel[]; boundaries: RegionBoundary[] };

export type CandidateProps = {
  systems: SystemRecord[];
  regions: RegionLayerData;
  onReady: () => void;
  onSelect: (id64: number, startedAt: number) => void;
};

export type HarnessSnapshot = {
  candidate: RendererCandidateId;
  datasetSize: DatasetSize;
  ready: boolean;
  selectedId64: number | null;
  selectionCount: number;
  initialLoadMs: number | null;
  clickLatencyMs: number | null;
  frameTimesMs: number[];
  fixtureResults: Record<string, 'pass' | 'fail'>;
  fixtureFailures: string[];
  regionLabelCount: number;
  regionBoundaryCount: number;
};

declare global {
  interface Window {
    __stage26bBakeoff?: {
      snapshot: () => HarnessSnapshot;
    };
  }
}
