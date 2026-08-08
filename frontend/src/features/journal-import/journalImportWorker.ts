/// <reference lib="webworker" />

import type { JournalImportObservationInput } from '@/types/api';
import type { JournalImportParseResult } from './types';

type ParseRequest = {
  type: 'parse';
  files: File[];
};

type ParseSuccess = {
  type: 'parsed';
  result: JournalImportParseResult;
};

type ParseFailure = {
  type: 'error';
  message: string;
};

const ALLOWED_EVENT_TYPES = new Set<JournalImportObservationInput['event_type']>([
  'CarrierJump',
  'ColonisationBeaconDeployed',
  'ColonisationConstructionDepot',
  'ColonisationContribution',
  'ColonisationSystemClaim',
  'ColonisationSystemClaimRelease',
  'CompleteConstruction',
  'Docked',
  'FSDJump',
  'FSSAllBodiesFound',
  'FSSBodySignals',
  'FSSDiscoveryScan',
  'Location',
  'SAASignalsFound',
  'Scan',
]);

const PRIVACY_BOUNDARY = {
  strip_before_network: true,
  raw_file_uploaded: false,
  allowlist_only: true,
};

function pickDefined<T extends Record<string, unknown>>(value: T): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined && item !== null));
}

function asPositiveInt(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) return Math.trunc(value);
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed > 0) return Math.trunc(parsed);
  }
  return null;
}

function bodySubjectId(raw: Record<string, unknown>): string | null {
  const bodyId = asPositiveInt(raw.BodyID);
  if (bodyId != null) return String(bodyId);
  if (typeof raw.BodyName === 'string' && raw.BodyName.trim()) return raw.BodyName.trim();
  return null;
}

function summaryForEvent(eventType: JournalImportObservationInput['event_type'], raw: Record<string, unknown>): string {
  switch (eventType) {
    case 'Location':
      return 'Commander location observed from local journal.';
    case 'FSDJump':
      return 'Commander jump observed from local journal.';
    case 'CarrierJump':
      return 'Carrier jump observed from local journal.';
    case 'Docked':
      return `Docked at ${typeof raw.StationName === 'string' ? raw.StationName : 'a station'}.`;
    case 'Scan':
      return `Body scan observed for ${typeof raw.BodyName === 'string' ? raw.BodyName : 'a body'}.`;
    case 'FSSDiscoveryScan':
      return 'Discovery scan observed from local journal.';
    case 'FSSAllBodiesFound':
      return 'All bodies found event observed from local journal.';
    case 'FSSBodySignals':
      return `Body signals observed for ${typeof raw.BodyName === 'string' ? raw.BodyName : 'a body'}.`;
    case 'SAASignalsFound':
      return `Surface signals observed for ${typeof raw.BodyName === 'string' ? raw.BodyName : 'a body'}.`;
    case 'ColonisationSystemClaim':
      return 'Colonisation claim filed for the system.';
    case 'ColonisationSystemClaimRelease':
      return 'Colonisation claim released for the system.';
    case 'ColonisationConstructionDepot':
      return 'Construction depot progress observed from local journal.';
    case 'ColonisationContribution':
      return 'Contribution to a colonisation construction depot observed.';
    case 'ColonisationBeaconDeployed':
      return 'Colonisation beacon deployed.';
    case 'CompleteConstruction':
      return 'Colonisation construction completed.';
  }
}

