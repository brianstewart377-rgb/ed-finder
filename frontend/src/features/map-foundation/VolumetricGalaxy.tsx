import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo } from 'react';
import * as THREE from 'three';

const vertexShader = `
  precision highp float;

  attribute vec3 position;

  uniform mat4 uProjectionMatrixInverse;
  uniform mat4 uViewMatrixInverse;
  uniform vec3 uCameraPos;

  varying vec3 vRayOrigin;
  varying vec3 vRayDirection;

  void main() {
    // Unproject this full-screen vertex onto the camera's near plane.
    vec4 cameraSpacePosition = uProjectionMatrixInverse
      * vec4(position.xy, -1.0, 1.0);
    vec3 cameraSpaceDirection = cameraSpacePosition.xyz
      / cameraSpacePosition.w;

    // A direction has no translation, hence w = 0. The renderer stores game
    // [X, Y, Z] as Three.js [X, Z, Y], so convert the world ray back to the
    // API/game convention before interpolation and ray marching.
    vec3 renderWorldDirection = (
      uViewMatrixInverse * vec4(cameraSpaceDirection, 0.0)
    ).xyz;
    vRayOrigin = uCameraPos;
    // Keep the ray unnormalised here. Its components are linear across the
    // near plane, so interpolating it over the oversized triangle remains
    // exact; the fragment shader normalises the interpolated result.
    vRayDirection = vec3(
      renderWorldDirection.x,
      renderWorldDirection.z,
      renderWorldDirection.y
    );

    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

const fragmentShader = `
  precision highp float;

  uniform float uOpacity;

  varying vec3 vRayOrigin;
  varying vec3 vRayDirection;

  const float PI = 3.141592653589793;
  const float TWO_PI = 6.283185307179586;

  // All positions and distances below use API/game-world light-years.
  const vec3 GALAXY_CENTER = vec3(25.2, 0.0, 25899.9);
  const float BULGE_RADIUS_LY = 4000.0;
  const float DISK_SCALE_RADIUS_LY = 3000.0;
  const float DISK_SCALE_HEIGHT_LY = 300.0;
  const float SPIRAL_ARM_COUNT = 4.0;
  const float SPIRAL_PITCH_RADIANS = 20.0 * PI / 180.0;

  const float STEP_SIZE_LY = 500.0;
  const int MAX_STEPS = 96;
  const float MARCH_BOUND_RADIUS_LY = 24000.0;

  float bulgeDensity(vec3 worldPosition) {
    float radius = length(worldPosition - GALAXY_CENTER);
    float scaledRadius = radius / BULGE_RADIUS_LY;
    return exp(-0.5 * scaledRadius * scaledRadius);
  }

  float diskDensity(vec3 worldPosition) {
    vec3 relative = worldPosition - GALAXY_CENTER;
    float radialDistance = length(relative.xz);
    float height = abs(relative.y);
    return exp(-radialDistance / DISK_SCALE_RADIUS_LY)
      * exp(-height / DISK_SCALE_HEIGHT_LY);
  }

  float spiralArmDensity(vec3 worldPosition) {
    vec3 relative = worldPosition - GALAXY_CENTER;
    float radialDistance = length(relative.xz);
    float azimuth = atan(relative.z, relative.x);

    // A logarithmic spiral satisfies theta = log(r / r0) / tan(pitch).
    // Folding its phase into one arm period produces exactly four arms.
    float spiralPhase = azimuth
      - log(max(radialDistance, 1.0) / DISK_SCALE_RADIUS_LY)
        / tan(SPIRAL_PITCH_RADIANS);
    float armPeriod = TWO_PI / SPIRAL_ARM_COUNT;
    float distanceToArm = abs(
      mod(spiralPhase + 0.5 * armPeriod, armPeriod) - 0.5 * armPeriod
    );
    float armWidthRadians = 0.18;
    float armMask = exp(
      -0.5 * distanceToArm * distanceToArm
        / (armWidthRadians * armWidthRadians)
    );

    // Keep the arm pattern inside the same physical disk volume.
    return armMask * diskDensity(worldPosition);
  }

  float stellarDensity(vec3 worldPosition) {
    float bulge = bulgeDensity(worldPosition);
    float disk = diskDensity(worldPosition);
    float arms = spiralArmDensity(worldPosition);
    return 0.95 * bulge + 0.35 * disk + 1.1 * arms;
  }

  float dustDensity(vec3 worldPosition) {
    vec3 relative = worldPosition - GALAXY_CENTER;
    float radialDistance = length(relative.xz);
    float height = abs(relative.y);
    float thinDisk = exp(-radialDistance / DISK_SCALE_RADIUS_LY)
      * exp(-height / (DISK_SCALE_HEIGHT_LY * 0.55));
    return thinDisk * (0.25 + 0.75 * spiralArmDensity(worldPosition));
  }

  vec2 intersectMarchBounds(vec3 rayOrigin, vec3 rayDirection) {
    vec3 offset = rayOrigin - GALAXY_CENTER;
    float projectedOffset = dot(offset, rayDirection);
    float discriminant = projectedOffset * projectedOffset
      - dot(offset, offset)
      + MARCH_BOUND_RADIUS_LY * MARCH_BOUND_RADIUS_LY;

    if (discriminant < 0.0) return vec2(-1.0);

    float halfChord = sqrt(discriminant);
    return vec2(
      max(0.0, -projectedOffset - halfChord),
      -projectedOffset + halfChord
    );
  }

  void main() {
    vec3 rayOrigin = vRayOrigin;
    vec3 rayDirection = normalize(vRayDirection);
    vec2 marchBounds = intersectMarchBounds(rayOrigin, rayDirection);

    if (marchBounds.y <= marchBounds.x) {
      gl_FragColor = vec4(0.0);
      return;
    }

    vec3 emission = vec3(0.0);
    float transmittance = 1.0;

    // Skip empty space between the camera and the galaxy, then advance in
    // fixed 500-LY world-space intervals through the bounded volume.
    for (int stepIndex = 0; stepIndex < MAX_STEPS; stepIndex += 1) {
      float rayDistance = marchBounds.x
        + (float(stepIndex) + 0.5) * STEP_SIZE_LY;
      if (rayDistance > marchBounds.y) break;

      vec3 worldPosition = rayOrigin + rayDirection * rayDistance;
      float stars = stellarDensity(worldPosition);
      float dust = dustDensity(worldPosition);
      float radialDistance = length((worldPosition - GALAXY_CENTER).xz);
      float coreWarmth = exp(-radialDistance / 9000.0);
      vec3 stellarColor = mix(
        vec3(0.32, 0.48, 0.90),
        vec3(1.00, 0.55, 0.20),
        coreWarmth
      );

      emission += transmittance * stellarColor * stars * 0.075;
      transmittance *= exp(-dust * 0.11);
      if (transmittance < 0.01) break;
    }

    // AdditiveBlending multiplies RGB by this alpha, making uOpacity the
    // component's single, predictable fade control.
    gl_FragColor = vec4(1.0 - exp(-emission), uOpacity);
  }
