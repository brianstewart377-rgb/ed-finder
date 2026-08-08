import { useEffect, useMemo } from 'react';
import * as THREE from 'three';

export const GALAXY_CENTER = { x: 25.2, z: 25_899.9 } as const;
export const GALAXY_RADIUS_LY = 50_000;
export const GALAXY_POINT_COUNT = 18_000;
export const GALACTIC_CORE_GLOW_CLOSE_RADIUS_LY = 18_000;
export const GALACTIC_CORE_GLOW_WIDE_RADIUS_LY = 10_000;
export const GALACTIC_CORE_GLOW_CLOSE_ZOOM = 70;
export const GALACTIC_CORE_GLOW_WIDE_ZOOM = 145;
export const GALACTIC_CORE_GLOW_HEIGHT_LY = -850;

export function galacticCoreGlowPresentation(zoom: number, spatial: boolean) {
  const closeProgress = Math.max(0, Math.min(
    1,
    (GALACTIC_CORE_GLOW_WIDE_ZOOM - zoom)
      / (GALACTIC_CORE_GLOW_WIDE_ZOOM - GALACTIC_CORE_GLOW_CLOSE_ZOOM),
  ));
  const easedProgress = closeProgress * closeProgress * (3 - 2 * closeProgress);
  return {
    radiusLy: GALACTIC_CORE_GLOW_WIDE_RADIUS_LY
      + (GALACTIC_CORE_GLOW_CLOSE_RADIUS_LY - GALACTIC_CORE_GLOW_WIDE_RADIUS_LY)
      * easedProgress,
    opacity: (spatial ? 0.38 : 0.44)
      + (spatial ? 0.68 - 0.38 : 0.76 - 0.44) * easedProgress,
  };
}

function makeGalaxyPointCloud() {
  const pointPositions = new Float32Array(GALAXY_POINT_COUNT * 3);
  const pointColors = new Float32Array(GALAXY_POINT_COUNT * 3);
  let seed = 0x5f3759df;
  const random = () => {
    seed = (Math.imul(seed, 1_664_525) + 1_013_904_223) >>> 0;
    return seed / 4_294_967_296;
  };

  for (let index = 0; index < GALAXY_POINT_COUNT; index += 1) {
    const inCentralBar = random() < 0.28;
    let x: number;
    let y: number;
    let radial: number;
    if (inCentralBar) {
      const along = (random() - random()) * 31_000;
      const across = (random() - random()) * (7_500 - Math.abs(along) * 0.12);
      const barAngle = -22 * Math.PI / 180;
      x = along * Math.cos(barAngle) - across * Math.sin(barAngle);
      y = along * Math.sin(barAngle) + across * Math.cos(barAngle);
      radial = Math.min(1, Math.hypot(x, y) / GALAXY_RADIUS_LY);
    } else {
      radial = Math.pow(random(), 0.68);
      const radius = radial * GALAXY_RADIUS_LY;
      const angle = random() * Math.PI * 2;
      x = Math.cos(angle) * radius + (random() - random()) * 1_250;
      y = Math.sin(angle) * radius * 0.72 + (random() - random()) * 900;
    }
    const thickness = (random() - random()) * (1 - radial * 0.8) * 1_150;
    pointPositions.set([
      GALAXY_CENTER.x + x,
      GALAXY_CENTER.z + y,
      thickness,
    ], index * 3);

    const warmth = Math.max(0, 1 - radial * 1.25);
    const brightness = 0.34 + random() * 0.28;
    pointColors.set([
      brightness + warmth * 0.24,
      brightness * 0.7 + warmth * 0.12,
      brightness * 0.54 + (1 - warmth) * 0.16,
    ], index * 3);
  }
  return { positions: pointPositions, colors: pointColors };
}

