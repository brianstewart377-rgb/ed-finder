import * as THREE from 'three';
import type { BodyThumbnailParams } from './bodyThumbnailParams';

// Renders a small procedural planet/star thumbnail for a body offscreen and
// returns a PNG data-URL, cached per (params, seed, size). One hidden
// WebGLRenderer + sphere/ring is reused for every body. Returns '' when WebGL
// is unavailable (jsdom / headless) so the caller can fall back to a CSS disc.

const PLANET_VERTEX = /* glsl */ `
  varying vec3 vObjNormal;
  varying vec3 vWorldNormal;
  varying vec3 vViewDir;
  void main() {
    vObjNormal = normal;
    vWorldNormal = normalize(mat3(modelMatrix) * normal);
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vViewDir = cameraPosition - wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;

const PLANET_FRAGMENT = /* glsl */ `
  varying vec3 vObjNormal;
  varying vec3 vWorldNormal;
  varying vec3 vViewDir;
  uniform vec3 uBase;
  uniform vec3 uAccent;
  uniform vec3 uAtmo;
  uniform float uContrast;
  uniform float uSeed;
  uniform bool uGas;
  uniform bool uStar;
  uniform bool uAtmoOn;

  float hash(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
  }
  float noise(vec3 x) {
    vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash(i + vec3(0,0,0)), hash(i + vec3(1,0,0)), f.x),
                   mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
                   mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
  }
  float fbm(vec3 p) {
    float v = 0.0; float a = 0.5;
    for (int i = 0; i < 5; i++) { v += a * noise(p); p *= 2.0; a *= 0.5; }
    return v;
  }

  void main() {
    vec3 n = normalize(vObjNormal);
    vec3 sp = n * 2.2 + uSeed;
    float f;
    if (uGas) {
      float bands = sin(n.y * 9.0 + fbm(sp * 1.5) * 3.0);
      f = 0.5 + 0.5 * bands;
    } else {
      f = fbm(sp * 2.6);
    }
    f = clamp((f - 0.5) * uContrast * 2.0 + 0.5, 0.0, 1.0);
    vec3 col = mix(uBase, uAccent, f);

    if (uStar) {
      float gr = fbm(sp * 6.0);
      gl_FragColor = vec4(uBase * (0.82 + 0.34 * gr), 1.0);
      return;
    }

    vec3 L = normalize(vec3(0.6, 0.5, 0.85));
    float diff = clamp(dot(normalize(vWorldNormal), L), 0.0, 1.0);
    col *= 0.15 + 0.95 * diff; // ambient + diffuse -> terminator

    if (uAtmoOn) {
      float fres = pow(1.0 - clamp(dot(normalize(vWorldNormal), normalize(vViewDir)), 0.0, 1.0), 2.5);
      col += uAtmo * fres * (0.35 + 0.65 * diff);
    }
    gl_FragColor = vec4(col, 1.0);
  }
`;

const RING_FRAGMENT = /* glsl */ `
  varying vec2 vUv;
  uniform vec3 uColor;
  void main() {
    float r = length(vUv - 0.5) * 2.0;      // 0 (inner-ish) .. 1 (outer)
    float bands = 0.55 + 0.45 * sin(r * 34.0);
    float gap = smoothstep(0.62, 0.66, r) * (1.0 - smoothstep(0.70, 0.74, r));
    float alpha = bands * (1.0 - gap) * 0.7;
    if (alpha < 0.02) discard;
    gl_FragColor = vec4(uColor, alpha);
  }
`;

const RING_VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

interface Rig {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  group: THREE.Group;
  planet: THREE.Mesh;
  planetMat: THREE.ShaderMaterial;
  ring: THREE.Mesh;
  ringMat: THREE.ShaderMaterial;
  size: number;
}

let rig: Rig | null = null;
let rigFailed = false;
const cache = new Map<string, string>();

function getRig(size: number): Rig | null {
  if (rigFailed) return null;
  if (rig && rig.size === size) return rig;
  try {
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, preserveDrawingBuffer: true });
    renderer.setSize(size, size, false);
    renderer.setClearColor(0x000000, 0);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
    camera.position.set(0, 0.35, 4.4);
    camera.lookAt(0, 0, 0);

    const group = new THREE.Group();
    group.rotation.set(0.42, 0.0, 0.15); // slight 3/4 tilt so rings read as ellipses
    scene.add(group);

    const planetMat = new THREE.ShaderMaterial({
      vertexShader: PLANET_VERTEX,
      fragmentShader: PLANET_FRAGMENT,
      uniforms: {
        uBase: { value: new THREE.Color('#888') },
        uAccent: { value: new THREE.Color('#aaa') },
        uAtmo: { value: new THREE.Color('#88a') },
        uContrast: { value: 0.6 },
        uSeed: { value: 0 },
        uGas: { value: false },
        uStar: { value: false },
        uAtmoOn: { value: false },
      },
    });
    const planet = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 5), planetMat);
    group.add(planet);

    const ringMat = new THREE.ShaderMaterial({
      vertexShader: RING_VERTEX,
      fragmentShader: RING_FRAGMENT,
      uniforms: { uColor: { value: new THREE.Color('#cbb') } },
      transparent: true,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const ring = new THREE.Mesh(new THREE.RingGeometry(1.4, 2.2, 96), ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.visible = false;
    group.add(ring);

    rig = { renderer, scene, camera, group, planet, planetMat, ring, ringMat, size };
    return rig;
  } catch {
    rigFailed = true;
    return null;
  }
}

function cacheKey(p: BodyThumbnailParams, seed: number, size: number): string {
  return [p.kind, p.base, p.accent, p.atmosphereColor, p.gasGiant, p.rings, p.atmosphere, p.contrast, seed, size].join('|');
}

export function renderBodyThumbnail(params: BodyThumbnailParams, seed: number, size = 72): string {
  if (params.kind === 'none') return '';
  const key = cacheKey(params, seed, size);
  const cached = cache.get(key);
  if (cached !== undefined) return cached;

  const r = getRig(size);
  if (!r) {
    cache.set(key, '');
    return '';
  }

  const u = r.planetMat.uniforms;
  u.uBase.value.set(params.base);
  u.uAccent.value.set(params.accent);
  u.uAtmo.value.set(params.atmosphereColor);
  u.uContrast.value = params.contrast;
  u.uSeed.value = (seed % 997) * 0.031;
  u.uGas.value = params.gasGiant;
  u.uStar.value = params.kind === 'star';
  u.uAtmoOn.value = params.atmosphere;

  r.ring.visible = params.rings;
  if (params.rings) r.ringMat.uniforms.uColor.value.set(params.accent);

  try {
    r.renderer.render(r.scene, r.camera);
    const url = r.renderer.domElement.toDataURL('image/png');
    cache.set(key, url);
    return url;
  } catch {
    cache.set(key, '');
    return '';
  }
}

// Stable small seed from a body's id/name so a body always renders the same.
export function seedFromBody(idOrName: string | number | null | undefined): number {
  const s = String(idOrName ?? '');
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