`;

export interface VolumetricGalaxyProps {
  opacity?: number;
}

/** World-space volumetric galaxy pass rendered on a full-screen triangle. */
export function VolumetricGalaxy({ opacity = 1 }: VolumetricGalaxyProps) {
  const { camera } = useThree();

  const geometry = useMemo(() => {
    const fullscreenTriangle = new THREE.BufferGeometry();
    fullscreenTriangle.setAttribute('position', new THREE.BufferAttribute(
      new Float32Array([
        -1, -1, 0,
        3, -1, 0,
        -1, 3, 0,
      ]),
      3,
    ));
    return fullscreenTriangle;
  }, []);

  const material = useMemo(() => {
    camera.updateMatrixWorld(true);
    const cameraRenderWorldPosition = new THREE.Vector3()
      .setFromMatrixPosition(camera.matrixWorld);

    return new THREE.RawShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: {
        uProjectionMatrixInverse: {
          value: new THREE.Matrix4().copy(camera.projectionMatrix).invert(),
        },
        uViewMatrixInverse: { value: new THREE.Matrix4().copy(camera.matrixWorld) },
        uCameraPos: {
          value: new THREE.Vector3(
            cameraRenderWorldPosition.x,
            cameraRenderWorldPosition.z,
            cameraRenderWorldPosition.y,
          ),
        },
        // useFrame sets the current prop immediately before each render.
        uOpacity: { value: 1 },
      },
      transparent: true,
      depthTest: false,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
  }, [camera]);

  useEffect(() => () => {
    geometry.dispose();
    material.dispose();
  }, [geometry, material]);

  useFrame(({ camera: frameCamera }) => {
    frameCamera.updateMatrixWorld(true);

    const uniforms = material.uniforms;
    uniforms.uProjectionMatrixInverse.value
      .copy(frameCamera.projectionMatrix)
      .invert();
    uniforms.uViewMatrixInverse.value.copy(frameCamera.matrixWorld);

    const renderWorldPosition = uniforms.uCameraPos.value as THREE.Vector3;
    renderWorldPosition.setFromMatrixPosition(frameCamera.matrixWorld);
    renderWorldPosition.set(
      renderWorldPosition.x,
      renderWorldPosition.z,
      renderWorldPosition.y,
    );
    uniforms.uOpacity.value = opacity;
  });

  return (
    <mesh
      geometry={geometry}
      material={material}
      frustumCulled={false}
      renderOrder={-10}
    />
  );
}
