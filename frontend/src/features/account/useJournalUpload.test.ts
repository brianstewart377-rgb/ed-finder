import { describe, expect, it } from 'vitest';
import type { JournalImportParseResult } from '@/lib/journalParsing';
import {
  MAX_V3_UPLOAD_EVENTS,
  MAX_V3_UPLOAD_FILES,
  UploadSelectionTooLargeError,
  buildV3JournalImportRequest,
  countObservationsWithoutTimestamp,
  countUploadableEvents,
  screenUploadFiles,
} from './useJournalUpload';

function makeFile(name: string, size: number): File {
  return new File([new Uint8Array(Math.min(size, 1024))], name, { type: 'text/plain' });
}

function makeResult(observations: JournalImportParseResult['observations']): JournalImportParseResult {
  return {
    client_manifest: {
      parser_version: 'journal-import-worker-v2',
      files: [{ name: 'Journal.demo.log', event_count: 1 }],
    },
    file_manifest: [{
      name: 'Journal.demo.log',
      content_sha256: 'c'.repeat(64),
      size_bytes: 10,
      event_count: 1,
      line_count: 2,
    }],
    observations,
    powerplay_events: [],
    checkpoints: [],
    preview: {
      files_processed: 1,
      lines_read: 2,
      observations_ready: 1,
      powerplay_events_ready: 0,
      skipped_lines: 0,
      event_counts: { Scan: 1 },
    },
  };
}

describe('screenUploadFiles', () => {
  it('summarizes oversize-file skips instead of emitting one warning per file', () => {
    const big = new File([new Uint8Array(1024)], 'big.log', { type: 'text/plain' });
    Object.defineProperty(big, 'size', { value: 129 * 1024 * 1024 });
    const { accepted, warnings } = screenUploadFiles([
      big,
      big,
      big,
      makeFile('ok.log', 10),
    ]);

    expect(accepted.map((f) => f.name)).toEqual(['ok.log']);
    expect(warnings[0]).toBe('3 files were skipped — larger than the 128 MiB file cap.');
    expect(warnings[1]).toContain('Skipped: big.log, big.log, big.log');
    expect(warnings).toHaveLength(2);
  });

  it('caps the skipped-file name list at 10 entries with an "and N more" tail', () => {
    const big = new File([new Uint8Array(1024)], 'big.log', { type: 'text/plain' });
    Object.defineProperty(big, 'size', { value: 129 * 1024 * 1024 });
    const manyBig = Array.from({ length: 15 }, (_, i) => {
      const file = new File([new Uint8Array(1024)], `big-${i}.log`, { type: 'text/plain' });
      Object.defineProperty(file, 'size', { value: 129 * 1024 * 1024 });
      return file;
    });

    const { warnings } = screenUploadFiles(manyBig);
    expect(warnings[0]).toBe('15 files were skipped — larger than the 128 MiB file cap.');
    expect(warnings[1]).toContain('big-9.log');
    expect(warnings[1]).not.toContain('big-10.log');
    expect(warnings[1]).toContain('and 5 more');
  });

  it('caps the accepted selection at 200 files with a single summary warning', () => {
    const files = Array.from({ length: 250 }, (_, i) => makeFile(`j-${i}.log`, 10));
    const { accepted, warnings } = screenUploadFiles(files);

    expect(accepted).toHaveLength(MAX_V3_UPLOAD_FILES);
    expect(warnings).toEqual([`Only the first ${MAX_V3_UPLOAD_FILES} files will be uploaded (server cap).`]);
  });
});

describe('countUploadableEvents / countObservationsWithoutTimestamp', () => {
  const observation = {
    observation_key: 'k'.repeat(64),
    source_file: 'Journal.demo.log',
    event_type: 'Scan' as const,
    subject_type: 'body' as const,
    summary: 'Body scan observed.',
    payload: {},
    privacy_boundary: {},
  };

  it('counts only timestamped observations as uploadable', () => {
    const result = makeResult([
      { ...observation, observed_at: '2026-08-28T10:00:01Z' },
      { ...observation, observed_at: null },
      { ...observation, observed_at: undefined },
    ]);
    expect(countUploadableEvents(result)).toBe(1);
    expect(countObservationsWithoutTimestamp(result)).toBe(2);
  });
});

describe('UploadSelectionTooLargeError', () => {
  it('carries the event count and friendly copy naming the cap', () => {
    const error = new UploadSelectionTooLargeError(50_001);
    expect(error.eventCount).toBe(50_001);
    expect(error.message).toContain('50,000-event per-upload cap');
    expect(error.message).toContain('50,001');
    expect(error.message).toContain('Split the selection');
    expect(error.message).not.toContain('/v1/journal/imports');
    expect(error.message).not.toContain('"detail"');
  });
});

describe('buildV3JournalImportRequest', () => {
  it('drops observations without a timestamp from the wire request (hook warns with the count)', () => {
    const observation = {
      observation_key: 'k'.repeat(64),
      source_file: 'Journal.demo.log',
      event_type: 'Scan' as const,
      subject_type: 'body' as const,
      summary: 'Body scan observed.',
      payload: { BodyName: 'Demo A' },
      privacy_boundary: {},
    };
    const result = makeResult([
      { ...observation, observed_at: '2026-08-28T10:00:01Z' },
      { ...observation, observation_key: 'j'.repeat(64), observed_at: null },
    ]);

    const request = buildV3JournalImportRequest(result);
    expect(request.events).toHaveLength(1);
    expect(request.events[0]?.source_record_hash).toBe('k'.repeat(64));
    expect(request.files[0]?.first_event_at).toBe('2026-08-28T10:00:01Z');
    expect(request.files[0]?.last_event_at).toBe('2026-08-28T10:00:01Z');
  });
});

describe('MAX_V3_UPLOAD_EVENTS', () => {
  it('matches the server wire-contract cap of 50,000', () => {
    expect(MAX_V3_UPLOAD_EVENTS).toBe(50_000);
  });
});
