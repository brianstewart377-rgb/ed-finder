import { useEffect, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * Volumetric galaxy rendering: emissive volume + dust extinction pass.
 *
 * Implements the research recommendation (Pass B):
 * - Render to half-resolution target
 * - March through flattened cylinder volume
 * - Accumulate emission (star density) and transmittance (dust)
 * - Composite result with proper blending
 */
export function VolumetricGalaxy({
  opacity = 1,
}: {
  opacity?: number;
}) {
  const { gl, scene, camera, size } = useThree();
  const targetRef = useRef<THREE.WebGLRenderTarget | null>(null);
  const quadRef = useRef<THREE.Mesh | null>(null);

  // Initialize render target and materials
  useEffect(() => {
    // Half-resolution render target for performance
    const target = new THREE.WebGLRenderTarget(
      Math.floor(size.width / 2),
      Math.floor(size.height / 2),
      {
        format: THREE.RGBAFormat,
        type: THREE.FloatType,
        minFilter: THREE.LinearFilter,
        magFilter: THREE.LinearFilter,
      },
    );
    targetRef.current = target;

    // Volumetric shader material
    const material = new THREE.RawShaderMaterial({
      uniforms: {
        uViewMatrix: { value: camera.matrixWorldInverse },
        uProjectionMatrix: { value: camera.projectionMatrix },
        uCameraPos: { value: camera.position },
        uTime: { value: 0 },
        uOpacity: { value: opacity },
        uResolution: { value: new THREE.Vector2(size.width, size.height) },
      },
      vertexShader: `
        precision highp float;

        attribute vec3 position;

        void main() {
          gl_Position = vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        precision highp float;

        uniform mat4 uViewMatrix;
        uniform mat4 uProjectionMatrix;
        uniform vec3 uCameraPos;
        uniform float uTime;
        uniform float uOpacity;
        uniform vec2 uResolution;

        // Density functions from research
        float bulgeProfile(float R) {
          const float bulgeK = 0.5;
          const float bulgeRadius = 0.15;
          const float bulgeHeight = 0.5;
          return exp(-bulgeK * pow(R / bulgeRadius, 0.25)) * exp(-bulgeHeight);
        }

        float diskProfile(float R, float y) {
          const float diskScale = 0.35;
          const float diskHeight = 0.02;
          return exp(-R / diskScale) * exp(-0.5 * (y / diskHeight) * (y / diskHeight));
        }

        float armProfile(float R, float theta) {
          const float armCount = 4.0;
          const float pitch = 0.25;
          const float armWidth = 0.05;

          float thetaArm = atan(theta, 1.0) + log(max(R, 0.1)) / tan(pitch) + 2.0 * 3.14159 / armCount;
          float armDist = abs(R * (theta - thetaArm));
          return exp(-0.5 * (armDist / armWidth) * (armDist / armWidth));
        }

        float densityStars(vec3 pos) {
          float R = length(pos.xz);
          float bulge = bulgeProfile(R);
          float disk = diskProfile(R, pos.y);
          float arm = armProfile(R, atan(pos.z, pos.x));

          float density = bulge + disk * (0.3 + 0.7 * arm);
          return density;
        }

        float densityDust(vec3 pos) {
          float R = length(pos.xz);
          float arm = armProfile(R, atan(pos.z, pos.x));

          const float dustBase = 0.1;
          const float dustHeight = 0.008;
          float dust = exp(-R / 0.35) * (dustBase + 0.9 * arm) * exp(-0.5 * (pos.y / dustHeight) * (pos.y / dustHeight));
          return dust;
        }

        void main() {
          // Normalized screen coordinates (0 to 1)
          vec2 uv = gl_FragCoord.xy / uResolution;

          // Ray direction from camera through screen pixel
          vec3 rayDir = normalize(vec3(uv - 0.5, 1.0));
          vec3 rayPos = uCameraPos;

          vec3 color = vec3(0.0);
          float transmittance = 1.0;
          float stepSize = 0.1;

          for (int i = 0; i < 24; i++) {
            float rho = densityStars(rayPos);
            float dust = densityDust(rayPos);

            // Emission: star field color based on density
            vec3 starColor = mix(vec3(0.8, 0.7, 1.0), vec3(1.0, 0.9, 0.5), rho);
            color += transmittance * starColor * rho * stepSize;

            // Extinction: dust absorption
            transmittance *= exp(-dust * 0.1 * stepSize);

            rayPos += rayDir * stepSize;
          }

          gl_FragColor = vec4(color * uOpacity, transmittance);
        }
      `,
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
    });

    // Full-screen quad
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array([
      -1, -1, 0,
      3, -1, 0,
      -1, 3, 0,
    ]);
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const quad = new THREE.Mesh(geometry, material);
    quad.frustumCulled = false;
    scene.add(quad);
    quadRef.current = quad;

    return () => {
      target.dispose();
      geometry.dispose();
      material.dispose();
      scene.remove(quad);
    };
  }, [gl, scene, camera, size]);

  // Update shader uniforms each frame
  useFrame(({ camera: cam, clock, size: frameSize }) => {
    if (quadRef.current && quadRef.current.material instanceof THREE.RawShaderMaterial) {
      quadRef.current.material.uniforms.uCameraPos.value.copy(cam.position);
      quadRef.current.material.uniforms.uTime.value = clock.elapsedTime;
      quadRef.current.material.uniforms.uOpacity.value = opacity;
      quadRef.current.material.uniforms.uResolution.value.set(frameSize.width, frameSize.height);
    }
  });

  return null;
}