function makeGalaxyTexture(): THREE.CanvasTexture | null {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  canvas.width = 1_024;
  canvas.height = 1_024;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const centre = 512;

  context.globalCompositeOperation = 'lighter';
  context.save();
  context.translate(centre, centre);
  context.rotate(-22 * Math.PI / 180);
  context.scale(1.9, 0.42);
  const bar = context.createRadialGradient(0, 0, 0, 0, 0, 245);
  bar.addColorStop(0, 'rgba(255, 177, 87, 0.32)');
  bar.addColorStop(0.48, 'rgba(185, 88, 39, 0.13)');
  bar.addColorStop(1, 'rgba(60, 53, 54, 0)');
  context.fillStyle = bar;
  context.fillRect(-260, -260, 520, 520);
  context.restore();

  let cloudSeed = 0xa511e9b3;
  const cloudRandom = () => {
    cloudSeed = (Math.imul(cloudSeed, 1_103_515_245) + 12_345) >>> 0;
    return cloudSeed / 4_294_967_296;
  };
  for (let index = 0; index < 190; index += 1) {
    const progress = Math.pow(cloudRandom(), 0.72);
    const radius = progress * 455;
    const angle = cloudRandom() * Math.PI * 2;
    const x = centre + Math.cos(angle) * radius;
    const y = centre + Math.sin(angle) * radius * 0.72;
    const cloudRadius = 18 + cloudRandom() * 42 * (1 - progress * 0.55);
    const cloud = context.createRadialGradient(x, y, 0, x, y, cloudRadius);
    const alpha = 0.012 + cloudRandom() * 0.018;
    cloud.addColorStop(0, `rgba(224, ${Math.round(120 + progress * 42)}, ${Math.round(82 + progress * 50)}, ${alpha})`);
    cloud.addColorStop(1, 'rgba(58, 66, 82, 0)');
    context.fillStyle = cloud;
    context.fillRect(x - cloudRadius, y - cloudRadius, cloudRadius * 2, cloudRadius * 2);
  }
  context.globalCompositeOperation = 'source-over';

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function makeGalacticCoreGlowTexture(): THREE.CanvasTexture | null {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const centre = canvas.width / 2;
  const glow = context.createRadialGradient(centre, centre, 0, centre, centre, centre);
  glow.addColorStop(0, 'rgba(255, 196, 116, 0.92)');
  glow.addColorStop(0.12, 'rgba(255, 150, 62, 0.58)');
  glow.addColorStop(0.36, 'rgba(190, 86, 31, 0.28)');
  glow.addColorStop(0.68, 'rgba(93, 45, 27, 0.1)');
  glow.addColorStop(1, 'rgba(35, 39, 52, 0)');
  context.fillStyle = glow;
  context.fillRect(0, 0, canvas.width, canvas.height);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

export function GalacticCoreGlow({ spatial, zoom }: { spatial: boolean; zoom: number }) {
  const texture = useMemo(makeGalacticCoreGlowTexture, []);
  const presentation = galacticCoreGlowPresentation(zoom, spatial);
  useEffect(() => () => texture?.dispose(), [texture]);
  if (!texture) return null;
  return <mesh
    position={[
      GALAXY_CENTER.x,
      GALAXY_CENTER.z,
      GALACTIC_CORE_GLOW_HEIGHT_LY,
    ]}
    scale={[presentation.radiusLy, presentation.radiusLy, 1]}
    renderOrder={-2}
  >
    <planeGeometry args={[2, 2]} />
    <meshBasicMaterial
      map={texture}
      transparent
      opacity={presentation.opacity}
      blending={THREE.AdditiveBlending}
      depthTest={false}
      depthWrite={false}
    />
  </mesh>;
}

export function GalaxyBackdrop({ spatial, zoom }: { spatial: boolean; zoom: number }) {
  const galaxy = useMemo(makeGalaxyPointCloud, []);
  const texture = useMemo(makeGalaxyTexture, []);
  useEffect(() => () => texture?.dispose(), [texture]);
  return <group>
    {texture && <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_350]} renderOrder={-5}>
      <planeGeometry args={[GALAXY_RADIUS_LY * 2.08, GALAXY_RADIUS_LY * 1.5]} />
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={spatial ? 0.66 : 0.56}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </mesh>}
    <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_250]} renderOrder={-4}>
      <circleGeometry args={[GALAXY_RADIUS_LY * 1.02, 128]} />
      <meshBasicMaterial color="#1b100b" transparent opacity={spatial ? 0.13 : 0.2} depthWrite={false} />
    </mesh>
    <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_100]} renderOrder={-3}>
      <circleGeometry args={[GALAXY_RADIUS_LY * 0.48, 128]} />
      <meshBasicMaterial color="#48210f" transparent opacity={spatial ? 0.1 : 0.14} depthWrite={false} />
    </mesh>
    <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_000]} renderOrder={-2}>
      <circleGeometry args={[GALAXY_RADIUS_LY * 0.16, 96]} />
      <meshBasicMaterial color="#b45a1b" transparent opacity={spatial ? 0.11 : 0.15} depthWrite={false} />
    </mesh>
    <GalacticCoreGlow spatial={spatial} zoom={zoom} />
    <points renderOrder={-1}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[galaxy.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[galaxy.colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        vertexColors
        size={Math.max(18, zoom * (spatial ? 1.4 : 1.1))}
        sizeAttenuation
        transparent
        opacity={spatial ? 0.44 : 0.34}
        depthWrite={false}
      />
    </points>
  </group>;
}
