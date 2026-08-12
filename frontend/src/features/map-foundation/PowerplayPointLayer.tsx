import { useMemo } from 'react';
import * as THREE from 'three';
import type { PowerplaySystemState } from '@/lib/api';
import { attenuatedPointSize } from './camera';
import { powerColour, powerplayFreshness, powerplayStateSize } from './powerplayPresentation';

export function PowerplayPointLayer({ systems, zoom }: { systems: PowerplaySystemState[]; zoom: number }) {
  const groups = useMemo(() => {
    const grouped = new Map<number, { positions: number[]; colours: number[] }>();
    systems.forEach((system) => {
      if (system.x == null || system.y == null || system.z == null) return;
      const size = powerplayStateSize(system.control_state);
      const group = grouped.get(size) ?? { positions: [], colours: [] };
      group.positions.push(system.x, system.z, system.y + 14);
      const colour = new THREE.Color(powerColour(system.controlling_power));
      const freshness = powerplayFreshness(system.uncertainty);
      group.colours.push(colour.r * freshness, colour.g * freshness, colour.b * freshness);
      grouped.set(size, group);
    });
    return [...grouped.entries()].map(([size, values]) => ({
      size,
      positions: new Float32Array(values.positions),
      colours: new Float32Array(values.colours),
    }));
  }, [systems]);

  return <group renderOrder={12}>
    {groups.map((group) => <points key={group.size} renderOrder={12}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[group.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[group.colours, 3]} />
      </bufferGeometry>
      <pointsMaterial
        vertexColors
        size={attenuatedPointSize(zoom, group.size)}
        sizeAttenuation
        transparent
        opacity={0.95}
        depthWrite={false}
      />
    </points>)}
  </group>;
}
