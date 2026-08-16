import { useMemo } from 'react';
import * as THREE from 'three';
import type { ProductionHeatmapGeometry } from './types';

/**
 * Density swirl visualization: particle-based representation of star density
 * matching ED in-game galaxy map aesthetic.
 *
 * Each cell becomes a particle sized by color brightness (which encodes density).
 * Renders at wide zoom, fades as real stars come into view.
 */
export function DensitySwirl({
  heatmap,
  opacity = 1,
}: {
  heatmap: ProductionHeatmapGeometry | null;
  opacity?: number;
}) {
  const buffers = useMemo(() => {
    if (!heatmap || heatmap.positions.length === 0) {
      return { positions: new Float32Array(0), colors: new Float32Array(0), sizes: new Float32Array(0) };
    }

    const positionCount = heatmap.positions.length / 3;
    const sizes = new Float32Array(positionCount);
    const color = new THREE.Color();
    const hsl = { h: 0, s: 0, l: 0 };

    // Derive particle size from color brightness (brightness ≈ density in heatmap)
    for (let i = 0; i < positionCount; i++) {
      color.setRGB(
        heatmap.colors[i * 3],
        heatmap.colors[i * 3 + 1],
        heatmap.colors[i * 3 + 2],
      );

      // Size based on brightness: darker (sparse) → smaller, brighter (dense) → larger
      color.getHSL(hsl);
      sizes[i] = 2 + hsl.l * 18; // 2-20 range, scaled by lightness
    }

    return { positions: heatmap.positions, colors: heatmap.colors, sizes };
  }, [heatmap]);

  if (buffers.positions.length === 0) return null;

  return (
    <points renderOrder={1}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[buffers.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[buffers.colors, 3]} />
        <bufferAttribute attach="attributes-size" args={[buffers.sizes, 1]} />
      </bufferGeometry>
      <pointsMaterial
        vertexColors
        size={1}
        sizeAttenuation={true}
        transparent={true}
        opacity={opacity}
        depthWrite={false}
        fog={false}
      />
    </points>
  );
}
