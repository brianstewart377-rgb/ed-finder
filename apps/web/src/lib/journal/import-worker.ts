import { parseJournalFilesStreaming } from '@ed-finder/planner-core/journal';
import type { V3JournalImportRequest } from '$lib/api/client';

self.onmessage = async (message: MessageEvent<{ files: File[] }>) => {
  const files = message.data.files;
  const body: V3JournalImportRequest = {
    parser_version: 'journal-import-worker-v3',
    files: [],
    events: [],
  };
  const held: Array<{ name: string; reason: string }> = [];
  let bytes = 0;
  try {
    for (const file of files.slice(0, 200)) {
      if (
        file.size > 16 * 1024 * 1024 ||
        bytes + file.size > 64 * 1024 * 1024
      ) {
        held.push({
          name: file.name,
          reason: 'File or selection exceeds this importer’s size limit',
        });
        continue;
      }
      bytes += file.size;
      try {
        // Parsing separately prevents cross-file line dedupe from removing an
        // identity header. The server owns account/commander semantic dedupe.
        const parsed = await parseJournalFilesStreaming([file]);
        const events = parsed.observations
          .filter(
            (row) =>
              row.observed_at && Number.isFinite(Date.parse(row.observed_at)),
          )
          .map((row) => ({
            event_type: row.event_type,
            event_timestamp: row.observed_at!,
            source_record_hash: row.observation_key,
            source_file: row.source_file,
            source_offset: row.source_offset ?? 0,
            payload: row.payload,
          }));
        if (
          !events.length ||
          (body.events?.length ?? 0) + events.length > 50_000
        ) {
          held.push({
            name: file.name,
            reason: events.length
              ? 'Selection exceeds 50,000 events; import this file separately'
              : 'No supported events with valid timestamps',
          });
          continue;
        }
        body.files.push(...parsed.file_manifest);
        body.events!.push(...events);
        if (parsed.preview.skipped_lines)
          held.push({
            name: file.name,
            reason: `${parsed.preview.skipped_lines} malformed, duplicate or unsupported lines skipped; valid records retained`,
          });
        self.postMessage({ type: 'progress', count: body.files.length });
      } catch {
        held.push({
          name: file.name,
          reason: 'Could not read this file; other files can continue',
        });
      }
    }
    for (const file of files.slice(200))
      held.push({
        name: file.name,
        reason: 'Select up to 200 files per import',
      });
    self.postMessage({ type: 'parsed', body, held });
  } catch {
    self.postMessage({
      type: 'error',
      message: 'Journal parsing stopped; no upload was sent',
    });
  }
};
