import { describe, expect, it, vi } from 'vitest';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { PickingInfo } from '@babylonjs/core/Collisions/pickingInfo.js';
import { Ray } from '@babylonjs/core/Culling/ray.js';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';

import type { BodyVisualDescriptor, SystemSceneContract } from '../contracts';
import {
  applySystemCamera,
  createBabylonSession,
  createBabylonSystemScene,
} from './adapter';

function body(
  bodyId: number,
  name: string,
  parentId: number | null,
  distance?: number,
  bodyClass = 'Planet',
): BodyVisualDescriptor {
  return {
    ref: { systemId64: '42', bodyId },
    name,
    ...(parentId === null
      ? {}
      : { parent: { systemId64: '42', bodyId: parentId } }),
    class: { value: bodyClass, representation: 'AUTHORITATIVE' },
    ...(distance === undefined
      ? {}
      : {
          distanceFromArrivalLs: {
            value: distance,
            representation: 'AUTHORITATIVE',
          },
        }),
    displayRadius: bodyClass === 'Star' ? 2.2 : 0.68,
    orbital: { placement: 'DETERMINISTIC_SCHEMATIC' },
    rings: { state: 'UNKNOWN', bands: [] },
  };
}

function fixture(): SystemSceneContract {
  return {
    kind: 'system',
    revision: 1,
    systemId64: '42',
    fidelity: 'S1',
    camera: {
      systemId64: '42',
      focus: { kind: 'system', systemId64: '42' },
      semanticDistance: 80,
      bearingRad: -0.8,
      pitchRad: 0.6,
      revision: 1,
    },
    bodies: [
      body(0, 'Sol', null, 0, 'Star'),
      body(2, 'Earth', 0, 500),
      body(3, 'Luna', 2, 501),
      body(4, 'Second moon', 2, 502),
      body(5, 'Mars', 0, 1_000),
      body(8, 'Binary barycentre', null, 0, 'Barycentre'),
      body(9, 'Binary A', 8, 5, 'Star'),
      body(10, 'Binary B', 8, 10, 'Star'),
      body(11, 'Unattached', 999, 20),
      body(12, 'Moon with unknown distance', 2),
    ],
    infrastructure: [],
    contributions: [],
  };
}

