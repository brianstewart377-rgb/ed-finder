import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { makeGlowPointsMaterial } from './glowPointsMaterial';

describe('makeGlowPointsMaterial', () => {
  it('is an additive, non-depth-writing transparent points shader', () => {
    const material = makeGlowPointsMaterial({ size: 8 });
    expect(material).toBeInstanceOf(THREE.ShaderMaterial);
    expect(material.blending).toBe(THREE.AdditiveBlending);
    expect(material.depthWrite).toBe(false);
    expect(material.transparent).toBe(true);
    // The soft-glow effect is a radial gl_PointCoord falloff in the fragment shader.
    expect(material.fragmentShader).toContain('gl_PointCoord');
    expect(material.fragmentShader).toContain('smoothstep');
  });

  it('defaults to a flat color with size attenuation on', () => {
    const material = makeGlowPointsMaterial({ size: 5, color: '#ff9a3d' });
    expect(material.uniforms.uUseVertexColor.value).toBe(false);
    expect(material.uniforms.uAttenuate.value).toBe(true);
    expect(material.uniforms.uSize.value).toBe(5);
    expect(material.uniforms.uColor.value).toBeInstanceOf(THREE.Color);
  });

  it('honors vertexColors and disabled attenuation', () => {
    const material = makeGlowPointsMaterial({ size: 12, vertexColors: true, sizeAttenuation: false });
    expect(material.uniforms.uUseVertexColor.value).toBe(true);
    expect(material.uniforms.uAttenuate.value).toBe(false);
    expect(material.uniforms.uSize.value).toBe(12);
  });
});
