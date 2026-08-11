import * as THREE from 'three';

// Soft-glow point material for the map's star layers: renders each GL point as
// a soft round additive glow (radial gl_PointCoord falloff) instead of a flat
// opaque square, so stars read as glowing stars. Dependency-free — a
// hand-written ShaderMaterial, not a postprocessing pass. Deliberately NOT
// applied to the score heatmap (that's a density layer, not stars).
//
// Size handling mirrors THREE.PointsMaterial: with sizeAttenuation the point
// shrinks with view-space depth (the `300.0 / -mv.z` factor approximates
// PointsMaterial's attenuation closely enough for this map's scale).

const VERTEX_SHADER = /* glsl */ `
  uniform float uSize;
  uniform bool uAttenuate;
  attribute vec3 color;
  varying vec3 vColor;
  void main() {
    vColor = color;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = uSize * (uAttenuate ? (300.0 / -mv.z) : 1.0);
    gl_Position = projectionMatrix * mv;
  }
`;

const FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform bool uUseVertexColor;
  uniform float uOpacity;
  varying vec3 vColor;
  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    float alpha = smoothstep(0.5, 0.0, d); // soft round core -> transparent edge
    alpha = pow(alpha, 1.6);               // tighter bright core, wider faint halo
    alpha *= uOpacity;                     // per-layer brightness (keep backdrop subtle)
    if (alpha < 0.01) discard;             // trim the fully-transparent corners
    vec3 c = uUseVertexColor ? vColor : uColor;
    gl_FragColor = vec4(c, alpha);
  }
`;

export interface GlowPointsMaterialOptions {
  /** Flat color for the whole layer (ignored when vertexColors is true). */
  color?: THREE.ColorRepresentation;
  /** Base point size, same units as PointsMaterial.size. */
  size: number;
  /** Shrink points with distance (default true), matching PointsMaterial. */
  sizeAttenuation?: boolean;
  /** Use a per-point `color` buffer attribute instead of the flat color. */
  vertexColors?: boolean;
  /** Overall alpha multiplier (default 1); lower it to keep faint layers subtle. */
  opacity?: number;
}

export function makeGlowPointsMaterial(options: GlowPointsMaterialOptions): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(options.color ?? '#ffffff') },
      uSize: { value: options.size },
      uAttenuate: { value: options.sizeAttenuation ?? true },
      uUseVertexColor: { value: options.vertexColors ?? false },
      uOpacity: { value: options.opacity ?? 1 },
    },
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    depthTest: false,
  });
}
