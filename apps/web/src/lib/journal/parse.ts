import type { V3JournalImportRequest } from '$lib/api/client';

export interface ParsedImport {
  body: V3JournalImportRequest;
  held: Array<{ name: string; reason: string }>;
}

export function parseJournals(
  files: File[],
  signal: AbortSignal,
  progress: (count: number) => void,
): Promise<ParsedImport> {
  return new Promise((resolve, reject) => {
    if (signal.aborted)
      return reject(new DOMException('Cancelled', 'AbortError'));
    const worker = new Worker(new URL('./import-worker.ts', import.meta.url), {
      type: 'module',
    });
    const stop = () => {
      worker.terminate();
      signal.removeEventListener('abort', cancel);
    };
    const cancel = () => {
      stop();
      reject(new DOMException('Cancelled', 'AbortError'));
    };
    signal.addEventListener('abort', cancel, { once: true });
    worker.onmessage = (event) => {
      if (event.data.type === 'progress') return progress(event.data.count);
      stop();
      if (event.data.type === 'parsed') resolve(event.data);
      else reject(new Error(event.data.message));
    };
    worker.onerror = () => {
      stop();
      reject(new Error('Journal parsing failed'));
    };
    worker.postMessage({ files });
  });
}