function payloadForEvent(eventType: JournalImportObservationInput['event_type'], raw: Record<string, unknown>): Record<string, unknown> {
  switch (eventType) {
    case 'Location':
    case 'FSDJump':
    case 'CarrierJump':
      return pickDefined({
        StarSystem: raw.StarSystem,
        SystemAddress: asPositiveInt(raw.SystemAddress),
        StarPos: Array.isArray(raw.StarPos) ? raw.StarPos : undefined,
      });
    case 'Docked':
      return pickDefined({
        StarSystem: raw.StarSystem,
        SystemAddress: asPositiveInt(raw.SystemAddress),
        StationName: raw.StationName,
        StationType: raw.StationType,
        MarketID: asPositiveInt(raw.MarketID),
      });
    case 'Scan':
      return pickDefined({
        StarSystem: raw.StarSystem,
        SystemAddress: asPositiveInt(raw.SystemAddress),
        BodyName: raw.BodyName,
        BodyID: asPositiveInt(raw.BodyID),
        PlanetClass: raw.PlanetClass,
        StarType: raw.StarType,
        Subclass: raw.Subclass,
        TerraformState: raw.TerraformState,
        Landable: raw.Landable,
        DistanceFromArrivalLS: raw.DistanceFromArrivalLS,
      });
    case 'FSSDiscoveryScan':
      return pickDefined({
        StarSystem: raw.StarSystem,
        SystemAddress: asPositiveInt(raw.SystemAddress),
        BodyCount: raw.BodyCount,
        NonBodyCount: raw.NonBodyCount,
      });
    case 'FSSAllBodiesFound':
      return pickDefined({
        StarSystem: raw.StarSystem,
        SystemAddress: asPositiveInt(raw.SystemAddress),
        Count: raw.Count,
      });
    case 'FSSBodySignals':
    case 'SAASignalsFound':
      return pickDefined({
        StarSystem: raw.StarSystem,
        SystemAddress: asPositiveInt(raw.SystemAddress),
        BodyName: raw.BodyName,
        BodyID: asPositiveInt(raw.BodyID),
        Signals: raw.Signals,
        Genuses: raw.Genuses,
      });
    case 'ColonisationSystemClaim':
    case 'ColonisationSystemClaimRelease':
      return pickDefined({
        StarSystem: raw.StarSystem,
        SystemAddress: asPositiveInt(raw.SystemAddress),
      });
    case 'ColonisationConstructionDepot':
      return pickDefined({
        MarketID: asPositiveInt(raw.MarketID),
        ConstructionProgress: raw.ConstructionProgress,
        ConstructionComplete: raw.ConstructionComplete,
        ConstructionFailed: raw.ConstructionFailed,
        ResourcesRequired: Array.isArray(raw.ResourcesRequired) ? raw.ResourcesRequired : undefined,
      });
    case 'ColonisationContribution':
      return pickDefined({
        MarketID: asPositiveInt(raw.MarketID),
        Contributions: Array.isArray(raw.Contributions) ? raw.Contributions : undefined,
      });
    // These two events carry only { timestamp, event } per Frontier's
    // journal schema -- no market, system, or body fields at all. Their
    // system context comes entirely from trackSystemContext's fallback in
    // normaliseObservation below.
    case 'ColonisationBeaconDeployed':
    case 'CompleteConstruction':
      return {};
  }
}

