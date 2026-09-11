import type {
  JournalFileSource,
  JournalImportParseResult,
  JournalParseFileProgress,
} from '@ed-finder/planner-core/journal';

type ParseSuccess = {
  type: 'parsed';
  result: JournalImportParseResult;
};

type ParseFailure = {
  type: 'error';
  message: string;
};

type ParseProgress = {
  type: 'progress';
  progress: JournalParseFileProgress;
};

/**
 * Parse journal files in the streaming Web Worker. `onProgress` receives a
 * live per-file progress update (files processed / events parsed) while the
 * worker is still running; the returned promise resolves with the final
 * parse result (including the V3 `file_manifest` with per-file SHA-256).
 */
export async function parseJournalFiles(
  files: JournalFileSource[],
  onProgress?: (progress: JournalParseFileProgress) => void,
): Promise<JournalImportParseResult> {
  if (files.length === 0) {
    throw new Error('Select at least one journal file first.');
  }

  return new Promise<JournalImportParseResult>((resolve, reject) => {
    const worker = new Worker(new URL('./journalImportWorker.ts', import.meta.url), { type: 'module' });

    worker.onmessage = (event: MessageEvent<ParseSuccess | ParseFailure | ParseProgress>) => {
      if (event.data.type === 'progress') {
        onProgress?.(event.data.progress);
        return;
      }
      worker.terminate();
      if (event.data.type === 'parsed') {
        resolve(event.data.result);
        return;
      }
      reject(new Error(event.data.message));
    };

    worker.onerror = (event) => {
      worker.terminate();
      reject(new Error(event.message || 'Journal parse worker failed.'));
    };

    worker.postMessage({ type: 'parse', files });
  });
}
