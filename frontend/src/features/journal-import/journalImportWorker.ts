/// <reference lib="webworker" />

import { parseJournalFilesStreaming } from '@ed-finder/planner-core/journal';
import type { JournalFileSource, JournalImportParseResult } from '@ed-finder/planner-core/journal';

type ParseRequest = {
  type: 'parse';
  files: JournalFileSource[];
};

type ParseSuccess = {
  type: 'parsed';
  result: JournalImportParseResult;
};

type ParseFailure = {
  type: 'error';
  message: string;
};

self.onmessage = (event: MessageEvent<ParseRequest>) => {
  if (event.data?.type !== 'parse') return;
  void parseJournalFilesStreaming(event.data.files)
    .then((result) => {
      const message: ParseSuccess = { type: 'parsed', result };
      self.postMessage(message);
    })
    .catch((error: unknown) => {
      const message: ParseFailure = {
        type: 'error',
        message: error instanceof Error ? error.message : 'Journal parse failed',
      };
      self.postMessage(message);
    });
};

export {};
