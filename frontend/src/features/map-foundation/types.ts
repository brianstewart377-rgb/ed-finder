import type {
  CameraState,
  ClusterRepresentation,
  GalaxyCoord,
  MapInteractionEvent,
  MapReturnWorkflow,
  MapSceneState,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { FoundationPerformanceMeasurement } from './performance';

export type RegionLabel = {
  id: number;
  name: string;
  position: [number, number, number];
};

export type RegionBoundary = {
  source: [number, number, number];
  target: [number, number, number];
};

export type RegionLayerData = {
  labels: RegionLabel[];
  boundaries: RegionBoundary[];
};

export type ViewportSize = { width: number; height: number };

export type VisibilityMetadata = {
  totalInViewBackground: number;
  returnedBackground: number;
  aggregateRemainder: number;
  truncated: boolean;
  guaranteedCount: number;
};

export type VisibleScene = {
  background: SystemRecord[];
  guaranteed: SystemRecord[];
  metadata: VisibilityMetadata;
};

export type FoundationSnapshot = {
  ready: boolean;
  datasetSize: number;
  camera: CameraState;
  selectedSystemId64: number | null;
  regionLabelCount: number;
  regionBoundaryCount: number;
  visible: VisibilityMetadata;
  highlightCount: number;
  clusterCount: number;
  overlapCandidateIds: number[];
  contextState: 'ready' | 'lost' | 'restored' | 'usable';
  lastInteraction: MapInteractionEvent | null;
  returnWorkflowType: MapReturnWorkflow['type'] | null;
  lastHostCommand: string;
  omittedHandoffSystemIds: number[];
};

export type FoundationRendererProps = {
  scene: MapSceneState;
  regions: RegionLayerData;
  viewport: ViewportSize;
  maxBackgroundPoints?: number;
  onInteraction: (event: MapInteractionEvent) => void;
  onVisibilityChange?: (metadata: VisibilityMetadata) => void;
  onReady?: () => void;
};

export type ClusterGeometry = {
  cluster: ClusterRepresentation;
  anchor: SystemRecord | null;
  members: SystemRecord[];
  edgePositions: Float32Array;
  hullPositions: Float32Array | null;
};

export type ProjectedLabel = RegionLabel & { screen: GalaxyCoord; visible: boolean };

declare global {
  interface Window {
    __stage26cFoundation?: {
    snapshot: () => FoundationSnapshot;
    loseContext: () => boolean;
    measurePerformance: () => Promise<FoundationPerformanceMeasurement>;
    };
  }
}
