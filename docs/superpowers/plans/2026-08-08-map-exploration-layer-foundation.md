# Exploration Layer Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the backend plumbing (table, models, store, API routes) and frontend client for personal exploration data, so a later plan can wire real journal-file parsing and map-layer rendering onto it without any further schema/API changes.

**Architecture:** A new, fully separate domain (`apps/api/src/exploration/`) mirrors the shape of the existing `journal_import/` staging lane — a Pydantic request/response layer, an asyncpg-based store, and a thin FastAPI router — but writes to its own `exploration_facts` table and never touches `journal_import_staging`, `body_scan_facts`, or any canonical-promotion code path. Identity reuses the app's existing anonymous `sync_key` mechanism (`frontend/src/store/syncKeyStore.ts`, already used by journal-import and watchlist/notes) rather than inventing a new one — no new frontend identity code is needed in this plan.

**Tech Stack:** FastAPI + Pydantic v2 + asyncpg (backend, matching `journal_import/`), Vite + React + TypeScript + Vitest (frontend, matching `src/lib/api/`), raw SQL migration (matching `sql/032_journal_import_staging.sql`).

## Global Constraints

- No canonical-truth promotion: `exploration_facts` rows are never merged into `body_scan_facts`, `body_rings`, or any other shared/canonical table. This is a personal-data table only.
- `sync_key` validation must match the existing regex used by `journal_import`: `^[A-Za-z0-9_-]{16,128}$`, with `"legacy"` rejected as reserved.
- Avoid `Optional[dict]` in Pydantic request models per CLAUDE.md's API-contracts rule — use `JsonObject = dict[str, Any]` (the same alias `journal_import/api_models.py` uses).
- `frontend/src/types/api.gen.ts` is auto-generated (`yarn types:gen`) — never hand-edit it. Response types are pulled from it via `Schemas['...']`; request types are hand-authored in `frontend/src/types/api.ts` (matching how `JournalImportRequest` is already done there), since the frontend constructs them before any backend round trip exists to generate from.
- DB changes must be proven against the local `postgres:16-alpine` container before push (`docs/development/windows-dev-environment.md` / CLAUDE.md's DB workflow), not discovered in CI.
- Every step's commands are PowerShell-first per this repo's Windows-primary dev environment; Bash-tool equivalents are noted where the working session uses Git Bash.

---

## Task 1: Roadmap amendment — map as a shared layer substrate

**Files:**
- Modify: `docs/ROADMAP.md`

**Interfaces:** None (docs only).

- [ ] **Step 1: Add the amendment**

Open `docs/ROADMAP.md` and find the "Map posture" bullet inside the `## Current State` section (currently reads: `Map remains a secondary Explore surface, not the primary planning workspace. Stage 26 authorizes a measured desktop replacement of its low-value frontend implementation while preserving that product role.`). Immediately after that bullet, insert a new bullet:

```markdown
- Map layer posture (2026-08-08): the map's typed `MapSceneDescriptor` layer/adapter
  boundary (Stage 26D) is the standing, documented pattern for any Explore-journey
  feature that wants map presence — not a closed list limited to Finder, Compare,
  System Detail, Cluster Search, and Planner hand-off. The first new consumer of
  this pattern is a personal exploration data layer (own design doc:
  `docs/superpowers/specs/2026-08-08-map-exploration-layer-design.md`). This does
  not change "Map remains a secondary Explore surface" or Colony Cockpit's role as
  the sole canonical planning workspace, and does not authorize planner-map fusion.
```

- [ ] **Step 2: Verify the file still reads correctly**

Run (PowerShell):
```powershell
Select-String -Path docs/ROADMAP.md -Pattern "Map layer posture"
```
Expected: one match, the new bullet.

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs: authorize the map's layer boundary as a standing pattern for Explore features"
```

---

## Task 2: `exploration_facts` migration

**Files:**
- Create: `sql/042_exploration_facts.sql`
- Modify: `sql/migration-manifest.txt`

**Interfaces:**
- Produces: table `exploration_facts` with columns `id, sync_key, source, source_record_hash, event_type, system_id64, system_name, body_id, body_name, observed_at, payload_json, created_at`. `source_record_hash` is `UNIQUE` (client-supplied dedupe key, same pattern as `journal_import_staging.source_record_hash`).

- [ ] **Step 1: Write the migration**

Create `sql/042_exploration_facts.sql`:

```sql
-- =============================================================================
-- Personal exploration layer - staging table
-- =============================================================================
-- Additive/idempotent migration. Creates the table backing personal exploration
-- data (systems visited, bodies scanned/mapped, discoveries, exobiology, Codex
-- entries), scoped by the existing anonymous sync_key mechanism. This table is
-- never merged into body_scan_facts, body_rings, or any other canonical table -
-- see docs/superpowers/specs/2026-08-08-map-exploration-layer-design.md.

CREATE TABLE IF NOT EXISTS exploration_facts (
    id                  BIGSERIAL       PRIMARY KEY,
    sync_key            TEXT            NOT NULL,
    source              TEXT            NOT NULL DEFAULT 'journal',
    source_record_hash  TEXT            NOT NULL UNIQUE,
    event_type          TEXT            NOT NULL,
    system_id64         BIGINT          NOT NULL,
    system_name         TEXT            DEFAULT NULL,
    body_id             INTEGER         DEFAULT NULL,
    body_name           TEXT            DEFAULT NULL,
    observed_at         TIMESTAMPTZ     NOT NULL,
    payload_json        JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_exploration_facts_source
        CHECK (source IN ('journal', 'edsm'))
);

CREATE INDEX IF NOT EXISTS idx_exploration_facts_sync_key_observed
    ON exploration_facts (sync_key, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_exploration_facts_sync_key_event_type
    ON exploration_facts (sync_key, event_type);

COMMENT ON TABLE exploration_facts
    IS 'Personal exploration data (visits, scans, mapping, discoveries, exobiology, Codex), scoped by sync_key. Never promoted to canonical/shared tables.';

COMMENT ON COLUMN exploration_facts.source_record_hash
    IS 'Stable client-computed dedupe key for one observation. Re-importing the same journal/EDSM data is a no-op at this layer.';

COMMENT ON COLUMN exploration_facts.source
    IS 'journal = parsed from the player''s own Elite Dangerous journal files. edsm = backfilled from the player''s own EDSM flight log via their personal API key.';
```

- [ ] **Step 2: Register it in the manifest**

Open `sql/migration-manifest.txt` and append a new line:
```
042_exploration_facts.sql
```

- [ ] **Step 3: Apply it to the local disposable Postgres and verify**

Run (PowerShell, from repo root):
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/reset_local_db.ps1 -ConfirmReset
```
Expected: migration `042_exploration_facts.sql` listed as applied, no checksum-ledger errors.

Then verify the table shape directly:
```powershell
docker compose -f docker-compose.local.yml exec -T postgres psql -U edfinder -d edfinder -c "\d exploration_facts"
```
Expected: output listing all 12 columns and the two indexes.

- [ ] **Step 4: Commit**

```bash
git add sql/042_exploration_facts.sql sql/migration-manifest.txt
git commit -m "feat(db): add exploration_facts staging table for personal exploration data"
```

---

## Task 3: Backend Pydantic models

**Files:**
- Create: `apps/api/src/exploration/__init__.py`
- Create: `apps/api/src/exploration/api_models.py`
- Test: `tests/test_exploration_import.py`

**Interfaces:**
- Produces: `ExplorationObservationInput`, `ExplorationImportRequest`, `ExplorationImportSummary`, `ExplorationImportReceipt`, `ExplorationFactRow`, `ExplorationFactsResponse` — all in `edfinder_api.exploration.api_models`. `ALLOWED_EXPLORATION_EVENT_TYPES: set[str]` is also exported from that module.

- [ ] **Step 1: Write the failing test**

Create `tests/test_exploration_import.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from exploration.api_models import (  # noqa: E402
    ALLOWED_EXPLORATION_EVENT_TYPES,
    ExplorationImportRequest,
    ExplorationObservationInput,
)

pytestmark = pytest.mark.unit


def _valid_observation(**overrides: object) -> dict[str, object]:
    base = {
        'observation_key': 'a' * 32,
        'event_type': 'Scan',
        'observed_at': '2026-08-08T09:00:00Z',
        'system_id64': 1000,
        'system_name': 'Test System',
        'body_id': 1,
        'body_name': 'Test System 1',
        'payload': {'BodyName': 'Test System 1'},
    }
    base.update(overrides)
    return base


def test_allowed_event_types_cover_all_six_facets():
    assert ALLOWED_EXPLORATION_EVENT_TYPES == {
        'FSDJump', 'Location', 'Scan', 'FSSDiscoveryScan',
        'SAASignalsFound', 'FSSBodySignals', 'CodexEntry',
    }


def test_observation_rejects_event_type_outside_allowlist():
    with pytest.raises(ValidationError):
        ExplorationObservationInput.model_validate(_valid_observation(event_type='ShipTargeted'))


def test_observation_accepts_naive_datetime_as_utc():
    observation = ExplorationObservationInput.model_validate(
        _valid_observation(observed_at='2026-08-08T09:00:00')
    )
    assert observation.observed_at.tzinfo is not None
    assert observation.observed_at.isoformat() == '2026-08-08T09:00:00+00:00'


def test_request_rejects_legacy_sync_key():
    with pytest.raises(ValidationError):
        ExplorationImportRequest.model_validate({
            'sync_key': 'legacy',
            'observations': [],
        })


def test_request_rejects_short_sync_key():
    with pytest.raises(ValidationError):
        ExplorationImportRequest.model_validate({
            'sync_key': 'tooshort',
            'observations': [],
        })


def test_request_accepts_valid_sync_key_and_defaults_source_to_journal():
    request = ExplorationImportRequest.model_validate({
        'sync_key': 'a' * 32,
        'observations': [_valid_observation()],
    })
    assert request.source == 'journal'
    assert len(request.observations) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_exploration_import.py -v
```
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'exploration'`.

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/exploration/__init__.py` (empty file).

Create `apps/api/src/exploration/api_models.py`:

```python
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

JsonObject = dict[str, Any]
_SYNC_KEY_RE = re.compile(r'^[A-Za-z0-9_-]{16,128}$')

ALLOWED_EXPLORATION_EVENT_TYPES = {
    'FSDJump',
    'Location',
    'Scan',
    'FSSDiscoveryScan',
    'SAASignalsFound',
    'FSSBodySignals',
    'CodexEntry',
}


def _strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ExplorationObservationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    observation_key: str = Field(min_length=16, max_length=128)
    event_type: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    system_id64: int = Field(gt=0)
    system_name: str | None = Field(default=None, max_length=128)
    body_id: int | None = Field(default=None)
    body_name: str | None = Field(default=None, max_length=128)
    payload: JsonObject = Field(default_factory=dict)

    @field_validator('observation_key', 'system_name', 'body_name')
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip_text(value)

    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        stripped = value.strip()
        if stripped not in ALLOWED_EXPLORATION_EVENT_TYPES:
            raise ValueError(f'event_type must be one of {sorted(ALLOWED_EXPLORATION_EVENT_TYPES)}')
        return stripped

    @field_validator('observed_at', mode='before')
    @classmethod
    def validate_observed_at(cls, value: object) -> datetime:
        if isinstance(value, str):
            stripped = value.strip()
            value = datetime.fromisoformat(stripped.replace('Z', '+00:00'))
        if not isinstance(value, datetime):
            raise ValueError('observed_at must be an ISO-8601 timestamp')
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_validator('payload')
    @classmethod
    def validate_payload(cls, value: JsonObject) -> JsonObject:
        if not isinstance(value, dict):
            raise ValueError('payload must be an object')
        return value


class ExplorationImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    sync_key: str = Field(min_length=16, max_length=128)
    source: Literal['journal', 'edsm'] = 'journal'
    observations: list[ExplorationObservationInput] = Field(default_factory=list, max_length=20_000)

    @field_validator('sync_key')
    @classmethod
    def validate_sync_key(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == 'legacy':
            raise ValueError('sync_key="legacy" is reserved for migration')
        if not _SYNC_KEY_RE.match(stripped):
            raise ValueError('sync_key must be 16-128 chars, alphanumeric + "_" or "-" only.')
        return stripped


class ExplorationImportSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    observations_received: int
    observations_staged: int
    duplicates_skipped: int
    event_counts: dict[str, int] = Field(default_factory=dict)


class ExplorationImportReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    sync_key: str
    status: str
    summary: ExplorationImportSummary


class ExplorationFactRow(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_type: str
    system_id64: int
    system_name: str | None = None
    body_id: int | None = None
    body_name: str | None = None
    observed_at: str
    payload: JsonObject = Field(default_factory=dict)


class ExplorationFactsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    sync_key: str
    facts: list[ExplorationFactRow] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_exploration_import.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Lint and commit**

```powershell
.venv\Scripts\python.exe -m ruff check apps/api/src/exploration tests/test_exploration_import.py
```
Expected: no errors.

```bash
git add apps/api/src/exploration/__init__.py apps/api/src/exploration/api_models.py tests/test_exploration_import.py
git commit -m "feat(api): add exploration domain Pydantic models"
```

---

## Task 4: Backend store (`import_exploration_batch`, `get_exploration_facts`)

**Files:**
- Create: `apps/api/src/exploration/store.py`
- Test: `tests/integration/test_exploration_store.py`

**Interfaces:**
- Consumes: `ExplorationImportRequest`, `ExplorationImportReceipt`, `ExplorationFactsResponse` from `edfinder_api.exploration.api_models` (Task 3).
- Produces: `async def import_exploration_batch(pool: asyncpg.Pool, request: ExplorationImportRequest) -> ExplorationImportReceipt`, `async def get_exploration_facts(pool: asyncpg.Pool, sync_key: str, *, limit: int = 5_000) -> ExplorationFactsResponse`, and `class ExplorationImportRateLimitError(RuntimeError)` — all in `edfinder_api.exploration.store`, consumed by Task 5's router.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_exploration_store.py`:

```python
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from exploration.api_models import ExplorationImportRequest  # noqa: E402
from exploration import store  # noqa: E402

pytestmark = pytest.mark.db


def _sync_key() -> str:
    return f'synckey_{uuid4().hex[:24]}'


async def test_import_stages_rows_and_dedupes_on_replay(pool):
    sync_key = _sync_key()
    observation_key = uuid4().hex
    request = ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'source': 'journal',
        'observations': [{
            'observation_key': observation_key,
            'event_type': 'Scan',
            'observed_at': '2026-08-08T09:00:00Z',
            'system_id64': 12345,
            'system_name': 'Store Test System',
            'body_id': 1,
            'body_name': 'Store Test System 1',
            'payload': {'PlanetClass': 'Rocky body'},
        }],
    })

    receipt = await store.import_exploration_batch(pool, request)
    assert receipt.status == 'succeeded'
    assert receipt.summary.observations_staged == 1
    assert receipt.summary.duplicates_skipped == 0

    replay_receipt = await store.import_exploration_batch(pool, request)
    assert replay_receipt.summary.observations_staged == 0
    assert replay_receipt.summary.duplicates_skipped == 1


async def test_get_exploration_facts_returns_only_matching_sync_key(pool):
    sync_key_a = _sync_key()
    sync_key_b = _sync_key()
    for sync_key in (sync_key_a, sync_key_b):
        await store.import_exploration_batch(pool, ExplorationImportRequest.model_validate({
            'sync_key': sync_key,
            'observations': [{
                'observation_key': uuid4().hex,
                'event_type': 'FSDJump',
                'observed_at': '2026-08-08T09:00:00Z',
                'system_id64': 54321,
                'system_name': 'Visited System',
                'payload': {},
            }],
        }))

    facts = await store.get_exploration_facts(pool, sync_key_a)
    assert facts.sync_key == sync_key_a
    assert len(facts.facts) == 1
    assert facts.facts[0].system_id64 == 54321


async def test_import_raises_rate_limit_error_over_daily_budget(pool, monkeypatch):
    monkeypatch.setattr(store, 'MAX_DAILY_ROWS_PER_SYNC_KEY', 1)
    sync_key = _sync_key()
    first = ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'observations': [{
            'observation_key': uuid4().hex,
            'event_type': 'Scan',
            'observed_at': '2026-08-08T09:00:00Z',
            'system_id64': 11111,
            'payload': {},
        }],
    })
    await store.import_exploration_batch(pool, first)

    second = ExplorationImportRequest.model_validate({
        'sync_key': sync_key,
        'observations': [{
            'observation_key': uuid4().hex,
            'event_type': 'Scan',
            'observed_at': '2026-08-08T09:05:00Z',
            'system_id64': 22222,
            'payload': {},
        }],
    })
    with pytest.raises(store.ExplorationImportRateLimitError):
        await store.import_exploration_batch(pool, second)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_exploration_store.py -v
```
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'exploration.store'` (or collection error).

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/exploration/store.py`:

```python
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

import asyncpg

from edfinder_api.exploration.api_models import (
    ExplorationFactRow,
    ExplorationFactsResponse,
    ExplorationImportReceipt,
    ExplorationImportRequest,
    ExplorationImportSummary,
)

MAX_DAILY_ROWS_PER_SYNC_KEY = 50_000
DEFAULT_FACTS_LIMIT = 5_000


class ExplorationImportRateLimitError(RuntimeError):
    """Raised when the bounded exploration-import daily row budget is exceeded."""


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        decoded = json.loads(stripped)
        return dict(decoded) if isinstance(decoded, dict) else {}
    return dict(value)


def _dt_to_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


async def _daily_rows_for_sync_key(conn: asyncpg.Connection, sync_key: str) -> int:
    count = await conn.fetchval(
        '''
        SELECT COUNT(*)
        FROM exploration_facts
        WHERE sync_key = $1
          AND created_at >= (NOW() - INTERVAL '1 day')
        ''',
        sync_key,
    )
    return int(count or 0)


async def import_exploration_batch(
    pool: asyncpg.Pool,
    request: ExplorationImportRequest,
) -> ExplorationImportReceipt:
    event_counts: Counter[str] = Counter(observation.event_type for observation in request.observations)
    rows_read = len(request.observations)
    rows_staged = 0
    rows_skipped = 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            daily_rows_before = await _daily_rows_for_sync_key(conn, request.sync_key)
            if daily_rows_before + rows_read > MAX_DAILY_ROWS_PER_SYNC_KEY:
                raise ExplorationImportRateLimitError(
                    f'Exploration import row budget exceeded for this sync key: '
                    f'{daily_rows_before + rows_read:,} rows in the last 24h '
                    f'(limit {MAX_DAILY_ROWS_PER_SYNC_KEY:,}).'
                )

            for observation in request.observations:
                inserted = await conn.fetchrow(
                    '''
                    INSERT INTO exploration_facts (
                        sync_key, source, source_record_hash, event_type,
                        system_id64, system_name, body_id, body_name,
                        observed_at, payload_json
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9::timestamptz, $10::jsonb
                    )
                    ON CONFLICT (source_record_hash) DO NOTHING
                    RETURNING source_record_hash
                    ''',
                    request.sync_key,
                    request.source,
                    observation.observation_key,
                    observation.event_type,
                    observation.system_id64,
                    observation.system_name,
                    observation.body_id,
                    observation.body_name,
                    observation.observed_at,
                    observation.payload,
                )
                if inserted is None:
                    rows_skipped += 1
                    continue
                rows_staged += 1

    return ExplorationImportReceipt(
        sync_key=request.sync_key,
        status='succeeded',
        summary=ExplorationImportSummary(
            observations_received=rows_read,
            observations_staged=rows_staged,
            duplicates_skipped=rows_skipped,
            event_counts=dict(event_counts),
        ),
    )


async def get_exploration_facts(
    pool: asyncpg.Pool,
    sync_key: str,
    *,
    limit: int = DEFAULT_FACTS_LIMIT,
) -> ExplorationFactsResponse:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT event_type, system_id64, system_name, body_id, body_name, observed_at, payload_json
            FROM exploration_facts
            WHERE sync_key = $1
            ORDER BY observed_at DESC
            LIMIT $2
            ''',
            sync_key,
            limit,
        )

    facts = [
        ExplorationFactRow(
            event_type=str(row['event_type']),
            system_id64=int(row['system_id64']),
            system_name=row['system_name'],
            body_id=row['body_id'],
            body_name=row['body_name'],
            observed_at=_dt_to_str(row['observed_at']) or '',
            payload=_json_object(row['payload_json']),
        )
        for row in rows
    ]
    return ExplorationFactsResponse(sync_key=sync_key, facts=facts)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_exploration_store.py -v -m db
```
Expected: 3 passed. (Requires the local disposable Postgres from Task 2, Step 3 to be running.)

- [ ] **Step 5: Lint and commit**

```powershell
.venv\Scripts\python.exe -m ruff check apps/api/src/exploration/store.py tests/integration/test_exploration_store.py
```
Expected: no errors.

```bash
git add apps/api/src/exploration/store.py tests/integration/test_exploration_store.py
git commit -m "feat(api): add exploration_facts store (import + read), rate-limited per sync_key"
```

---

## Task 5: Router + app wiring

**Files:**
- Create: `apps/api/src/routers/exploration.py`
- Modify: `apps/api/src/main.py`
- Test: `tests/integration/test_exploration_router.py`

**Interfaces:**
- Consumes: `store.import_exploration_batch`, `store.get_exploration_facts`, `store.ExplorationImportRateLimitError` (Task 4); `ExplorationImportRequest`, `ExplorationImportReceipt`, `ExplorationFactsResponse` (Task 3).
- Produces: `POST /api/exploration/import` and `GET /api/exploration/facts/{sync_key}`, consumed by Task 6's frontend client.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_exploration_router.py`:

```python
from __future__ import annotations

from uuid import uuid4


async def test_exploration_import_and_facts_round_trip(client):
    sync_key = f'synckey_{uuid4().hex[:24]}'
    observation_key = uuid4().hex

    import_response = await client.post(
        '/api/exploration/import',
        json={
            'sync_key': sync_key,
            'source': 'journal',
            'observations': [
                {
                    'observation_key': observation_key,
                    'event_type': 'Scan',
                    'observed_at': '2026-08-08T09:00:00Z',
                    'system_id64': 99999,
                    'system_name': 'Router Test System',
                    'body_id': 1,
                    'body_name': 'Router Test System 1',
                    'payload': {'PlanetClass': 'Rocky body'},
                },
            ],
        },
    )
    assert import_response.status_code == 200, import_response.text
    body = import_response.json()
    assert body['sync_key'] == sync_key
    assert body['summary']['observations_staged'] == 1

    facts_response = await client.get(f'/api/exploration/facts/{sync_key}')
    assert facts_response.status_code == 200, facts_response.text
    facts_body = facts_response.json()
    assert facts_body['sync_key'] == sync_key
    assert len(facts_body['facts']) == 1
    assert facts_body['facts'][0]['system_id64'] == 99999


async def test_exploration_import_rejects_invalid_sync_key(client):
    response = await client.post(
        '/api/exploration/import',
        json={'sync_key': 'legacy', 'observations': []},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_exploration_router.py -v
```
Expected: FAIL — 404 Not Found (route doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/routers/exploration.py`:

```python
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request

from edfinder_api.config import limiter
from edfinder_api.deps import get_pool
from edfinder_api.exploration.api_models import (
    ExplorationFactsResponse,
    ExplorationImportReceipt,
    ExplorationImportRequest,
)
from edfinder_api.exploration import store

router = APIRouter(tags=['exploration'])


@router.post('/api/exploration/import', response_model=ExplorationImportReceipt)
@limiter.limit('10/minute')
async def import_exploration(
    request: Request,
    body: ExplorationImportRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ExplorationImportReceipt:
    try:
        return await store.import_exploration_batch(pool, body)
    except store.ExplorationImportRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get('/api/exploration/facts/{sync_key}', response_model=ExplorationFactsResponse)
@limiter.limit('60/minute')
async def get_exploration_facts_for_sync_key(
    request: Request,
    sync_key: str = Path(..., min_length=16, max_length=128),
    pool: asyncpg.Pool = Depends(get_pool),
) -> ExplorationFactsResponse:
    del request
    return await store.get_exploration_facts(pool, sync_key)
```

Modify `apps/api/src/main.py`: find the line `from edfinder_api.routers.journal_import import router as journal_import_router` and add immediately after it:

```python
from edfinder_api.routers.exploration import router as exploration_router
```

Find the line `app.include_router(journal_import_router)` and add immediately after it:

```python
app.include_router(exploration_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_exploration_router.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Full local backend suite + lint, then commit**

```powershell
.venv\Scripts\python.exe -m ruff check apps/api/src/routers/exploration.py apps/api/src/main.py tests/integration/test_exploration_router.py
.venv\Scripts\python.exe -m pytest tests/test_exploration_import.py tests/integration/test_exploration_store.py tests/integration/test_exploration_router.py -v
```
Expected: no lint errors, 11 passed total.

```bash
git add apps/api/src/routers/exploration.py apps/api/src/main.py tests/integration/test_exploration_router.py
git commit -m "feat(api): wire /api/exploration/import and /api/exploration/facts routes"
```

---

## Task 6: Frontend types + API client module

**Files:**
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/lib/api/exploration.ts`
- Modify: `frontend/src/lib/api/index.ts`
- Test: `frontend/src/lib/api.exploration.test.ts`

**Interfaces:**
- Consumes: the live local API from Task 5 (for `yarn types:gen`), and `jsonFetch` from `frontend/src/lib/api/core.ts`.
- Produces: `importExploration(request: ExplorationImportRequest): Promise<ExplorationImportReceipt>` and `getExplorationFacts(syncKey: string): Promise<ExplorationFactsResponse>`, exported from `@/lib/api` (both as `api.importExploration` / `api.getExplorationFacts` and as flat named exports), for a later plan's UI/worker code to call. `useSyncKeyStore` (`frontend/src/store/syncKeyStore.ts`, unchanged) remains the source of the `sync_key` value callers pass in.

- [ ] **Step 1: Regenerate OpenAPI types against the local API**

Start the local API (if not already running from Task 2's DB step):
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_api.ps1 -EnsureServices
```

Then, from `frontend/`:
```powershell
yarn types:gen
```
Expected: `src/types/api.gen.ts` is regenerated and now contains `ExplorationImportReceipt`, `ExplorationImportSummary`, `ExplorationFactRow`, and `ExplorationFactsResponse` under `components['schemas']`. Verify:
```powershell
Select-String -Path src/types/api.gen.ts -Pattern "ExplorationFactsResponse"
```
Expected: at least one match.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/lib/api.exploration.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

describe('exploration API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts observations to /exploration/import', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        sync_key: 'a'.repeat(32),
        status: 'succeeded',
        summary: {
          observations_received: 1,
          observations_staged: 1,
          duplicates_skipped: 0,
          event_counts: { Scan: 1 },
        },
      }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    const receipt = await api.importExploration({
      sync_key: 'a'.repeat(32),
      source: 'journal',
      observations: [{
        observation_key: 'b'.repeat(32),
        event_type: 'Scan',
        observed_at: '2026-08-08T09:00:00Z',
        system_id64: 1000,
        payload: {},
      }],
    });

    expect(receipt.summary.observations_staged).toBe(1);
    const [url, init] = fetchMock.mock.calls[0] as [RequestInfo | URL, RequestInit | undefined];
    expect(String(url)).toContain('/exploration/import');
    expect(init?.method).toBe('POST');
  });

  it('fetches facts by sync key', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => ({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        sync_key: 'a'.repeat(32),
        facts: [],
      }),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);

    const facts = await api.getExplorationFacts('a'.repeat(32));

    expect(facts.sync_key).toBe('a'.repeat(32));
    const [url] = fetchMock.mock.calls[0] as [RequestInfo | URL, RequestInit | undefined];
    expect(String(url)).toContain(`/exploration/facts/${'a'.repeat(32)}`);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `frontend/`):
```powershell
yarn test src/lib/api.exploration.test.ts
```
Expected: FAIL — `api.importExploration is not a function`.

- [ ] **Step 4: Write the implementation**

In `frontend/src/types/api.ts`, find the existing hand-authored `JournalImportRequest` interface (around line 109) and add these new interfaces immediately after its closing brace:

```ts
export interface ExplorationObservationInput {
  observation_key: string;
  event_type:
    | 'FSDJump'
    | 'Location'
    | 'Scan'
    | 'FSSDiscoveryScan'
    | 'SAASignalsFound'
    | 'FSSBodySignals'
    | 'CodexEntry';
  observed_at: string;
  system_id64: number;
  system_name?: string | null;
  body_id?: number | null;
  body_name?: string | null;
  payload: Record<string, unknown>;
}

export interface ExplorationImportRequest {
  sync_key: string;
  source?: 'journal' | 'edsm';
  observations: ExplorationObservationInput[];
}

export type ExplorationImportReceipt = Schemas['ExplorationImportReceipt'];
export type ExplorationFactsResponse = Schemas['ExplorationFactsResponse'];
```

Create `frontend/src/lib/api/exploration.ts`:

```ts
import type {
  ExplorationFactsResponse,
  ExplorationImportReceipt,
  ExplorationImportRequest,
} from '@/types/api';
import { jsonFetch } from './core';

export function importExploration(request: ExplorationImportRequest): Promise<ExplorationImportReceipt> {
  return jsonFetch('/exploration/import', {
    method: 'POST',
    body:   JSON.stringify(request),
  });
}

export function getExplorationFacts(syncKey: string): Promise<ExplorationFactsResponse> {
  return jsonFetch(`/exploration/facts/${encodeURIComponent(syncKey)}`);
}
```

In `frontend/src/lib/api/index.ts`:

1. In the large `import type { ... } from '@/types/api';` block near the top, add these three names in alphabetical position:
```ts
  ExplorationFactsResponse,
  ExplorationImportReceipt,
  ExplorationImportRequest,
```

2. Add the module import next to the existing `import * as planner from './planner';` line:
```ts
import * as exploration from './exploration';
```

3. Inside the `export const api = { ... }` object, add these two lines next to the existing `importJournal: planner.importJournal,` entry:
```ts
  importExploration: exploration.importExploration,
  getExplorationFacts: exploration.getExplorationFacts,
```

4. Add flat convenience exports next to the existing `export function importJournal(...)` block:
```ts
export function importExploration(request: ExplorationImportRequest): Promise<ExplorationImportReceipt> {
  return api.importExploration(request);
}

export function getExplorationFacts(syncKey: string): Promise<ExplorationFactsResponse> {
  return api.getExplorationFacts(syncKey);
}
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `frontend/`):
```powershell
yarn test src/lib/api.exploration.test.ts
```
Expected: 2 passed.

- [ ] **Step 6: Typecheck, lint, and full check, then commit**

```powershell
yarn typecheck
yarn lint
yarn test src/lib/api.exploration.test.ts src/lib/api.observations.test.ts
```
Expected: all clean (the second test file is a spot-check that the `index.ts` edits didn't break an existing sibling module).

```bash
git add frontend/src/types/api.ts frontend/src/types/api.gen.ts frontend/src/lib/api/exploration.ts frontend/src/lib/api/index.ts frontend/src/lib/api.exploration.test.ts
git commit -m "feat(frontend): add exploration API client (importExploration, getExplorationFacts)"
```

---

## Self-Review Notes

- **Spec coverage:** Task 1 covers the roadmap-amendment requirement. Tasks 2-5 cover identity (reusing `sync_key`/`useSyncKeyStore` rather than inventing new code — documented in the Architecture section, no separate task needed), the `exploration_facts` data model (all six event types accepted by the allowlist, ready for any facet), and the "no review/canonical-promotion" decision (no promotion code path exists anywhere in this plan, unlike `journal_import`'s `promote_journal_batch`). Task 6 covers the frontend client boundary. Journal-file parsing (`journalImportWorker.ts` changes), EDSM backfill, and all map-layer/visual work are explicitly out of scope for this plan — they're Plans 2-4 from the design doc's phased roadmap, sequenced after this foundation lands.
- **Placeholder scan:** No TBD/TODO; every step has literal code or exact commands.
- **Type consistency:** `ExplorationImportRequest`/`ExplorationObservationInput`/`ExplorationImportReceipt`/`ExplorationFactsResponse` names match exactly across Task 3 (Pydantic), Task 4 (store signatures), Task 5 (router), and Task 6 (TypeScript) — same field names (`sync_key`, `source`, `observations`, `observation_key`, `event_type`, `observed_at`, `system_id64`, `system_name`, `body_id`, `body_name`, `payload`) throughout, so `yarn types:gen`'s generated shape lines up with the hand-authored request interfaces without renaming.
