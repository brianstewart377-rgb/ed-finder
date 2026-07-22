import { describe, expect, it } from 'vitest';
import type { ClusterResult } from '@/features/cluster-search/useClusterSearch';
import type { WatchlistEntry } from '@/lib/api';
import type { PinnedEntry } from '@/store/pinnedStore';
import type { EvidenceSystemSummaryResponse, SystemDetail, SystemResult } from '@/types/api';
import { createFoundationDemoScene } from './demo-scene';
import { applyFeatureHandoff, resolveMapInteraction, toSystemRecord } from './feature-handoffs';

const result = (id64: number, x = id64, z = -id64): SystemResult => ({
  id64,
  name: `System ${id64}`,
  coords: { x, y: 0, z },
  population: 1_000,
  primaryEconomy: 'Industrial',
  overall_development_potential: 77,
});

const detail = (id64: number): SystemDetail => ({
  id64,
  name: `Detail ${id64}`,
  x: id64,
  y: 0,
  z: -id64,
  population: 2_000,
  primary_economy: 'Refinery',
});

const evidence = (systemId64: number): EvidenceSystemSummaryResponse => ({
  schema_version: 'evidence_store/v1',
  system_id64: systemId64,
  observed_fact_count: 1,
  imported_record_count: 0,
  derived_feature_count: 0,
  open_rule_proposal_count: 0,
  focus_areas: [],
  records: [],
  derived_features: [],
  open_rule_proposals: [],
});

describe('Stage 26D inbound feature hand-offs', () => {
  it('maps Finder results without resetting camera or layers and keeps bounded metadata', () => {
    const scene = createFoundationDemoScene(100_000);
    scene.camera = { center: { x: 123, z: 456 }, zoom: 9, pitchDeg: 20, bearingDeg: 30 };
    const layers = scene.layers;
    const handoff = applyFeatureHandoff(scene, {
      type: 'finder',
      systems: [result(11), result(12)],
      selectedSystemId64: 12,
      metadata: { count: 900, truncated: true, continuationToken: 'next-page' },
    });

    expect(handoff.scene.camera).toEqual(scene.camera);
    expect(handoff.scene.layers).toEqual(layers);
    expect(handoff.scene.selectedSystemId64).toBe(12);
    expect(handoff.scene.boundedResponse).toEqual({ count: 900, truncated: true, continuationToken: 'next-page' });
    expect(handoff.acceptedSystemIds).toEqual([11, 12]);
  });

  it('maps Compare and both real saved-system persistence shapes', () => {
    let scene = createFoundationDemoScene(100_000);
    scene = applyFeatureHandoff(scene, {
      type: 'compare', systems: [result(21), result(22)], leftId64: 21, rightId64: 22,
    }).scene;
    expect(scene.highlights).toEqual([{ type: 'compare', leftId64: 21, rightId64: 22 }]);

    const pinned: PinnedEntry = {
      id64: 23, name: 'Pinned', x: 23, y: 0, z: -23, population: null,
      is_colonised: false, economy: 'Tourism', pinned_at: '2026-07-22T00:00:00Z',
    };
    const watched: WatchlistEntry = {
      system_id64: 24, name: 'Watched', x: 24, y: 0, z: -24, population: null,
      is_colonised: false, added_at: '2026-07-22T00:00:00Z', economy_suggestion: 'High Tech',
    };
    const saved = applyFeatureHandoff(scene, { type: 'savedSystems', systems: [pinned, watched] });
    expect(saved.acceptedSystemIds).toEqual([23, 24]);
    expect(saved.scene.highlights.at(-1)).toMatchObject({ type: 'cluster', cluster: { memberIds: [23, 24], label: 'Saved Systems' } });
  });

  it('requires coordinate-bearing evidence context and reports missing coordinates', () => {
    const noCoords = { ...result(31), coords: null };
    const mapped = applyFeatureHandoff(createFoundationDemoScene(100_000), {
      type: 'evidenceMap',
      entries: [
        { summary: evidence(30), system: result(30) },
        { summary: evidence(31), system: noCoords },
        { summary: evidence(32), system: result(99) },
      ],
    });
    expect(mapped.acceptedSystemIds).toEqual([30]);
    expect(mapped.omittedSystemIds).toEqual([31, 32]);
    expect(mapped.scene.boundedResponse.truncated).toBe(true);
    expect(mapped.scene.highlights.at(-1)).toMatchObject({ type: 'cluster', cluster: { memberIds: [30], label: 'Evidence Systems' } });
  });

  it('maps System Detail into selected context', () => {
    const scene = createFoundationDemoScene(100_000);
    const guaranteedBefore = [...scene.guaranteedSystemIds];
    const mapped = applyFeatureHandoff(scene, { type: 'systemDetail', system: detail(40) });
    expect(mapped.scene.selectedSystemId64).toBe(40);
    expect(mapped.scene.guaranteedSystemIds).toContain(40);
    expect(mapped.scene.systems.find((system) => system.id64 === 40)).toMatchObject({ primaryEconomy: 'Refinery' });
    expect(scene.guaranteedSystemIds).toEqual(guaranteedBefore);
  });

  it('maps only coordinate-resolved cluster members and retains group context', () => {
    const cluster: ClusterResult = {
      anchor_id64: 50, anchor_name: 'Cluster Anchor', anchor_coords: { x: 50, y: 0, z: -50 },
      galaxy_region: 'Inner Orion Spur', coverage_score: 80, economy_diversity: 2, total_viable: 3,
      agriculture_count: 0, agriculture_best: 0, refinery_count: 1, refinery_best: 80,
      industrial_count: 1, industrial_best: 70, hightech_count: 0, hightech_best: 0,
      military_count: 0, military_best: 0, tourism_count: 0, tourism_best: 0,
      distance_ly: 10, cluster_radius_ly: 25,
      slots: [{ slot_index: 0, label: 'Industry', economies: ['Industrial'], matches: [
        { system_id64: 51, system_name: 'Resolved', scores: {}, distance_from_anchor_ly: 5 },
        { system_id64: 52, system_name: 'Missing', scores: {}, distance_from_anchor_ly: 9 },
      ] }],
    };
    const mapped = applyFeatureHandoff(createFoundationDemoScene(100_000), {
      type: 'clusterSearch', cluster, systemsById: new Map([[51, result(51)]]),
    });
    expect(mapped.acceptedSystemIds).toEqual([51, 50]);
    expect(mapped.omittedSystemIds).toEqual([52]);
    expect(mapped.scene.clusters.at(-1)).toMatchObject({
      anchorId64: 50,
      memberIds: [50, 51],
      groupContext: { name: 'Cluster Anchor' },
    });
  });

  it('round-trips planner overlays without mutating a plan payload', () => {
    const scene = createFoundationDemoScene(100_000);
    const payload = { projectId: 'draft-1', mode: 'map' };
    const mapped = applyFeatureHandoff(scene, {
      type: 'planner',
      systems: [result(60)],
      highlights: scene.highlights,
      layers: scene.layers,
      clusters: scene.clusters,
      workflowPayload: payload,
    });
    expect(mapped.scene.returnWorkflow).toMatchObject({ type: 'planner', workflowPayload: payload });
    expect(payload).toEqual({ projectId: 'draft-1', mode: 'map' });
    expect(mapped.scene.camera).toEqual(scene.camera);
  });

  it('normalizes every coordinate-bearing production shape', () => {
    expect(toSystemRecord(result(70))).toMatchObject({ id64: 70, primaryEconomy: 'Industrial' });
    expect(toSystemRecord(detail(71))).toMatchObject({ id64: 71, primaryEconomy: 'Refinery' });
  });
});

