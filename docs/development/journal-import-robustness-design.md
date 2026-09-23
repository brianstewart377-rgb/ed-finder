# Journal import robustness — streaming, batched, resumable upload

Status: design approved 2026-09-16. Branch: `feat/journal-import-robustness`.

## Problem

The verified-journal importer assembles the **entire** selection into one
JSON body and performs a **single all-or-nothing POST** to
`/api/v1/journal/verified-imports`. This has three hard ceilings, all of which
a real commander (hundreds of files, millions of events) hits:

1. **nginx returns 413.** `config/nginx.conf` sets no `client_max_body_size`
   on the `/api/` locations (`:106`, `:224`), so nginx's 1 MB default rejects
   the POST before it reaches FastAPI. The only `client_max_body_size` in the
   repo (`25m`, `:332`) is scoped to the unrelated Octopus block.
2. **50,000 events *total* per import** (`import-worker.ts:61`). For a full
   history only the first ~50k events ever upload; the rest are silently held.
   Even with nginx fixed, the whole history can never be imported this way.
3. **One-shot commit.** Any network blip, rate-limit (endpoint is
   `@limiter.limit('5/minute')`), or timeout loses the entire attempt.

A second visible symptom — "nothing shows in contributions even for files that
parsed" — is a *consequence* of (1): parsing is 100% client-side, nothing is
persisted until the POST succeeds, and the 413 throws before persistence, so
no `import_ids` are returned and the galaxy-facts offer step never runs.

## Key facts that make the fix safe (verified in code)

- **Imports are already fully idempotent.** Dedup is content-based:
  per-file `content_sha256` and per-event `source_record_hash`. Each commander
  group commits in its own transaction; retries recover prior receipts
  (`v3_journal.py:380-421`). Re-sending a batch just increments
  `duplicates_skipped`/`files_skipped`. This is what makes chunking safe.
- **`source_record_hash` is computed over the raw journal line before any
  stripping** (`journalParser.ts:223`), so field stripping cannot change it and
  cannot break dedup.
- **Payloads are already minimised.** The EDRE parser applies a frozen
  30-event-type allowlist and a per-event field allowlist *in the browser
  before the network* (`event_contract.py`, `journalParser.ts`); the server
  re-strips to the byte-identical allowlist as defense-in-depth. The documented
  ~50× reduction is already realised. **No new stripping is needed or wanted**
  (residual gain is single-digit %, and touching the allowlist risks dedup,
  projections, galaxy-facts, and the EDRE export). The 413 is pure *volume*,
  not fat payloads.
- The design doc already mandates "normalised observation **batches**"
  (`docs/colonisation-redesign/journal-import-and-colonisation-routing-design-v1.md`
  L57–58); the current one-shot code deviates from that intent. This change
  realigns to it.

## Design

Stream-parse → bounded batches → resumable, retrying upload. Client-side only
plus a rate-limit bump and an nginx directive. No new API endpoints or shapes
(reuses `V3JournalImportRequest` / `V3VerifiedImportReceipt`).

### Components

1. **Worker (`import-worker.ts`)** — parse files one at a time and **stream**
   each file's result out (`{ manifest, events, held }`) with a per-file
   **ack handshake** for backpressure, instead of accumulating one body. Memory
   stays flat regardless of selection size. Removes the 50k-*total* accumulation
   cap; removes the cumulative 64 MiB *total* cap (streaming isn't memory-bound
   by total size). Keeps a generous **per-file** guard (32 MiB raw; a single
   file whose stripped body would exceed the nginx ceiling is held with a clear
   reason). Raises the file-count cap 200 → 2000. Continues to hold files with
   invalid Commander/LoadGame timestamps and unreadable files, as today.

2. **`parse.ts`** — expose the worker as an `AsyncIterable<ParsedFile>` (pull =
   ack next file), so the consumer's upload speed applies natural backpressure.

