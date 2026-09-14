import type {
  CameraState,
  GalaxySceneContract,
  GalaxySystemPoint,
  SpatialTarget,
  Vec3Ly,
} from './contracts';
import { GALAXY_CAMERA_FOV_RAD, galaxyCameraPose } from './galaxy-camera';
import { findGalaxyRegionAt, galaxyRegionsSceneLayer } from './galaxy-regions';

export type GalaxyLabelKind = 'region' | 'system';

export type GalaxyLabelCandidate = Readonly<{
  key: string;
  kind: GalaxyLabelKind;
  text: string;
  positionLy: Vec3Ly;
  target: SpatialTarget;
  selected: boolean;
  hovered: boolean;
  current: boolean;
}>;

export type ProjectedGalaxyLabel = GalaxyLabelCandidate &
  Readonly<{
    xPx: number;
    yPx: number;
    anchorXPx: number;
    anchorYPx: number;
    leaderEndXPx: number;
    placement: 'map' | 'atlas-left' | 'atlas-right';
    priority: number;
  }>;

export type GalaxyLabelViewport = Readonly<{
  width: number;
  height: number;
}>;

export type GalaxyLabelLayoutOptions = Readonly<{
  safeArea?: Partial<{
    top: number;
    right: number;
    bottom: number;
    left: number;
  }>;
  maximumSystemLabels?: number;
}>;

type ScreenProjection = Readonly<{
  xPx: number;
  yPx: number;
  depthLy: number;
}>;

type LabelBox = Readonly<{
  left: number;
  right: number;
  top: number;
  bottom: number;
}>;

const SYSTEM_LABEL_DISTANCE_LY = 30_000;
const DEFAULT_MAXIMUM_SYSTEM_LABELS = 8;

function subtract(left: Vec3Ly, right: Vec3Ly): Vec3Ly {
  return {
    x: left.x - right.x,
    y: left.y - right.y,
    z: left.z - right.z,
  };
}

function dot(left: Vec3Ly, right: Vec3Ly): number {
  return left.x * right.x + left.y * right.y + left.z * right.z;
}

function cross(left: Vec3Ly, right: Vec3Ly): Vec3Ly {
  return {
    x: left.y * right.z - left.z * right.y,
    y: left.z * right.x - left.x * right.z,
    z: left.x * right.y - left.y * right.x,
  };
}

function length(value: Vec3Ly): number {
  return Math.hypot(value.x, value.y, value.z);
}

function normalize(value: Vec3Ly): Vec3Ly {
  const magnitude = length(value);
  if (magnitude === 0) throw new RangeError('Cannot normalize a zero vector');
  return {
    x: value.x / magnitude,
    y: value.y / magnitude,
    z: value.z / magnitude,
  };
}

function targetKey(target: SpatialTarget): string {
  if (target.kind === 'system') return `system:${target.systemId64}`;
  if ('id' in target) return `${target.kind}:${target.id}`;
  return target.kind;
}

function systemPoints(
  scene: GalaxySceneContract,
): readonly GalaxySystemPoint[] {
  const points: GalaxySystemPoint[] = [];
  for (const contribution of scene.contributions) {
    if (contribution.owner !== 'FINDER') continue;
    for (const layer of contribution.layers) {
      if (layer.id !== 'finder-systems') continue;
      const payload = layer.payload as { systems?: unknown };
      if (!Array.isArray(payload.systems)) continue;
      for (const value of payload.systems) {
        if (!value || typeof value !== 'object') continue;
        const point = value as GalaxySystemPoint;
        if (
          typeof point.systemId64 === 'string' &&
          typeof point.name === 'string' &&
          point.positionLy &&
          [point.positionLy.x, point.positionLy.y, point.positionLy.z].every(
            Number.isFinite,
          )
        ) {
          points.push(point);
        }
      }
    }
  }
  return points;
}

/**
 * Collect only named targets already accepted by scene contributions. Region
 * anchors remain source-derived; this layer never invents a label position.
 */
