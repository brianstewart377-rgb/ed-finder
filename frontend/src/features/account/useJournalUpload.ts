import { useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createV3JournalImport } from '@/lib/api';
import type {
  V3JournalFileRef,
  V3JournalImportReceipt,
  V3JournalImportRequest,
} from '@/lib/api';
import { parseJournalFiles } from '@/features/journal-import/parseJournalFiles';
import type { JournalImportParseResult, JournalParseFileProgress } from '@ed-finder/planner-core/journal';

// Server-side quotas (see the V3 journal plan — Global Constraints).
export const MAX_V3_UPLOAD_FILES = 200;
export const MAX_V3_UPLOAD_FILE_BYTES = 128 * 1024 * 1024; // 128 MiB client-side cap
// V3JournalImportRequest.events max_length (router: MAX_EVENTS_PER_REQUEST).
export const MAX_V3_UPLOAD_EVENTS = 50_000;

export type JournalUploadPhase = 'idle' | 'parsing' | 'uploading' | 'done' | 'error';

/**
 * Raised when a parsed selection has more events than the server accepts in a
 * single request. Chunked uploads are NOT attempted: the server's file-level
 * dedupe admits a file (account, content_sha256) once, and events whose
 * source file was skipped in THAT request are not processed — so repeating
 * the file manifest across chunks would silently drop every later chunk.
 * The honest fallback is this friendly pre-flight error (no RFC 7807 body).
 */
export class UploadSelectionTooLargeError extends Error {
  constructor(public readonly eventCount: number) {
    super(
      `This selection has ${eventCount.toLocaleString()} journal events — more than the ` +
        `${MAX_V3_UPLOAD_EVENTS.toLocaleString()}-event per-upload cap. Split the selection ` +
        '(for example, import a shorter date range of journal files) and import again.',
    );
    this.name = 'UploadSelectionTooLargeError';
  }
}

/** Observations that would actually go on the wire (V3 requires a timestamp). */
export function countUploadableEvents(result: JournalImportParseResult): number {
  return result.observations.filter((observation) => observation.observed_at).length;
}

/** Observations the wire request must drop because they lack `observed_at`. */
export function countObservationsWithoutTimestamp(result: JournalImportParseResult): number {
  return result.observations.length - countUploadableEvents(result);
}

export interface JournalUploadProgress {
  files_processed: number;
  files_total: number;
  events_parsed: number;
}

/**
 * Browser support probe for the `webkitdirectory` folder picker. jsdom and
 * some browsers do not implement it — the folder control is hidden then
 * (feature-detect, per the plan's UX contract).
 */
export function supportsWebkitDirectory(): boolean {
  return typeof document !== 'undefined' && 'webkitdirectory' in document.createElement('input');
}

/**
 * V3 journal upload flow: select files → parse in the streaming worker
 * (live per-file progress) → POST normalized events to /api/v1/journal/imports
 * → server receipt. Consent is NEVER part of this flow: upload works with
 * consent NONE and this hook never mentions research contribution.
 */
export function useJournalUpload() {
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<JournalUploadPhase>('idle');
  const [progress, setProgress] = useState<JournalUploadProgress | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  // Synchronous in-flight guard: `phase` is async state, so two `start` calls
  // in the same tick must still not double-parse/double-upload.
  const inFlightRef = useRef(false);
  const busy = phase === 'parsing' || phase === 'uploading';

  const mutation = useMutation({
    mutationFn: async (files: File[]): Promise<V3JournalImportReceipt> => {
      const { accepted, warnings: selectionWarnings } = screenUploadFiles(files);
      setWarnings(selectionWarnings);
      setProgress(null);
      setPhase('parsing');
      const result = await parseJournalFiles(accepted, (update: JournalParseFileProgress) => {
        setProgress(update);
      });
      if (result.observations.length === 0) {
        setWarnings((current) => [
          ...current,
          'No supported journal events were found in the selected files.',
        ]);
      }
      const droppedWithoutTimestamp = countObservationsWithoutTimestamp(result);
      if (droppedWithoutTimestamp > 0) {
        setWarnings((current) => [
          ...current,
          `${droppedWithoutTimestamp} observation${droppedWithoutTimestamp === 1 ? '' : 's'} ` +
            `without a timestamp ${droppedWithoutTimestamp === 1 ? 'was' : 'were'} not uploaded — ` +
            'every uploaded event needs an event timestamp.',
        ]);
      }
      const uploadable = countUploadableEvents(result);
      if (uploadable > MAX_V3_UPLOAD_EVENTS) {
        // Pre-flight cap check: never send a request the server must reject
        // with 422 — see UploadSelectionTooLargeError for why not chunked.
        throw new UploadSelectionTooLargeError(uploadable);
      }
      setPhase('uploading');
      return createV3JournalImport(buildV3JournalImportRequest(result));
    },
    onSuccess: () => {
      setPhase('done');
      // The personal projections change with every import.
      void queryClient.invalidateQueries({ queryKey: ['v3-journal', 'summary'] });
    },
    onError: () => {
      setPhase('error');
    },
    onSettled: () => {
      inFlightRef.current = false;
    },
  });

  return {
    phase,
    busy,
    progress,
    warnings,
    receipt: mutation.data ?? null,
    error: mutation.error ?? null,
    start: (files: File[]) => {
      // Re-entrancy guard: ignore a start while a parse/upload is in flight.
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      mutation.mutate(files);
    },
    reset: () => {
      inFlightRef.current = false;
      mutation.reset();
      setPhase('idle');
      setProgress(null);
      setWarnings([]);
    },
  };
}

