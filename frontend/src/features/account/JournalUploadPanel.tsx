import { useState } from 'react';
import type { DragEvent, InputHTMLAttributes } from 'react';
import { ApiError } from '@/lib/api';
import {
  MAX_V3_UPLOAD_FILES,
  UploadSelectionTooLargeError,
  supportsWebkitDirectory,
  useJournalUpload,
} from './useJournalUpload';

const DROP_EXTENSION_RE = /\.(log|json)$/i;

/**
 * V3 journal upload: choose files or a folder (or drag/drop), live
 * client-side progress, then the server receipt with dedupe counts.
 * Deliberately self-contained: research contribution is a SEPARATE card and
 * is never mentioned here — upload works with consent NONE.
 */
export function JournalUploadPanel() {
  const upload = useJournalUpload();
  const [dragging, setDragging] = useState(false);
  const folderSupported = supportsWebkitDirectory();

  const handleFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    upload.start(Array.from(list));
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (upload.busy) return; // pickers/dropzone are inert while a run is in flight
    const dropped = Array.from(event.dataTransfer?.files ?? [])
      .filter((file) => DROP_EXTENSION_RE.test(file.name));
    if (dropped.length === 0) return;
    upload.start(dropped);
  };

  return (
    <section className="premium-subpanel space-y-4 p-4" data-testid="journal-upload-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-base tracking-[0.12em] text-text">
            Import Elite Dangerous journals
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-silver">
            Choose your local journal files (or a whole journal folder). They are parsed on
            this device into the supported observation events — the raw journal never
            leaves your browser.
          </p>
        </div>
        <span className="premium-toolbar rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-orange-lt">
          Private to your account
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="btn-metal cursor-pointer text-[11px] font-mono">
          Choose journal files
          <input
            type="file"
            accept=".log,.json,.txt"
            multiple
            disabled={upload.busy}
            onChange={(event) => handleFiles(event.target.files)}
            className="sr-only"
            data-testid="journal-upload-file-input"
          />
        </label>
        {folderSupported ? (
          <label className="btn-metal cursor-pointer text-[11px] font-mono">
            Choose journal folder
            <input
              type="file"
              multiple
              disabled={upload.busy}
              onChange={(event) => handleFiles(event.target.files)}
              className="sr-only"
              data-testid="journal-upload-folder-input"
              {...({ webkitdirectory: '' } as InputHTMLAttributes<HTMLInputElement>)}
            />
          </label>
        ) : null}
        <span className="font-mono text-[11px] text-silver-dk" data-testid="journal-upload-caps">
          {MAX_V3_UPLOAD_FILES} files max · 128 MiB per file
        </span>
      </div>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (upload.busy) return;
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        aria-disabled={upload.busy}
        data-testid="journal-upload-dropzone"
        className={[
          'flex min-h-[96px] items-center justify-center rounded-chunk-lg border border-dashed px-4 py-6 text-center text-sm transition-colors',
          dragging ? 'border-orange bg-orange/10 text-orange' : 'border-border/70 bg-bg2/35 text-silver-dk',
          upload.busy ? 'cursor-not-allowed opacity-50' : '',
        ].join(' ')}
      >
        {upload.busy ? 'Import in progress — the pickers are disabled until it finishes.' : 'Drop .log or .json journal files here to import them.'}
      </div>

      {upload.phase !== 'idle' ? (
        <div className="rounded-chunk-lg border border-orange/25 bg-bg3/35 p-3" data-testid="journal-upload-progress">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
            {upload.phase === 'parsing' || upload.phase === 'uploading' ? 'Importing journals' : 'Import receipt'}
          </div>
          {upload.progress ? (
            <p className="mt-2 text-sm text-silver" data-testid="journal-upload-progress-counts">
              Files processed {upload.progress.files_processed}/{upload.progress.files_total} · Events parsed {upload.progress.events_parsed}
            </p>
          ) : null}
          {upload.phase === 'uploading' ? (
            <p className="mt-2 text-sm text-silver">Uploading normalized events...</p>
          ) : null}
        </div>
      ) : null}

      {upload.warnings.length > 0 ? (
        <ul className="space-y-1" data-testid="journal-upload-warnings">
          {upload.warnings.map((warning) => (
            <li key={warning} className="rounded-chunk-sm border border-amber/30 bg-amber/10 px-3 py-2 text-sm text-amber">
              {warning}
            </li>
          ))}
        </ul>
      ) : null}

      {upload.error ? (
        <div className="rounded-chunk-sm border border-red/40 bg-red/10 px-3 py-2 text-sm text-red" data-testid="journal-upload-error">
          {formatUploadError(upload.error)}
        </div>
      ) : null}

      {upload.receipt ? (
        <ReceiptBlock
          eventsInserted={upload.receipt.events_inserted}
          duplicatesSkipped={upload.receipt.duplicates_skipped}
          filesSkipped={upload.receipt.files_skipped}
          privacyStrippedFields={upload.receipt.privacy_stripped_fields}
          eventCounts={upload.receipt.event_counts}
        />
      ) : null}
    </section>
  );
}

function ReceiptBlock({
  eventsInserted,
  duplicatesSkipped,
  filesSkipped,
  privacyStrippedFields,
  eventCounts,
}: {
  eventsInserted: number;
  duplicatesSkipped: number;
  filesSkipped: number;
  privacyStrippedFields: number;
  eventCounts: Record<string, number>;
}) {
  return (
    <div className="rounded-chunk-lg border border-green/35 bg-green/10 p-3" data-testid="journal-upload-receipt">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <ReceiptMetric label="Events inserted" value={eventsInserted} />
        <ReceiptMetric label="Duplicates skipped" value={duplicatesSkipped} />
        <ReceiptMetric label="Privacy-stripped fields" value={privacyStrippedFields} />
        <ReceiptMetric label="Events received" value={Object.values(eventCounts).reduce((sum, count) => sum + count, 0)} />
      </div>
      {filesSkipped > 0 ? (
        <p className="mt-3 text-sm leading-relaxed text-silver" data-testid="journal-upload-files-skipped">
          {filesSkipped === 1 ? '1 file unchanged, skipped' : `${filesSkipped} files unchanged, skipped`} — re-importing
          the same journals adds nothing new.
        </p>
      ) : null}
      {Object.keys(eventCounts).length > 0 ? (
        <p className="mt-3 text-sm leading-relaxed text-silver">
          Event mix: {formatEventCounts(eventCounts)}
        </p>
      ) : null}
    </div>
  );
}

function ReceiptMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-border/50 bg-bg1/55 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="mt-1 text-lg text-text" data-testid={`journal-upload-metric-${label.toLowerCase().replace(/\s+/g, '-')}`}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}

function formatEventCounts(eventCounts: Record<string, number>): string {
  const entries = Object.entries(eventCounts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return 'No supported journal events found yet.';
  return entries.map(([eventType, count]) => `${eventType} ${count}`).join(' | ');
}

function formatUploadError(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    return 'Daily import quota exceeded (429). The server accepts 200,000 events per account per day — try again tomorrow.';
  }
  if (error instanceof UploadSelectionTooLargeError) {
    // Friendly pre-flight copy — deliberately NOT the raw RFC 7807 body.
    return error.message;
  }
  return error instanceof Error ? error.message : 'Journal import failed.';
}