export function galaxyLabelCandidates(
  scene: GalaxySceneContract,
  hoveredRegionId?: string,
): GalaxyLabelCandidate[] {
  const selectedKeys = new Set(scene.selection.map(targetKey));
  const candidates: GalaxyLabelCandidate[] = systemPoints(scene).map(
    (point) => {
      const target = { kind: 'system', systemId64: point.systemId64 } as const;
      return {
        key: targetKey(target),
        kind: 'system',
        text: point.name,
        positionLy: point.positionLy,
        target,
        selected: selectedKeys.has(targetKey(target)),
        hovered: false,
        current: false,
      };
    },
  );

  const regions = galaxyRegionsSceneLayer(scene);
  if (!regions) return candidates;
  const currentRegion = findGalaxyRegionAt(
    regions.payload.lookup,
    scene.camera.focusLy,
  );
  for (const region of regions.payload.regions) {
    const target = { kind: 'region', id: String(region.id) } as const;
    candidates.push({
      key: targetKey(target),
      kind: 'region',
      text: region.name,
      positionLy: region.labelLy,
      target,
      selected: selectedKeys.has(targetKey(target)),
      hovered: hoveredRegionId === target.id,
      current: currentRegion?.id === region.id,
    });
  }
  return candidates;
}

/** Match Babylon's perspective/orthographic camera basis in CSS pixels. */
export function projectGalaxyLabel(
  pointLy: Vec3Ly,
  camera: CameraState,
  viewport: GalaxyLabelViewport,
): ScreenProjection | null {
  if (
    !Number.isFinite(viewport.width) ||
    viewport.width <= 0 ||
    !Number.isFinite(viewport.height) ||
    viewport.height <= 0
  ) {
    throw new RangeError('Label viewport must have finite positive dimensions');
  }
  const pose = galaxyCameraPose(camera);
  const forward = normalize(subtract(pose.targetLy, pose.positionLy));
  const right = normalize(cross(pose.up, forward));
  const delta = subtract(pointLy, pose.positionLy);
  const depthLy = dot(delta, forward);
  if (depthLy <= Math.max(0.01, camera.distanceLy / 100_000)) return null;
  const cameraX = dot(delta, right);
  const cameraY = dot(delta, pose.up);
  const tangent = Math.tan(GALAXY_CAMERA_FOV_RAD / 2);
  const halfHeight =
    camera.projection === 'perspective'
      ? depthLy * tangent
      : camera.distanceLy * tangent;
  const halfWidth = halfHeight * (viewport.width / viewport.height);
  if (halfWidth <= 0 || halfHeight <= 0) return null;
  return {
    xPx: (cameraX / halfWidth / 2 + 0.5) * viewport.width,
    yPx: (0.5 - cameraY / halfHeight / 2) * viewport.height,
    depthLy,
  };
}

function priority(candidate: GalaxyLabelCandidate): number {
  if (candidate.kind === 'system' && candidate.selected) return 1_000;
  if (candidate.kind === 'region' && candidate.selected) return 950;
  if (candidate.hovered) return 900;
  if (candidate.current) return 850;
  if (candidate.kind === 'system') return 700;
  if (candidate.text === 'Galactic Centre') return 650;
  return 100;
}

function estimateBox(
  candidate: GalaxyLabelCandidate,
  xPx: number,
  yPx: number,
): LabelBox {
  const width = Math.min(
    candidate.kind === 'system' ? 230 : 180,
    Math.max(
      66,
      candidate.text.length * (candidate.kind === 'system' ? 7 : 6.4) + 22,
    ),
  );
  const height =
    candidate.kind === 'system' ? 28 : candidate.text.length > 22 ? 34 : 22;
  return {
    left: xPx - width / 2,
    right: xPx + width / 2,
    top: yPx - height / 2,
    bottom: yPx + height / 2,
  };
}

function overlaps(left: LabelBox, right: LabelBox): boolean {
  const gap = 6;
  return !(
    left.right + gap <= right.left ||
    left.left >= right.right + gap ||
    left.bottom + gap <= right.top ||
    left.top >= right.bottom + gap
  );
}

