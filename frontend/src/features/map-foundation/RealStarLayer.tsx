import { useMemo } from 'react';
import type { MapViewportSystem } from '@/lib/api';
import { buildRealStarBuffers } from '@/features/map/viewportSystems';
import { GlowPointsMaterial } from './glowPoints';
import { attenuatedPointSize } from './camera';

export interface RealStarLayerProps {
  systems: MapViewportSystem[];
  zoom: number;
  opacity: number; // 0–1, controls layer visibility during fade
}

// The zoom-in detail lane: renders the individual systems fetched for the
// current viewport as a glowing, spectral-colored point cloud, over the
// aggregate heatmap. Reuses the map's glow point shader.
export function RealStarLayer({ systems, zoom, opacity }: RealStarLayerProps) {
  const { positions, colors } = useMemo(() => buildRealStarBuffers(systems), [systems]);
  if (systems.length === 0) return null;
  return (
    <points renderOrder={7}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <GlowPointsMaterial
        vertexColors
        size={attenuatedPointSize(zoom, 5)}
        sizeAttenuation
        opacity={opacity}
      />
    </points>
  );
}
