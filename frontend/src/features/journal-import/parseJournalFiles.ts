import type { JournalImportParseResult } from './types';

type ParseSuccess = {
  type: 'parsed';
  result: JournalImportParseResult;
};

type ParseFailure = {
  type: 'error';
  message: string;
};

export async function parseJournalFiles(files: File[]): Promise<JournalImportParseResult> {
  if (files.length === 0) {
    throw new Error('Select at least one journal file first.');
  }

  return new Promise<JournalImportParseResult>((resolve, reject) => {
    const worker = new Worker(new URL('./journalImportWorker.ts', import.meta.url), { type: 'module' });

    worker.onmessage = (event: MessageEvent<ParseSuccess | ParseFailure>) => {
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