/**
 * Deterministic label solver. Every in-frame region name is retained: priority
 * only controls solve order and emphasis, never whether a region is rendered.
 * System labels remain deliberately budgeted and collision-managed.
 */
export function layoutGalaxyLabels(
  candidates: readonly GalaxyLabelCandidate[],
  camera: CameraState,
  viewport: GalaxyLabelViewport,
  options: GalaxyLabelLayoutOptions = {},
): ProjectedGalaxyLabel[] {
  const horizontal = Math.min(34, Math.max(14, viewport.width * 0.025));
  const vertical = Math.min(28, Math.max(12, viewport.height * 0.035));
  const safe = {
    top: Math.max(vertical, options.safeArea?.top ?? 0),
    right: Math.max(horizontal, options.safeArea?.right ?? 0),
    bottom: Math.max(vertical, options.safeArea?.bottom ?? 0),
    left: Math.max(horizontal, options.safeArea?.left ?? 0),
  };
  const centre = { x: viewport.width / 2, y: viewport.height / 2 };
  const projected = candidates.flatMap((candidate) => {
    const screen = projectGalaxyLabel(candidate.positionLy, camera, viewport);
    if (!screen) return [];
    if (
      candidate.kind === 'system' &&
      camera.distanceLy > SYSTEM_LABEL_DISTANCE_LY &&
      !candidate.selected
    ) {
      return [];
    }
    return [{ candidate, screen, priority: priority(candidate) }];
  });
  projected.sort((left, right) => {
    if (left.priority !== right.priority) return right.priority - left.priority;
    const leftDistance = Math.hypot(
      left.screen.xPx - centre.x,
      left.screen.yPx - centre.y,
    );
    const rightDistance = Math.hypot(
      right.screen.xPx - centre.x,
      right.screen.yPx - centre.y,
    );
    return (
      leftDistance - rightDistance ||
      left.candidate.key.localeCompare(right.candidate.key)
    );
  });

  const atlasRegions = projected.filter(
    (entry) => entry.candidate.kind === 'region',
  );
  const atlasActive =
    camera.distanceLy >= 100_000 && atlasRegions.length === 42;
  const accepted: ProjectedGalaxyLabel[] = atlasActive
    ? layoutRegionAtlas(atlasRegions, viewport, safe)
    : [];
  const occupiedBoxes: LabelBox[] = accepted.map((label) =>
    estimateBox(label, label.xPx, label.yPx),
  );
  let systemCount = 0;
  const maximumSystems =
    options.maximumSystemLabels ?? DEFAULT_MAXIMUM_SYSTEM_LABELS;
  const displacements = [
    [0, 0],
    [0, -42],
    [0, 42],
    [96, 0],
    [-96, 0],
    [78, -38],
    [-78, -38],
    [78, 38],
    [-78, 38],
  ] as const;

  for (const entry of projected) {
    if (atlasActive && entry.candidate.kind === 'region') continue;
    if (entry.candidate.kind === 'system' && systemCount >= maximumSystems) {
      continue;
    }
    const isRegion = entry.candidate.kind === 'region';
    const anchorIsInFrame =
      entry.screen.xPx >= 0 &&
      entry.screen.xPx <= viewport.width &&
      entry.screen.yPx >= 0 &&
      entry.screen.yPx <= viewport.height;
    if (isRegion && !anchorIsInFrame) continue;
    const important = entry.priority >= 850;
    const offsets =
      isRegion || important ? displacements : displacements.slice(0, 1);
    let placed = false;
    for (const [offsetX, offsetY] of offsets) {
      const xPx = entry.screen.xPx + offsetX;
      const yPx = entry.screen.yPx + offsetY;
      const box = estimateBox(entry.candidate, xPx, yPx);
      if (
        box.left < safe.left ||
        box.right > viewport.width - safe.right ||
        box.top < safe.top ||
        box.bottom > viewport.height - safe.bottom ||
        occupiedBoxes.some((occupied) => overlaps(occupied, box))
      ) {
        continue;
      }
      accepted.push({
        ...entry.candidate,
        xPx,
        yPx,
        anchorXPx: entry.screen.xPx,
        anchorYPx: entry.screen.yPx,
        leaderEndXPx: xPx,
        placement: 'map',
        priority: entry.priority,
      });
      occupiedBoxes.push(box);
      if (!isRegion) systemCount += 1;
      placed = true;
      break;
    }
    if (isRegion && !placed) {
      // Region names are an invariant, not a decluttering budget. If every
      // collision-free displacement fails, keep the source anchor truthful and
      // clamp only the label box into the safe area. Overlap is preferable to
      // silently removing a named region.
      const anchorBox = estimateBox(
        entry.candidate,
        entry.screen.xPx,
        entry.screen.yPx,
      );
      const halfWidth = (anchorBox.right - anchorBox.left) / 2;
      const halfHeight = (anchorBox.bottom - anchorBox.top) / 2;
      const minX = safe.left + halfWidth;
      const maxX = viewport.width - safe.right - halfWidth;
      const minY = safe.top + halfHeight;
      const maxY = viewport.height - safe.bottom - halfHeight;
      const xPx = clamp(entry.screen.xPx, minX, maxX);
      const yPx = clamp(entry.screen.yPx, minY, maxY);
      const box = estimateBox(entry.candidate, xPx, yPx);
      accepted.push({
        ...entry.candidate,
        xPx,
        yPx,
        anchorXPx: entry.screen.xPx,
        anchorYPx: entry.screen.yPx,
        leaderEndXPx: xPx,
        placement: 'map',
        priority: entry.priority,
      });
      occupiedBoxes.push(box);
    }
  }
  return accepted;
}

