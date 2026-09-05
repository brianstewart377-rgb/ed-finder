import type {
  JournalImportObservationInput,
  PowerplayJournalEventInput,
} from '@ed-finder/api-client/types';

export interface JournalParserState {
  system_id64: string | null;
  system_name: string | null;
  body_id: string | null;
  body_name: string | null;
  commander: string | null;
  game_version: string | null;
  game_build: string | null;
}

export interface JournalFileCheckpoint {
  version: 1;
  source_file: string;
  source_size: number;
  next_offset: number;
  line_number: number;
  last_record_hash: string | null;
  complete: boolean;
  state: JournalParserState;
}

export interface JournalFileInput {
  file: File;
  /** Byte offset at a previously returned line boundary. */
  offset?: number;
  /** Restores location/session state for events which omit those fields. */
  checkpoint?: JournalFileCheckpoint;
  /** Optional exclusive byte bound, useful for incremental parsing. */
  end_offset?: number;
}

export type JournalFileSource = File | JournalFileInput;

export interface JournalImportParseSummary {
  files_processed: number;
  lines_read: number;
  observations_ready: number;
  skipped_lines: number;
  powerplay_events_ready: number;
  event_counts: Record<string, number>;
}

export interface JournalImportParseResult {
  client_manifest: {
    parser_version: string;
    files: Array<{ name: string; event_count: number }>;
  };
  observations: JournalImportObservationInput[];
  powerplay_events: PowerplayJournalEventInput[];
  preview: JournalImportParseSummary;
  checkpoints: JournalFileCheckpoint[];
}
