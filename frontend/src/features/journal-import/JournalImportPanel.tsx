import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { importJournal } from '@/lib/api';
import type { JournalImportReceipt } from '@/types/api';
import { useSyncKeyStore } from '@/store/syncKeyStore';
import { parseJournalFiles } from './parseJournalFiles';
import type { JournalImportParseResult } from './types';

function formatEventCounts(eventCounts: Record<string, number>): string {
  const entries = Object.entries(eventCounts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return 'No allowlisted events found yet.';
  return entries.map(([eventType, count]) => `${eventType} ${count}`).join(' | ');
}

export function JournalImportPanel() {
  const syncKey = useSyncKeyStore((state) => state.syncKey);
  const [files, setFiles] = useState<File[]>([]);
  const [parseResult, setParseResult] = useState<JournalImportParseResult | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [parseBusy, setParseBusy] = useState(false);

  const importMutation = useMutation({
    mutationFn: importJournal,
  });

  const selectionLabel = useMemo(() => {
    if (files.length === 0) return 'No journal files selected yet.';
    return `${files.length} file${files.length === 1 ? '' : 's'} selected`;
  }, [files]);

  const handleFilesSelected = (list: FileList | null) => {
    const nextFiles = list ? Array.from(list) : [];
    setFiles(nextFiles);
    setParseResult(null);
    setParseError(null);
    importMutation.reset();
  };

  const handleParse = async () => {
    setParseBusy(true);
    setParseError(null);
    importMutation.reset();
    try {
      const result = await parseJournalFiles(files);
      setParseResult(result);
    } catch (error) {
      setParseResult(null);
      setParseError(error instanceof Error ? error.message : 'Journal parse failed.');
    } finally {
      setParseBusy(false);
    }
  };

  const handleImport = async () => {
    if (!parseResult || parseResult.observations.length === 0) return;
    await importMutation.mutateAsync({
      sync_key: syncKey,
      client_manifest: parseResult.client_manifest,
      evidence_mode: 'staging_only',
      observations: parseResult.observations,
    });
  };

  return (
    <section className="premium-subpanel space-y-4 p-4" data-testid="journal-import-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-base tracking-[0.12em] text-text">
            Journal Import
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-silver">
            Parse local journal files in your browser, preview the allowlisted observations, and stage evidence without writing directly into canonical data.
          </p>
        </div>
        <span className="premium-toolbar rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan">
          A-1 staging only
        </span>
      </div>

      <div className="rounded-chunk-lg border border-cyan/30 bg-cyan/8 px-3 py-3 text-sm text-cyan">
        Nothing else leaves your machine. The worker strips to an allowlist before upload and sends normalised observations only, scoped to your sync key and staged without opening the canonical evidence lane.
      </div>

      <div className="rounded border border-border/60 bg-bg2/35 px-3 py-2 font-mono text-[11px] text-silver-dk">
        Sync key scope: <span className="text-cyan">{syncKey}</span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="btn-metal cursor-pointer text-[11px] font-mono">
          Select journal files
          <input
            type="file"
            accept=".log,.txt"
            multiple
            onChange={(event) => handleFilesSelected(event.target.files)}
            className="sr-only"
            data-testid="journal-import-file-input"
          />
        </label>
        <button
          type="button"
          onClick={() => void handleParse()}
          disabled={files.length === 0 || parseBusy}
          className="btn-primary text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
          data-testid="journal-import-parse"
        >
          {parseBusy ? 'Parsing journals...' : 'Preview import'}
        </button>
        <button
          type="button"
          onClick={() => void handleImport()}
          disabled={!parseResult || parseResult.observations.length === 0 || importMutation.isPending}
          className="btn-primary text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
          data-testid="journal-import-submit"
        >
          {importMutation.isPending ? 'Staging evidence...' : 'Stage evidence'}
        </button>
        <span className="font-mono text-[11px] text-silver-dk" data-testid="journal-import-selection">
          {selectionLabel}
        </span>
      </div>

      {parseError ? (
        <div className="rounded-chunk-sm border border-red/40 bg-red/10 px-3 py-2 text-sm text-red" data-testid="journal-import-parse-error">
          {parseError}
        </div>
      ) : null}

      {parseResult ? (
        <PreviewPanel result={parseResult} />
      ) : null}

      {importMutation.isError ? (
        <div className="rounded-chunk-sm border border-red/40 bg-red/10 px-3 py-2 text-sm text-red" data-testid="journal-import-submit-error">
          {importMutation.error instanceof Error ? importMutation.error.message : 'Journal import failed.'}
        </div>
      ) : null}

      {importMutation.data ? (
        <ReceiptPanel receipt={importMutation.data} />
      ) : null}
    </section>
  );
}

function PreviewPanel({ result }: { result: JournalImportParseResult }) {
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.9fr)]" data-testid="journal-import-preview">
      <div className="rounded-chunk-lg border border-orange/25 bg-bg3/35 p-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Preview
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Metric label="Files" value={result.preview.files_processed} />
          <Metric label="Lines read" value={result.preview.lines_read} />
          <Metric label="Ready to stage" value={result.preview.observations_ready} />
          <Metric label="Skipped lines" value={result.preview.skipped_lines} />
        </div>
        <p className="mt-3 text-sm leading-relaxed text-silver">
          Parser version <span className="font-mono text-cyan">{result.client_manifest.parser_version}</span>
        </p>
        {result.client_manifest.files.length > 0 ? (
          <div className="mt-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
              Files
            </div>
            <ul className="mt-2 space-y-1 text-sm text-silver" data-testid="journal-import-preview-files">
              {result.client_manifest.files.map((file) => (
                <li key={file.name} className="flex flex-wrap items-center justify-between gap-2 rounded border border-border/40 bg-bg1/40 px-2 py-1">
                  <span className="truncate">{file.name}</span>
                  <span className="font-mono text-[11px] text-silver-dk">{file.event_count} ready</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
      <div className="rounded-chunk-lg border border-border/60 bg-bg2/40 p-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
          Allowlisted event mix
        </div>
        <p className="mt-3 text-sm leading-relaxed text-silver">
          {formatEventCounts(result.preview.event_counts)}
        </p>
      </div>
    </div>
  );
}

function ReceiptPanel({ receipt }: { receipt: JournalImportReceipt }) {
  return (
    <div className="rounded-chunk-lg border border-green/35 bg-green/10 p-3" data-testid="journal-import-receipt">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-green">
          Import receipt
        </span>
        <span className="font-mono text-[11px] text-silver-dk">
          {receipt.run_key}
        </span>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <Metric label="Received" value={receipt.summary.observations_received} />
        <Metric label="Staged" value={receipt.summary.observations_staged} />
        <Metric label="Duplicates" value={receipt.summary.duplicates_skipped} />
      </div>
      <p className="mt-3 text-sm leading-relaxed text-silver">
        Event mix: {formatEventCounts(receipt.summary.event_counts)}
      </p>
      {receipt.files.length > 0 ? (
        <div className="mt-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
            Source files
          </div>
          <ul className="mt-2 space-y-1 text-sm text-silver" data-testid="journal-import-receipt-files">
            {receipt.files.map((file) => (
              <li key={file.name} className="flex flex-wrap items-center justify-between gap-2 rounded border border-green/25 bg-bg1/35 px-2 py-1">
                <span className="truncate">{file.name}</span>
                <span className="font-mono text-[11px] text-silver-dk">{file.event_count} events</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="mt-3 text-sm leading-relaxed text-silver">
        Status {receipt.status}. Canonical data remains untouched in A-1; this run only writes staging plus evidence shelf records.
      </p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-border/50 bg-bg1/55 px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-silver-dk">
        {label}
      </div>
      <div className="mt-1 text-lg text-text">
        {value.toLocaleString()}
      </div>
    </div>
  );
}