describe('hierarchical System Map Babylon presentation', () => {
  it('keeps large hierarchy fits inside the camera far plane and guards non-finite distances', () => {
    const engine = new NullEngine();
    const contract = fixture();
    const product = createBabylonSystemScene(engine, {
      ...contract,
      camera: { ...contract.camera, semanticDistance: 1_000_000 },
    });
    expect(product.camera.position.length()).toBeCloseTo(1_000_000);
    for (const entry of product.bodies) {
      expect(
        Vector3.Distance(product.camera.position, entry.mesh.position) +
          entry.layout.body.displayRadius,
      ).toBeLessThan(product.camera.maxZ);
    }
    for (const semanticDistance of [Number.NaN, Infinity, Number.MAX_VALUE]) {
      applySystemCamera(
        product.camera,
        { ...contract.camera, semanticDistance },
        product.bodies,
      );
      expect(product.camera.position.asArray().every(Number.isFinite)).toBe(
        true,
      );
      expect(Number.isFinite(product.camera.maxZ)).toBe(true);
      expect(product.camera.maxZ).toBeGreaterThan(
        product.camera.position.length(),
      );
    }
    product.scene.dispose();
    engine.dispose();
  });

  it('draws one faint guide per parent at that parent, with distinct pickable unknown and barycentre markers', () => {
    const engine = new NullEngine();
    const product = createBabylonSystemScene(engine, fixture());
    const guides = product.orbitMesh?.metadata.guides as {
      parentBodyId: number;
      position: { x: number; y: number; z: number };
      radius: number;
    }[];
    expect(
      guides.map((guide) => guide.parentBodyId).sort((a, b) => a - b),
    ).toEqual([0, 2, 8]);
    expect(product.orbitMesh?.isPickable).toBe(false);
    expect(product.orbitMesh?.alpha).toBeLessThan(0.5);
    const vertices = product.orbitMesh!.getVerticesData('position')!;
    guides.forEach((guide, index) => {
      const parent = product.bodies.find(
        (entry) => entry.layout.body.ref.bodyId === guide.parentBodyId,
      )!;
      expect(guide.position).toEqual(parent.layout.position);
      const start = index * 97 * 3;
      expect(vertices[start]).toBeCloseTo(guide.position.x + guide.radius, 4);
      expect(vertices[start + 1]).toBeCloseTo(guide.position.y, 4);
      expect(vertices[start + 2]).toBeCloseTo(guide.position.z, 4);
    });
    expect(product.parentLinkMesh).toBeNull();
    for (const id of [11, 12]) {
      const unknown = product.bodies.find(
        (entry) => entry.layout.body.ref.bodyId === id,
      )!;
      expect(unknown.mesh.getClassName()).toBe('LinesMesh');
      expect(unknown.mesh.isPickable).toBe(true);
      expect(unknown.mesh.metadata).toMatchObject({
        markerKind: 'position-unknown',
        spatialTarget: { kind: 'body', ref: { systemId64: '42', bodyId: id } },
      });
      expect(unknown.mesh.position.asArray()).not.toEqual([0, 0, 0]);
      unknown.mesh.computeWorldMatrix(true);
      const hit = product.scene.pickWithRay(
        new Ray(
          unknown.mesh.position.add(
            new Vector3(unknown.layout.body.displayRadius, 10, 0),
          ),
          new Vector3(0, -1, 0),
        ),
        (mesh) => mesh === unknown.mesh,
      );
      expect(hit?.pickedMesh).toBe(unknown.mesh);
    }
    const barycentre = product.bodies.find(
      (entry) => entry.layout.body.ref.bodyId === 8,
    )!;
    expect(barycentre.mesh.getClassName()).toBe('LinesMesh');
    expect(barycentre.mesh.getTotalVertices()).toBe(4);
    expect(barycentre.mesh.metadata.markerKind).toBe('barycentre');
    barycentre.mesh.computeWorldMatrix(true);
    expect(
      product.scene.pickWithRay(
        new Ray(
          barycentre.mesh.position.add(new Vector3(0, 10, 0)),
          new Vector3(0, -1, 0),
        ),
        (mesh) => mesh === barycentre.mesh,
      )?.pickedMesh,
    ).toBe(barycentre.mesh);
    const orbitMesh = product.orbitMesh!;
    product.scene.dispose();
    expect(orbitMesh.isDisposed()).toBe(true);
    expect(barycentre.mesh.isDisposed()).toBe(true);
    engine.dispose();
  });

  it('outlines a parent region when every child has unknown orbital distance', () => {
    const engine = new NullEngine();
    const product = createBabylonSystemScene(engine, {
      ...fixture(),
      bodies: [body(0, 'Sol', null, 0, 'Star'), body(2, 'Unplaced planet', 0)],
    });
    const [parent, child] = product.bodies;
    expect(child!.layout.placement).toBe('unplaced');
    expect(child!.layout.orbitRadius).toBe(0);
    expect(child!.mesh.metadata.markerKind).toBe('position-unknown');
    expect(product.orbitMesh?.metadata.guides).toEqual([
      {
        parentBodyId: 0,
        position: parent!.layout.position,
        radius: parent!.layout.regionRadius,
      },
    ]);
    expect(product.orbitMesh?.getTotalVertices()).toBe(97);
    expect(product.orbitMesh?.isPickable).toBe(false);
    expect(product.parentLinkMesh).toBeNull();
    product.scene.dispose();
    engine.dispose();
  });

  it('renders only selected or hovered body links and disposes replaced interaction geometry', () => {
    const engine = new NullEngine();
    const session = createBabylonSession(engine, 'WEBGL2');
    const emit = vi.fn();
    const contract = fixture();
    session.execute?.({ type: 'LOAD_SCENE', scene: contract }, emit);
    const scene = engine.scenes.at(-1)!;
    const links = () => scene.getMeshByName('system-parent-links');
    expect(links()).toBeNull();

    const selectedCamera = {
      ...contract.camera,
      focus: { kind: 'body' as const, ref: { systemId64: '42', bodyId: 2 } },
      revision: 2,
    };
    session.execute?.({ type: 'SET_CAMERA', camera: selectedCamera }, emit);
    const selectedLinks = links()!;
    expect(selectedLinks.metadata.links).toEqual([
      { parentBodyId: 0, bodyId: 2 },
      { parentBodyId: 2, bodyId: 3 },
      { parentBodyId: 2, bodyId: 4 },
      { parentBodyId: 2, bodyId: 12 },
    ]);
    expect(selectedLinks.isPickable).toBe(false);
    session.execute?.(
      { type: 'SET_CAMERA', camera: { ...selectedCamera, bearingRad: 0.2 } },
      emit,
    );
    expect(links()).toBe(selectedLinks);

    const hit = new PickingInfo();
    hit.hit = true;
    hit.pickedMesh = scene.getMeshByName('system-body-9');
    vi.spyOn(scene, 'pick').mockReturnValue(hit);
    session.execute?.({ type: 'HOVER', screenX: 20, screenY: 30 }, emit);
    const hoverLinks = links()!;
    expect(selectedLinks.isDisposed()).toBe(true);
    expect(hoverLinks.metadata.links).toContainEqual({
      parentBodyId: 8,
      bodyId: 9,
    });
    expect(hoverLinks.metadata.links).not.toContainEqual({
      parentBodyId: 8,
      bodyId: 10,
    });
    expect(hoverLinks.metadata.links).toHaveLength(5);
    expect(emit).toHaveBeenCalledWith({
      type: 'TARGET_HOVERED',
      target: { kind: 'body', ref: { systemId64: '42', bodyId: 9 } },
    });

    session.execute?.({ type: 'CLEAR_HOVER' }, emit);
    expect(hoverLinks.isDisposed()).toBe(true);
    expect(links()!.metadata.links).toHaveLength(4);
    const restoredLinks = links()!;
    session.execute?.({ type: 'SET_CAMERA', camera: contract.camera }, emit);
    expect(restoredLinks.isDisposed()).toBe(true);
    expect(links()).toBeNull();

    hit.pickedMesh = scene.getMeshByName('system-body-11');
    session.execute?.({ type: 'PICK', screenX: 20, screenY: 30 }, emit);
    expect(emit).toHaveBeenCalledWith({
      type: 'TARGET_PICKED',
      target: { kind: 'body', ref: { systemId64: '42', bodyId: 11 } },
    });
    session.dispose();
  });
});