function clamp(value: number, minimum: number, maximum: number): number {
  if (maximum < minimum) return (minimum + maximum) / 2;
  return Math.min(maximum, Math.max(minimum, value));
}

function layoutRegionAtlas(
  regions: ReadonlyArray<{
    candidate: GalaxyLabelCandidate;
    screen: ScreenProjection;
    priority: number;
  }>,
  viewport: GalaxyLabelViewport,
  safe: { top: number; right: number; bottom: number; left: number },
): ProjectedGalaxyLabel[] {
  // Lowest projected x values use the left rail; highest use the right. Each
  // side is then ordered by source-anchor y, minimizing leader crossings.
  const split = [...regions].sort(
    (left, right) =>
      left.screen.xPx - right.screen.xPx ||
      left.candidate.key.localeCompare(right.candidate.key),
  );
  const midpoint = Math.ceil(split.length / 2);
  const railWidth = Math.min(230, Math.max(138, viewport.width * 0.22));
  const leftX = safe.left + railWidth / 2;
  const rightX = viewport.width - safe.right - railWidth / 2;
  const makeRail = (
    entries: typeof split,
    placement: 'atlas-left' | 'atlas-right',
    xPx: number,
  ) =>
    entries
      .sort(
        (left, right) =>
          left.screen.yPx - right.screen.yPx ||
          left.candidate.key.localeCompare(right.candidate.key),
      )
      .map((entry, index) => {
        const yPx =
          safe.top +
          ((index + 0.5) * (viewport.height - safe.top - safe.bottom)) /
            entries.length;
        return {
          ...entry.candidate,
          xPx,
          yPx,
          anchorXPx: entry.screen.xPx,
          anchorYPx: entry.screen.yPx,
          leaderEndXPx:
            placement === 'atlas-left'
              ? xPx + railWidth / 2
              : xPx - railWidth / 2,
          placement,
          priority: entry.priority,
        } satisfies ProjectedGalaxyLabel;
      });
  return [
    ...makeRail(split.slice(0, midpoint), 'atlas-left', leftX),
    ...makeRail(split.slice(midpoint), 'atlas-right', rightX),
  ];
}
