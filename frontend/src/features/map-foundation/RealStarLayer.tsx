import { useEffect, useMemo, useRef } from 'react';
import { useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { MapViewportSystem } from '@/lib/api';
import { buildRealStarBuffers } from '@/features/map/viewportSystems';
import { GlowPointsMaterial } from './glowPoints';
import { attenuatedPointSize } from './camera';
import { decodeGpuPickColor, encodeGpuPickColor } from './gpuPicking';

export interface RealStarLayerProps {
  systems: MapViewportSystem[];
  zoom: number;
  opacity: number;
  onSelect?: (system: MapViewportSystem) => void;
}

const PICK_VERTEX_SHADER = /* glsl */ `
  uniform float uSize;
  attribute vec3 pickColor;
  varying vec3 vPickColor;
  void main() {
    vPickColor = pickColor;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = max(12.0, uSize * (300.0 / -mv.z));
    gl_Position = projectionMatrix * mv;
  }
`;

const PICK_FRAGMENT_SHADER = /* glsl */ `
  varying vec3 vPickColor;
  void main() {
    if (length(gl_PointCoord - vec2(0.5)) > 0.5) discard;
    gl_FragColor = vec4(vPickColor, 1.0);
  }
`;

// The viewport point cloud stays a single GPU draw call. Selection uses a
// one-pixel, ID-colour render target, avoiding a CPU scan across up to 40K
// points for every click.
export function RealStarLayer({ systems, zoom, opacity, onSelect }: RealStarLayerProps) {
  const { positions, colors } = useMemo(() => buildRealStarBuffers(systems), [systems]);
  useGpuPointPicking(systems, positions, zoom, onSelect);
  if (systems.length === 0) return null;
  return (
    <points renderOrder={13}>
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

function useGpuPointPicking(
  systems: MapViewportSystem[],
  positions: Float32Array,
  zoom: number,
  onSelect: RealStarLayerProps['onSelect'],
) {
  const { camera, gl, size } = useThree();
  const pointerDown = useRef<{ x: number; y: number } | null>(null);
  useEffect(() => {
    if (!onSelect || systems.length === 0 || !(camera instanceof THREE.PerspectiveCamera)) {
      return undefined;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const pickColors = new Float32Array(systems.length * 3);
    systems.forEach((_, index) => pickColors.set(encodeGpuPickColor(index), index * 3));
    geometry.setAttribute('pickColor', new THREE.BufferAttribute(pickColors, 3));
    const material = new THREE.ShaderMaterial({
      uniforms: { uSize: { value: attenuatedPointSize(zoom, 5) } },
      vertexShader: PICK_VERTEX_SHADER,
      fragmentShader: PICK_FRAGMENT_SHADER,
      depthTest: true,
      depthWrite: true,
      toneMapped: false,
    });
    const pickingScene = new THREE.Scene();
    pickingScene.add(new THREE.Points(geometry, material));
    const target = new THREE.WebGLRenderTarget(1, 1, {
      minFilter: THREE.NearestFilter,
      magFilter: THREE.NearestFilter,
      depthBuffer: true,
      stencilBuffer: false,
    });
    target.texture.colorSpace = THREE.NoColorSpace;
    const pixel = new Uint8Array(4);
    const canvas = gl.domElement;

    const down = (event: PointerEvent) => {
      pointerDown.current = { x: event.clientX, y: event.clientY };
    };
    const up = (event: PointerEvent) => {
      const start = pointerDown.current;
      pointerDown.current = null;
      if (!start || Math.hypot(event.clientX - start.x, event.clientY - start.y) > 4) return;
      const rect = canvas.getBoundingClientRect();
      const x = Math.max(0, Math.min(size.width - 1, event.clientX - rect.left));
      const y = Math.max(0, Math.min(size.height - 1, event.clientY - rect.top));
      const previousTarget = gl.getRenderTarget();
      const previousAutoClear = gl.autoClear;
      const previousClearColor = gl.getClearColor(new THREE.Color()).clone();
      const previousClearAlpha = gl.getClearAlpha();
      try {
        camera.setViewOffset(size.width, size.height, Math.floor(x), Math.floor(y), 1, 1);
        camera.updateProjectionMatrix();
        gl.setRenderTarget(target);
        gl.setClearColor(0x000000, 0);
        gl.autoClear = true;
        gl.clear(true, true, true);
        gl.render(pickingScene, camera);
        gl.readRenderTargetPixels(target, 0, 0, 1, 1, pixel);
      } finally {
        camera.clearViewOffset();
        camera.updateProjectionMatrix();
        gl.setRenderTarget(previousTarget);
        gl.setClearColor(previousClearColor, previousClearAlpha);
        gl.autoClear = previousAutoClear;
      }
      const index = decodeGpuPickColor(pixel);
      if (index != null && systems[index]) onSelect(systems[index]);
    };
    canvas.addEventListener('pointerdown', down);
    window.addEventListener('pointerup', up);
    return () => {
      canvas.removeEventListener('pointerdown', down);
      window.removeEventListener('pointerup', up);
      target.dispose();
      material.dispose();
      geometry.dispose();
    };
  }, [camera, gl, onSelect, positions, size.height, size.width, systems, zoom]);
}