/**
 * Client-side quota screening: reject files over the 128 MiB cap and cap the
 * selection at 200 files (matching the server quotas). Warnings are surfaced
 * in the panel as a SUMMARY plus a capped name list — a per-file line per
 * oversize file would otherwise grow to the 200-file cap; accepted files
 * still upload normally.
 */
export function screenUploadFiles(files: File[]): { accepted: File[]; warnings: string[] } {
  const warnings: string[] = [];
  const overSize = files.filter((file) => file.size > MAX_V3_UPLOAD_FILE_BYTES);
  if (overSize.length > 0) {
    const verb = overSize.length === 1 ? 'file was' : 'files were';
    warnings.push(`${overSize.length} ${verb} skipped — larger than the 128 MiB file cap.`);
    const MAX_WARNING_NAMES = 10;
    const detailNames = overSize.slice(0, MAX_WARNING_NAMES).map((file) => file.name).join(', ');
    const extra = overSize.length > MAX_WARNING_NAMES ? ` and ${overSize.length - MAX_WARNING_NAMES} more` : '';
    warnings.push(`Skipped: ${detailNames}${extra}`);
  }
  let accepted = files.filter((file) => file.size <= MAX_V3_UPLOAD_FILE_BYTES);
  if (accepted.length > MAX_V3_UPLOAD_FILES) {
    warnings.push(`Only the first ${MAX_V3_UPLOAD_FILES} files will be uploaded (server cap).`);
    accepted = accepted.slice(0, MAX_V3_UPLOAD_FILES);
  }
  return { accepted, warnings };
}

/**
 * Build the V3 wire request from a parse result. `source_record_hash` is the
 * per-line SHA-256 the parser already computes (observation_key); per-file
 * first/last event timestamps come from the observations of that file.
 */
export function buildV3JournalImportRequest(result: JournalImportParseResult): V3JournalImportRequest {
  const events: V3JournalImportRequest['events'] = [];
  for (const observation of result.observations) {
    if (!observation.observed_at) continue; // V3 wire contract requires a timestamp
    events.push({
      event_type: observation.event_type,
      event_timestamp: observation.observed_at,
      source_record_hash: observation.observation_key,
      source_file: observation.source_file,
      source_offset: observation.source_offset ?? 0,
      payload: observation.payload,
    });
  }

  const files: V3JournalFileRef[] = result.file_manifest.map((entry) => {
    let firstEventAt: string | null = null;
    let lastEventAt: string | null = null;
    for (const observation of result.observations) {
      if (observation.source_file !== entry.name || !observation.observed_at) continue;
      if (firstEventAt == null || observation.observed_at < firstEventAt) firstEventAt = observation.observed_at;
      if (lastEventAt == null || observation.observed_at > lastEventAt) lastEventAt = observation.observed_at;
    }
    return {
      name: entry.name,
      content_sha256: entry.content_sha256,
      size_bytes: entry.size_bytes,
      line_count: entry.line_count,
      event_count: entry.event_count,
      first_event_at: firstEventAt,
      last_event_at: lastEventAt,
    };
  });

  return {
    parser_version: result.client_manifest.parser_version,
    files,
    events,
  };
}