describe('Stage 26D outbound interaction routing', () => {
  it('updates selected-system context with cluster anchor identity', () => {
    const scene = createFoundationDemoScene(100_000);
    const resolved = resolveMapInteraction(scene, { type: 'selectSystem', systemId64: 81, clusterAnchorId64: 80 });
    expect(resolved.scene.selectedSystemId64).toBe(81);
    expect(resolved.command).toEqual({ type: 'selectSystem', systemId64: 81, clusterAnchorId64: 80 });
  });

  it('routes every feature request through host commands', () => {
    const scene = { ...createFoundationDemoScene(100_000), selectedSystemId64: 91 };
    expect(resolveMapInteraction(scene, { type: 'navigateToFinder' }).command.type).toBe('openFinder');
    expect(resolveMapInteraction(scene, { type: 'navigateToSystemDetail', systemId64: 91 }).command.type).toBe('openSystemDetail');
    expect(resolveMapInteraction(scene, { type: 'navigateToCompare', leftId64: 91, rightId64: 92 }).command.type).toBe('openCompare');
    expect(resolveMapInteraction(scene, { type: 'navigateToSavedSystems' }).command.type).toBe('openSavedSystems');
    expect(resolveMapInteraction(scene, { type: 'navigateToEvidenceMap' }).command.type).toBe('openEvidenceMap');
    expect(resolveMapInteraction(scene, { type: 'navigateToClusterSearch', clusterId: 'cluster-91' }).command.type).toBe('openClusterSearch');
    expect(resolveMapInteraction(scene, { type: 'navigateToPlanner' }).command).toEqual({ type: 'openPlanner', systemId64: 91 });
  });

  it('requires an explicit selected system before planner navigation', () => {
    const scene = { ...createFoundationDemoScene(100_000), selectedSystemId64: null };
    const resolved = resolveMapInteraction(scene, { type: 'navigateToPlanner' });
    expect(resolved.command).toEqual({ type: 'plannerSelectionRequired' });
    expect(resolved.scene).toBe(scene);
  });
});