async function sha256Hex(value: string): Promise<string> {
  const cryptoApi = self.crypto?.subtle;
  if (cryptoApi) {
    const digest = await cryptoApi.digest('SHA-256', new TextEncoder().encode(value));
    return Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, '0')).join('');
  }
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return `fallback-${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

type SystemContext = { systemId64: number; systemName: string | null; lastSeenAtMs: number | null };

// ColonisationConstructionDepot, ColonisationContribution,
// ColonisationBeaconDeployed, and CompleteConstruction carry no
// StarSystem/SystemAddress of their own (verified against Frontier's
// journal schema) -- only MarketID, or nothing at all. Every other
// allowlisted event type (including ColonisationSystemClaim/Release) does
// carry its own SystemAddress and must keep using it directly -- the
// carried-context fallback below is deliberately scoped to only these four,
// so a malformed/older event of a normally-self-contained type is still
// dropped rather than silently misattributed to a stale system.
const CONTEXT_LESS_EVENT_TYPES = new Set<JournalImportObservationInput['event_type']>([
  'ColonisationBeaconDeployed',
  'ColonisationConstructionDepot',
  'ColonisationContribution',
  'CompleteConstruction',
]);

// A gap this large between the last tracked system-bearing event and the
// current one means the selected files most likely span more than one play
// session (a different day, a different commander, files picked out of
// order) -- carrying context across that boundary risks silently attributing
// a context-less event to the wrong system entirely.
const SESSION_GAP_RESET_MS = 30 * 60 * 1000;

function extractSystemContext(raw: Record<string, unknown>): { systemId64: number; systemName: string | null } | null {
  const systemId64 = asPositiveInt(raw.SystemAddress);
  if (systemId64 == null) return null;
  return {
    systemId64,
    systemName: typeof raw.StarSystem === 'string' ? raw.StarSystem : null,
  };
}

function eventTimestampMs(raw: Record<string, unknown>): number | null {
  if (typeof raw.timestamp !== 'string') return null;
  const ms = Date.parse(raw.timestamp);
  return Number.isFinite(ms) ? ms : null;
}

async function normaliseObservation(
  raw: Record<string, unknown>,
  sourceFile: string,
  systemContext: { current: SystemContext | null },
): Promise<JournalImportObservationInput | null> {
  const eventTimeMs = eventTimestampMs(raw);

  if (
    systemContext.current?.lastSeenAtMs != null
    && eventTimeMs != null
    && eventTimeMs - systemContext.current.lastSeenAtMs > SESSION_GAP_RESET_MS
  ) {
    systemContext.current = null;
  }

  // Extracted from *every* parsed event, not only allowlisted/staged ones --
  // an intermediate event type this worker never stages (e.g.
  // SupercruiseExit) can still be the most recent true system context for a
  // later context-less Colonisation event.
  const ownContext = extractSystemContext(raw);
  if (ownContext) systemContext.current = { ...ownContext, lastSeenAtMs: eventTimeMs };

  const eventType = typeof raw.event === 'string' ? raw.event : null;
  if (!eventType || !ALLOWED_EVENT_TYPES.has(eventType as JournalImportObservationInput['event_type'])) {
    return null;
  }

  const isContextLess = CONTEXT_LESS_EVENT_TYPES.has(eventType as JournalImportObservationInput['event_type']);
  const resolvedContext = isContextLess ? (ownContext ?? systemContext.current) : ownContext;
  if (!resolvedContext) return null;
  const systemId64 = resolvedContext.systemId64;

  const subjectType: JournalImportObservationInput['subject_type'] =
    eventType === 'Scan' || eventType === 'FSSBodySignals' || eventType === 'SAASignalsFound'
      ? 'body'
      : 'system';
  const subjectId = subjectType === 'body' ? bodySubjectId(raw) : null;
  const payload = payloadForEvent(eventType as JournalImportObservationInput['event_type'], raw);
  const summary = summaryForEvent(eventType as JournalImportObservationInput['event_type'], raw);
  const fingerprint = JSON.stringify({
    eventType,
    sourceFile,
    systemId64,
    subjectType,
    subjectId,
    observedAt: raw.timestamp ?? null,
    payload,
  });

  return {
    observation_key: await sha256Hex(fingerprint),
    source_file: sourceFile,
    event_type: eventType as JournalImportObservationInput['event_type'],
    observed_at: typeof raw.timestamp === 'string' ? raw.timestamp : null,
    system_id64: systemId64,
    system_name: resolvedContext.systemName,
    subject_type: subjectType,
    subject_id: subjectId,
    summary,
    payload,
    privacy_boundary: PRIVACY_BOUNDARY,
  };
}

export async function parseFiles(files: File[]): Promise<JournalImportParseResult> {
  const observations: JournalImportObservationInput[] = [];
  const seenKeys = new Set<string>();
  const eventCounts: Record<string, number> = {};
  const manifestFiles: Array<{ name: string; event_count: number }> = [];
  let linesRead = 0;
  let skippedLines = 0;
  // System context is carried across files, not reset per file: a session
  // can span multiple rotated journal files without a fresh Location event
  // at the start of the next one. That carry-over is only safe if files are
  // processed in chronological order -- Elite Dangerous journal filenames
  // (Journal.<timestamp>.NN.log) sort lexicographically in timestamp order,
  // so sort explicitly rather than trust the order the UI happened to hand
  // over (e.g. a browser file picker's multi-select order is unspecified).
  // SESSION_GAP_RESET_MS above still resets context on a large timestamp
  // gap even within this sorted order, covering a genuinely missing file.
  const sortedFiles = [...files].sort((a, b) => a.name.localeCompare(b.name));
  const systemContext: { current: SystemContext | null } = { current: null };

  for (const file of sortedFiles) {
    const text = await file.text();
    const lines = text.split(/\r?\n/);
    let fileEventCount = 0;
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      linesRead += 1;
      let raw: Record<string, unknown>;
      try {
        raw = JSON.parse(trimmed) as Record<string, unknown>;
      } catch {
        skippedLines += 1;
        continue;
      }
      const observation = await normaliseObservation(raw, file.name, systemContext);
      if (!observation) {
        skippedLines += 1;
        continue;
      }
      if (seenKeys.has(observation.observation_key)) {
        skippedLines += 1;
        continue;
      }
      seenKeys.add(observation.observation_key);
      observations.push(observation);
      fileEventCount += 1;
      eventCounts[observation.event_type] = (eventCounts[observation.event_type] ?? 0) + 1;
    }
    manifestFiles.push({ name: file.name, event_count: fileEventCount });
  }

  return {
    client_manifest: {
      parser_version: 'journal-import-worker-v1',
      files: manifestFiles,
    },
    observations,
    preview: {
      files_processed: files.length,
      lines_read: linesRead,
      observations_ready: observations.length,
      skipped_lines: skippedLines,
      event_counts: eventCounts,
    },
  };
}

self.onmessage = (event: MessageEvent<ParseRequest>) => {
  if (event.data?.type !== 'parse') return;
  void parseFiles(event.data.files)
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
