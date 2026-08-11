import { useEffect, useMemo } from 'react';
import { makeGlowPointsMaterial, type GlowPointsMaterialOptions } from './glowPointsMaterial';

// Drop-in replacement for <pointsMaterial>: attaches to a <points> the same way,
// rendering each point as a soft round additive glow. The material is created
// once; its uniforms are refreshed from props each render so zoom-driven
// `size`/`opacity` stay live without recreating it.
export type GlowPointsMaterialProps = GlowPointsMaterialOptions;

export function GlowPointsMaterial(props: GlowPointsMaterialProps) {
  const material = useMemo(
    () => makeGlowPointsMaterial({ size: props.size }),
    // Created once; live values are pushed into uniforms below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  material.uniforms.uSize.value = props.size;
  material.uniforms.uAttenuate.value = props.sizeAttenuation ?? true;
  material.uniforms.uUseVertexColor.value = props.vertexColors ?? false;
  material.uniforms.uOpacity.value = props.opacity ?? 1;
  if (props.color != null && !props.vertexColors) {
    material.uniforms.uColor.value.set(props.color);
  }

  useEffect(() => () => material.dispose(), [material]);

  return <primitive object={material} attach="material" />;
}