3. **`uploader.ts` (new, pure, unit-tested)** — consume the `ParsedFile`
   stream and:
   - accumulate whole files into a batch until the next file would exceed
     **`maxBytes` (default 700 KiB serialized — comfortably under the ~1 MB
     nginx/CDN edge body limit that returns 413 before the API; a ~500 KB body
     is verified to pass)**, **`maxEvents` (default 20,000)**, or **`maxFiles`
     (default 200, matching the server's `MAX_FILES_PER_IMPORT`; the server also
     caps events at 50,000/request)**, whichever first;
   - a single file larger than the thresholds is **split into slices that each
     carry the file manifest** (`splitFileForUpload`), so an oversized journal
     session still uploads across several sub-1 MB requests. The
     manifest/`source_file` invariant (`v3_journal.py:366`) holds within each
     slice, and dedup by `source_record_hash` keeps re-sends idempotent;
   - POST each batch via an injected `submit(body, signal)`;
   - **retry** on 429 / 5xx / network with exponential backoff (429 honours
     `Retry-After` when present); **do not** retry other 4xx (e.g. a residual
     413 or a 422) — record those files as failed and continue, because batches
     are independent and idempotent;
   - **aggregate** receipts across batches (union `import_ids`, sum
     `files_admitted` / `files_skipped` / `events_inserted` /
     `duplicates_skipped`, concat `held_files`);
   - report progress and per-batch commits (file `content_sha256` list +
     `import_ids`) so the panel can track completion, drive sharing, and
     **resume** (a retry re-parses only files not yet committed; idempotency
     makes accidental re-sends harmless).

4. **`JournalAccountPanel.svelte`** — wire the streaming pipeline; show batch
   progress ("Uploading batch 3 · 142 files saved"), a resume/retry affordance
   for any failed remainder, and updated copy for the new caps. Sharing reuses
   the existing per-import chunk-and-resume loop over the aggregated
   `import_ids`.

5. **Backend (`v3_journal.py`)** — raise the verified-imports limit
   `5/minute → 30/minute`. Chunked uploads issue more requests; the endpoint is
   authenticated and idempotent, and the client backs off on 429 regardless.

6. **nginx (`config/nginx.conf`)** — `client_max_body_size 32m` on both `/api/`
   locations. NOTE: `config/nginx.conf` is only used by the local
   `docker-compose.yml`; it does **not** govern production. Production serves the
   web image (`apps/web/nginx/default.conf.template`) behind an edge/CDN whose
   ~1 MB default returns the 413, and that edge is gated infra outside
   application code. The **real, deployment-agnostic fix is client-side**:
   batches (and per-file slices) stay under ~1 MB via `maxBytes` (700 KiB
   default), so imports clear the edge limit with no infra change. The local
   nginx allowance just keeps the Review Lab / dev compose from 413ing too.

### Data types (frontend)

```ts
interface HeldItem { name: string; reason: string }
interface ParsedFile {
  manifest: V3JournalFileRef[];  // usually 1; [] when the file is held
  events: V3JournalEventInput[]; // [] when the file is held
  held: HeldItem[];              // per-file hold reasons (may be empty)
}
interface UploadResult {
  receipt: V3VerifiedImportReceipt; // aggregated across batches
  held: HeldItem[];                 // per-file + receipt + failed-batch reasons
  committedShas: string[];          // content_sha256 committed (resume support)
  failed: Array<{ files: string[]; reason: string }>;
}
```

## Testing

- **vitest `uploader.test.ts`** (primary): batch boundary by bytes; boundary by
  event count; oversized single file → own batch; receipt aggregation
  (import_id union + summed counts); 429 → backoff+retry then success; network
  error → retry; non-retryable 4xx → file recorded failed, subsequent batches
  still upload; abort mid-stream leaves remainder resumable; empty/held files
  produce no POST but flow into aggregated held.
- Light integration for the worker→AsyncIterable backpressure (ack handshake).
- Backend: assert the new rate-limit value; existing idempotency tests unchanged.
- nginx config is syntax-tested in CI (per the file's own note).

## Out of scope

- No new stripping (already maximal).
- No server-side resumable-upload session (client idempotent resume suffices).
- No change to galaxy-facts / EDRE export contracts.

## Deploy note

The nginx change and rate-limit bump only take effect on a production deploy via
the current V3 operator path — **not applied here**. This PR delivers the code;
promotion is a separate, authorised step.
