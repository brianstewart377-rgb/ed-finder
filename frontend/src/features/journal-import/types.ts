import type {
  JournalImportClientManifest,
  JournalImportObservationInput,
} from '@/types/api';

export interface JournalImportParseSummary {
  files_processed: number;
  lines_read: number;
  observations_ready: number;
  skipped_lines: number;
  event_counts: Record<string, number>;
}

export interface JournalImportParseResult {
  client_manifest: JournalImportClientManifest;
  observations: JournalImportObservationInput[];
  preview: JournalImportParseSummary;
}
