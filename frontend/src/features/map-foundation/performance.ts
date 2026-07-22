export type FoundationPerformanceMeasurement = {
  frameSampleCount: number;
  frameP95Ms: number;
  frameMaxMs: number;
  gpuTimerSupported: boolean;
  gpuProbeMs: number | null;
  jsHeapBytes: number | null;
};

type TimerQueryExtension = {
  TIME_ELAPSED_EXT: number;
  GPU_DISJOINT_EXT: number;
};

function percentile(values: number[], fraction: number): number {
  if (values.length === 0) return 0;
  const ordered = [...values].sort((left, right) => left - right);
  return ordered[Math.min(ordered.length - 1, Math.floor(ordered.length * fraction))] ?? 0;
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
