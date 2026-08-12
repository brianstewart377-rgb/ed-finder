import { describe, expect, it } from 'vitest';
import type { ExplorationTrailPoint, ExplorationViewportVisit } from '@/lib/api';
import { decodeGpuPickColor, encodeGpuPickColor } from './gpuPicking';
import { buildExplorationTrailBuffers, buildExplorationVisitBuffers } from './explorationGeometry';

describe('personal exploration map geometry', () => {
  it('uses green for complete markers, yellow for partial markers, and purple for density', () => {
    const visits: ExplorationViewportVisit[] = [
      { kind: 'marker', system_id64: 1, system_name: 'Complete', x: 1, y: 2, z: 3, galaxy_region_id: 1, visit_count: 1, first_visited_at: 'a', last_visited_at: 'a', completion_state: 'complete', cell_size: null },
      { kind: 'marker', system_id64: 2, system_name: 'Partial', x: 4, y: 5, z: 6, galaxy_region_id: 1, visit_count: 1, first_visited_at: 'a', last_visited_at: 'a', completion_state: 'partial', cell_size: null },
      { kind: 'density', system_id64: null, system_name: null, x: 7, y: 8, z: 9, galaxy_region_id: null, visit_count: 4, first_visited_at: 'a', last_visited_at: 'a', completion_state: 'partial', cell_size: 500 },
    ];
    const buffers = buildExplorationVisitBuffers(visits, true);
    expect(Array.from(buffers.positions)).toEqual([1, 3, 7, 4, 6, 10, 7, 9, 13]);
    expect(Array.from(buffers.colors.slice(0, 3))).not.toEqual(Array.from(buffers.colors.slice(3, 6)));
    expect(Array.from(buffers.colors.slice(3, 6))).not.toEqual(Array.from(buffers.colors.slice(6, 9)));
  });

  it('sorts trail history chronologically and emits direction chevrons', () => {
    const point = (sequence: number, x: number): ExplorationTrailPoint => ({
      sequence, fact_id: sequence, system_id64: sequence, system_name: `S${sequence}`,
      visited_at: `2026-01-0${sequence}T00:00:00Z`, x, y: 0, z: 0,
      galaxy_region_id: 1, from_system_id64: sequence - 1 || null, distance_ly: 10,
    });
    const buffers = buildExplorationTrailBuffers([point(3, 30), point(1, 10), point(2, 20)]);
    expect(Array.from(buffers.positions.slice(0, 6))).toEqual([10, 0, 3, 20, 0, 3]);
    expect(buffers.arrowPositions.length).toBeGreaterThan(0);
  });

  it('round-trips 24-bit GPU pick IDs beyond the viewport point cap', () => {
    const index = 65_537;
    const encoded = encodeGpuPickColor(index);
    const pixel = new Uint8Array(encoded.map((channel) => Math.round(channel * 255)));
    expect(decodeGpuPickColor(pixel)).toBe(index);
  });
});
