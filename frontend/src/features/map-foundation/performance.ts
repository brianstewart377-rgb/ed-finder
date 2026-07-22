import type * as THREE from 'three';

export type FoundationPerformanceMeasurement = {
  frameSampleCount: number;
  frameP95Ms: number;
  frameMaxMs: number;
  gpuTimerSupported: boolean;
  gpuProbeMs: number | null;
  jsHeapBytes: number | null;
};

export type FoundationGpuTimingMeasurement = {
  method: 'EXT_disjoint_timer_query_webgl2';
  timerSupported: boolean;
  requestedSampleCount: number;
  validSampleCount: number;
  discardedDisjointSamples: number;
  medianMs: number | null;
  p95Ms: number | null;
  maxMs: number | null;
  renderer: string | null;
  hardwareAccelerated: boolean | null;
};

export type FoundationGpuTimer = (
  sampleCount?: number,
) => Promise<FoundationGpuTimingMeasurement>;

type TimerQueryExtension = {
  TIME_ELAPSED_EXT: number;
  GPU_DISJOINT_EXT: number;
};

function percentile(values: number[], fraction: number): number {
  if (values.length === 0) return 0;
  const ordered = [...values].sort((left, right) => left - right);
  return ordered[Math.min(ordered.length - 1, Math.floor(ordered.length * fraction))] ?? 0;
}

function rendererLooksHardwareAccelerated(renderer: string | null): boolean | null {
  if (!renderer) return null;
  return !/(swiftshader|llvmpipe|software rasterizer)/i.test(renderer);
}

async function readTimerQuery(
  gl: WebGL2RenderingContext,
  extension: TimerQueryExtension,
  query: WebGLQuery,
): Promise<{ milliseconds: number | null; disjoint: boolean }> {
  gl.flush();
  for (let attempt = 0; attempt < 180; attempt += 1) {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    const available = gl.getQueryParameter(query, gl.QUERY_RESULT_AVAILABLE) as boolean;
    const disjoint = gl.getParameter(extension.GPU_DISJOINT_EXT) as boolean;
    if (available) {
      const nanoseconds = gl.getQueryParameter(query, gl.QUERY_RESULT) as number;
      return {
        milliseconds: !disjoint && Number.isFinite(nanoseconds) ? nanoseconds / 1_000_000 : null,
        disjoint,
      };
    }
  }
  return { milliseconds: null, disjoint: false };
}

export async function measureRendererGpuTiming(
  renderer: THREE.WebGLRenderer,
  scene: THREE.Scene,
  camera: THREE.Camera,
  requestedSampleCount = 30,
): Promise<FoundationGpuTimingMeasurement> {
  const gl = renderer.getContext() as WebGL2RenderingContext;
  const extension = gl.getExtension('EXT_disjoint_timer_query_webgl2') as TimerQueryExtension | null;
  const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
  const rendererName = debugInfo
    ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) as string
    : gl.getParameter(gl.RENDERER) as string | null;
  const base = {
    method: 'EXT_disjoint_timer_query_webgl2' as const,
    requestedSampleCount,
    renderer: rendererName,
    hardwareAccelerated: rendererLooksHardwareAccelerated(rendererName),
  };
  if (!extension) {
    return {
      ...base,
      timerSupported: false,
      validSampleCount: 0,
      discardedDisjointSamples: 0,
      medianMs: null,
      p95Ms: null,
      maxMs: null,
    };
  }

  const samples: number[] = [];
  let discardedDisjointSamples = 0;
  for (let index = 0; index < requestedSampleCount; index += 1) {
    const query = gl.createQuery();
    if (!query) break;
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    gl.beginQuery(extension.TIME_ELAPSED_EXT, query);
    renderer.render(scene, camera);
    gl.endQuery(extension.TIME_ELAPSED_EXT);
    const result = await readTimerQuery(gl, extension, query);
    gl.deleteQuery(query);
    if (result.disjoint) discardedDisjointSamples += 1;
    if (result.milliseconds != null) samples.push(result.milliseconds);
    if (result.milliseconds == null && !result.disjoint) break;
  }

  return {
    ...base,
    timerSupported: true,
    validSampleCount: samples.length,
    discardedDisjointSamples,
    medianMs: samples.length > 0 ? percentile(samples, 0.5) : null,
    p95Ms: samples.length > 0 ? percentile(samples, 0.95) : null,
    maxMs: samples.length > 0 ? Math.max(...samples) : null,
  };
}

async function sampleFrames(sampleCount: number): Promise<number[]> {
  const samples: number[] = [];
  let previous = await new Promise<number>((resolve) => requestAnimationFrame(resolve));
  while (samples.length < sampleCount) {
    const current = await new Promise<number>((resolve) => requestAnimationFrame(resolve));
    samples.push(current - previous);
    previous = current;
  }
  return samples;
}

async function measureGpuProbe(canvas: HTMLCanvasElement): Promise<{ supported: boolean; milliseconds: number | null }> {
  const gl = canvas.getContext('webgl2');
  if (!gl) return { supported: false, milliseconds: null };
  const extension = gl.getExtension('EXT_disjoint_timer_query_webgl2') as TimerQueryExtension | null;
  if (!extension) return { supported: false, milliseconds: null };
  const query = gl.createQuery();
  if (!query) return { supported: true, milliseconds: null };

  gl.beginQuery(extension.TIME_ELAPSED_EXT, query);
  gl.clear(gl.COLOR_BUFFER_BIT);
  gl.endQuery(extension.TIME_ELAPSED_EXT);
  gl.flush();

  for (let attempt = 0; attempt < 180; attempt += 1) {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    const available = gl.getQueryParameter(query, gl.QUERY_RESULT_AVAILABLE) as boolean;
    const disjoint = gl.getParameter(extension.GPU_DISJOINT_EXT) as boolean;
    if (available) {
      const nanoseconds = gl.getQueryParameter(query, gl.QUERY_RESULT) as number;
      gl.deleteQuery(query);
      return {
        supported: true,
        milliseconds: !disjoint && Number.isFinite(nanoseconds) ? nanoseconds / 1_000_000 : null,
      };
    }
  }

  gl.deleteQuery(query);
  return { supported: true, milliseconds: null };
}

export async function measureFoundationPerformance(
  canvas: HTMLCanvasElement,
  frameSampleCount = 60,
): Promise<FoundationPerformanceMeasurement> {
  const frames = await sampleFrames(frameSampleCount);
  const gpu = await measureGpuProbe(canvas);
  const memory = performance as Performance & { memory?: { usedJSHeapSize?: number } };
  return {
    frameSampleCount: frames.length,
    frameP95Ms: percentile(frames, 0.95),
    frameMaxMs: Math.max(...frames),
    gpuTimerSupported: gpu.supported,
    gpuProbeMs: gpu.milliseconds,
    jsHeapBytes: typeof memory.memory?.usedJSHeapSize === 'number' ? memory.memory.usedJSHeapSize : null,
  };
}
