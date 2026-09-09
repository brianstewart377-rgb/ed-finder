from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException, Response
from starlette.requests import Request

from tests.helpers import db_isolation

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'http://testserver')
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from edfinder_api.auth import load_session, token_digest  # noqa: E402
from edfinder_api.config import settings  # noqa: E402
from edfinder_api.routers import auth as auth_router  # noqa: E402


def _request(
    *,
    origin: str = 'http://testserver',
    cookie: str = '',
) -> Request:
    headers = [
        (b'host', b'testserver'),
        (b'origin', origin.encode('ascii')),
    ]
    if cookie:
        headers.append((b'cookie', cookie.encode('ascii')))
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': '/api/v1/auth/owner/claim',
        'headers': headers,
        'query_string': b'',
        'server': ('testserver', 80),
        'client': ('127.0.0.1', 1234),
        'scheme': 'http',
    })


@pytest_asyncio.fixture
async def v3_auth_pool():
    if os.environ.get('EDFINDER_V3_IDENTITY_TEST_DATABASE') != 'yes':
        pytest.skip(
            'V3 auth PostgreSQL checks require '
            'EDFINDER_V3_IDENTITY_TEST_DATABASE=yes',
        )
    try:
        target = db_isolation.target_from_env(os.environ)
    except db_isolation.DbIsolationError as exc:
        pytest.skip(f'V3 auth PostgreSQL checks skipped: unsafe_target:{exc}')

    try:
        import asyncpg
    except ImportError:
        pytest.skip('V3 auth PostgreSQL checks skipped: asyncpg_missing')

    try:
        setup_conn = await asyncpg.connect(target.dsn, statement_cache_size=0)
    except Exception as exc:
        pytest.skip(f'V3 auth PostgreSQL checks skipped: {type(exc).__name__}')

    try:
        version = str(await setup_conn.fetchval('SHOW server_version_num'))
        ledger = await setup_conn.fetch(
            """
            SELECT migration_name, encode(migration_sha256, 'hex') AS sha256
            FROM v3_meta.schema_migration
            ORDER BY migration_name
            """
        )
    except Exception as exc:
        await setup_conn.close()
        pytest.fail(f'V3 auth database preflight failed: {type(exc).__name__}: {exc}')
    await setup_conn.close()

    assert version.startswith('18')
    assert [row['migration_name'] for row in ledger] == [
        '001_v3_baseline.sql',
        '002_v3_accounts_identity.sql',
    ]

    async def _init_conn(conn):
        import json

        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog',
        )

    pool = await asyncpg.create_pool(
        dsn=target.dsn,
        min_size=1,
        max_size=3,
        statement_cache_size=0,
        init=_init_conn,
    )
    try:
        yield pool
    finally:
        await pool.close()


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_v3_identity_structure_manifest_and_ledger(v3_auth_pool):
    async with v3_auth_pool.acquire() as conn:
        relations = await conn.fetch(
            """
            SELECT qualified_name
            FROM unnest(ARRAY[
                'v3_identity.account',
                'v3_identity.external_identity',
                'v3_identity.commander',
                'v3_identity.account_commander_access',
                'v3_identity.role',
                'v3_identity.account_role',
                'v3_identity.session',
                'v3_identity.oauth_login_state',
                'v3_identity.security_audit_event'
            ]) AS expected(qualified_name)
            WHERE to_regclass(qualified_name) IS NULL
            """
        )
        public_relations = await conn.fetchval(
            """
            SELECT count(*)
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public'
              AND relation.relkind IN ('r', 'p', 'v', 'm', 'S')
            """
        )
        identity_fks = await conn.fetchval(
            """
            SELECT count(*)
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'v3_identity'
              AND constraint_row.contype = 'f'
            """
        )
        required_indexes = await conn.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'v3_identity'
              AND indexname = ANY($1::text[])
            ORDER BY indexname
            """,
            [
                'account_role_single_active_owner_uidx',
                'external_identity_account_active_idx',
                'oauth_login_state_expiry_idx',
                'security_audit_event_code_time_idx',
                'session_account_active_idx',
            ],
        )
        roles = await conn.fetch(
            """
            SELECT role_id, public_code
            FROM v3_identity.role
            ORDER BY role_id
            """
        )
        digest_types = await conn.fetch(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'v3_identity'
              AND (table_name, column_name) IN (
                  ('session', 'session_token_sha256'),
                  ('oauth_login_state', 'state_sha256')
              )
            ORDER BY table_name
            """
        )

    assert relations == []
    assert public_relations == 0
    assert int(identity_fks) >= 15
    assert [row['indexname'] for row in required_indexes] == [
        'account_role_single_active_owner_uidx',
        'external_identity_account_active_idx',
        'oauth_login_state_expiry_idx',
        'security_audit_event_code_time_idx',
        'session_account_active_idx',
    ]
    assert [(row['role_id'], row['public_code']) for row in roles] == [
        (1, 'OWNER'),
        (2, 'ADMIN'),
        (3, 'MEMBER'),
        (4, 'SERVICE'),
    ]
    assert [row['data_type'] for row in digest_types] == [
        'bytea',
        'bytea',
    ]


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_repeated_login_identity_mapping_commander_separation_and_conflict(
    v3_auth_pool,
):
    identity = auth_router.FrontierIdentity(
        issuer=auth_router.FRONTIER_ISSUER,
        subject='stable-subject-one',
        commander_name='Same Commander',
    )
    first_user, first_raw_session, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        identity,
    )
    repeated_user, second_raw_session, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        identity.model_copy(update={'commander_name': 'Renamed Commander'}),
    )

    assert repeated_user.account_id == first_user.account_id
    assert repeated_user.commander_name == 'Renamed Commander'
    assert first_raw_session != second_raw_session

    other_user, _, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        auth_router.FrontierIdentity(
            issuer=auth_router.FRONTIER_ISSUER,
            subject='stable-subject-two',
            commander_name='Renamed Commander',
        ),
    )
    assert other_user.account_id != first_user.account_id

    with pytest.raises(HTTPException) as conflict:
        await auth_router._upsert_account_and_session(
            v3_auth_pool,
            identity,
            link_to_account_id=other_user.account_id,
        )
    assert conflict.value.status_code == 409

    async with v3_auth_pool.acquire() as conn:
        counts = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM v3_identity.account)::int AS accounts,
                (SELECT COUNT(*) FROM v3_identity.external_identity)::int AS identities,
                (SELECT COUNT(*) FROM v3_identity.commander)::int AS commanders,
                (SELECT COUNT(*) FROM v3_identity.session)::int AS sessions
            """
        )
        persisted_rows = await conn.fetch(
            'SELECT session_token_sha256 FROM v3_identity.session'
        )
        first_subject_account = await conn.fetchval(
            """
            SELECT account_id
            FROM v3_identity.external_identity
            WHERE provider = 'frontier'
              AND issuer = $1
              AND subject = 'stable-subject-one'
            """,
            auth_router.FRONTIER_ISSUER,
        )

    assert dict(counts) == {
        'accounts': 2,
        'identities': 2,
        'commanders': 2,
        'sessions': 3,
    }
    assert uuid.UUID(str(first_subject_account)) == first_user.account_id
    digest_values = {bytes(row['session_token_sha256']) for row in persisted_rows}
    assert first_raw_session not in digest_values
    assert token_digest(first_raw_session) in digest_values


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_disabled_identity_requires_explicit_owning_account_relink(
    v3_auth_pool,
    monkeypatch: pytest.MonkeyPatch,
):
    primary_identity = auth_router.FrontierIdentity(
        issuer=auth_router.FRONTIER_ISSUER,
        subject='disabled-relink-primary',
        commander_name='Relink Owner',
    )
    secondary_identity = auth_router.FrontierIdentity(
        issuer=auth_router.FRONTIER_ISSUER,
        subject='disabled-relink-secondary',
        commander_name='Relink Owner',
    )
    owner_user, _, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        primary_identity,
    )
    linked_user, _, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        secondary_identity,
        link_to_account_id=owner_user.account_id,
    )
    assert linked_user.account_id == owner_user.account_id

    async with v3_auth_pool.acquire() as conn:
        secondary_identity_id = await conn.fetchval(
            """
            SELECT external_identity_id
            FROM v3_identity.external_identity
            WHERE provider = 'frontier' AND issuer = $1 AND subject = $2
            """,
            auth_router.FRONTIER_ISSUER,
            secondary_identity.subject,
        )

    async def recently_authenticated_owner(_request: Request):
        return owner_user

    monkeypatch.setattr(
        auth_router,
        'get_request_user',
        recently_authenticated_owner,
    )
    await auth_router.unlink_identity(
        uuid.UUID(str(secondary_identity_id)),
        _request(),
        pool=v3_auth_pool,
    )

    async with v3_auth_pool.acquire() as conn:
        before_denied_login = await conn.fetchrow(
            """
            SELECT
                identity.disabled_at,
                identity.verified_at,
                (SELECT COUNT(*) FROM v3_identity.account)::int AS accounts,
                (
                    SELECT COUNT(*)
                    FROM v3_identity.session
                    WHERE account_id = identity.account_id
                )::int AS sessions
            FROM v3_identity.external_identity AS identity
            WHERE identity.external_identity_id = $1
            """,
            secondary_identity_id,
        )
    assert before_denied_login['disabled_at'] is not None

    with pytest.raises(HTTPException) as denied:
        await auth_router._upsert_account_and_session(
            v3_auth_pool,
            secondary_identity,
        )
    assert denied.value.status_code == 403

    async with v3_auth_pool.acquire() as conn:
        after_denied_login = await conn.fetchrow(
            """
            SELECT
                identity.disabled_at,
                identity.verified_at,
                (SELECT COUNT(*) FROM v3_identity.account)::int AS accounts,
                (
                    SELECT COUNT(*)
                    FROM v3_identity.session
                    WHERE account_id = identity.account_id
                )::int AS sessions
            FROM v3_identity.external_identity AS identity
            WHERE identity.external_identity_id = $1
            """,
            secondary_identity_id,
        )
    assert dict(after_denied_login) == dict(before_denied_login)

    other_user, _, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        auth_router.FrontierIdentity(
            issuer=auth_router.FRONTIER_ISSUER,
            subject='disabled-relink-other-account',
        ),
    )
    with pytest.raises(HTTPException) as conflict:
        await auth_router._upsert_account_and_session(
            v3_auth_pool,
            secondary_identity,
            link_to_account_id=other_user.account_id,
        )
    assert conflict.value.status_code == 409

    monkeypatch.setattr(settings, 'frontier_client_id', 'test-client-id')
    monkeypatch.setattr(settings, 'frontier_client_secret', 'test-client-secret')
    link_response = await auth_router.frontier_link(
        _request(),
        pool=v3_auth_pool,
    )
    state_cookie = link_response.headers['set-cookie']
    state = state_cookie.split('=', 1)[1].split(';', 1)[0]
    stored_link = await auth_router._consume_login_state(v3_auth_pool, state)
    assert stored_link is not None
    assert stored_link['intent'] == 'LINK'
    assert uuid.UUID(str(stored_link['account_id'])) == owner_user.account_id

    relinked_user, _, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        secondary_identity,
        link_to_account_id=uuid.UUID(str(stored_link['account_id'])),
    )
    assert relinked_user.account_id == owner_user.account_id

    subsequent_user, _, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        secondary_identity,
    )
    assert subsequent_user.account_id == owner_user.account_id

    async with v3_auth_pool.acquire() as conn:
        restored_disabled_at = await conn.fetchval(
            """
            SELECT disabled_at
            FROM v3_identity.external_identity
            WHERE external_identity_id = $1
            """,
            secondary_identity_id,
        )
    assert restored_disabled_at is None


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_state_replay_session_rotation_and_duplicate_owner_protection(
    v3_auth_pool,
    monkeypatch: pytest.MonkeyPatch,
):
    # A negative cutoff makes rotation deterministic even when the disposable
    # database clock is a few seconds ahead of the test process clock.
    monkeypatch.setattr(settings, 'auth_session_rotation_seconds', -10)
    monkeypatch.setattr(settings, 'admin_token', 'existing-admin-secret')
    monkeypatch.setattr(settings, 'cors_origins', 'http://testserver')

    async with v3_auth_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO v3_identity.oauth_login_state (
                state_sha256,
                code_verifier,
                return_to,
                intent,
                expires_at
            )
            VALUES ($1, 'verifier', '/', 'LOGIN', NOW() + INTERVAL '10 minutes')
            """,
            token_digest('one-time-state'),
        )
    assert await auth_router._consume_login_state(
        v3_auth_pool,
        'one-time-state',
    ) is not None
    assert await auth_router._consume_login_state(
        v3_auth_pool,
        'one-time-state',
    ) is None

    async with v3_auth_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO v3_identity.oauth_login_state (
                state_sha256,
                code_verifier,
                return_to,
                intent,
                created_at,
                expires_at
            )
            VALUES (
                $1,
                'expired-verifier',
                '/',
                'LOGIN',
                NOW() - INTERVAL '20 minutes',
                NOW() - INTERVAL '10 minutes'
            )
            """,
            token_digest('expired-state'),
        )
    assert await auth_router._consume_login_state(
        v3_auth_pool,
        'expired-state',
    ) is None

    first_user, raw_session, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        auth_router.FrontierIdentity(
            issuer=auth_router.FRONTIER_ISSUER,
            subject='owner-subject',
        ),
    )
    authentication = await load_session(v3_auth_pool, raw_session, rotate=True)
    assert authentication is not None
    assert authentication.rotated_token is not None
    assert authentication.rotated_token != raw_session
    assert authentication.user.account_id == first_user.account_id

    async def first_request_user(_request: Request):
        return first_user

    monkeypatch.setattr(auth_router, 'get_request_user', first_request_user)
    claimed = await auth_router.claim_owner(
        _request(),
        auth_router.OwnerClaimRequest(admin_token='existing-admin-secret'),
        pool=v3_auth_pool,
    )
    assert claimed.user is not None and claimed.user.is_owner is True

    second_user, _, _ = await auth_router._upsert_account_and_session(
        v3_auth_pool,
        auth_router.FrontierIdentity(
            issuer=auth_router.FRONTIER_ISSUER,
            subject='second-owner-attempt',
        ),
    )

    async def second_request_user(_request: Request):
        return second_user

    monkeypatch.setattr(auth_router, 'get_request_user', second_request_user)
    with pytest.raises(HTTPException) as duplicate:
        await auth_router.claim_owner(
            _request(),
            auth_router.OwnerClaimRequest(admin_token='existing-admin-secret'),
            pool=v3_auth_pool,
        )
    assert duplicate.value.status_code == 409

    async with v3_auth_pool.acquire() as conn:
        old_session = await conn.fetchrow(
            """
            SELECT
                session_state,
                revoked_at,
                revocation_reason,
                rotated_to_session_id
            FROM v3_identity.session
            WHERE session_token_sha256 = $1
            """,
            token_digest(raw_session),
        )
        owner_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM v3_identity.account_role AS account_role
            JOIN v3_identity.role AS role ON role.role_id = account_role.role_id
            WHERE role.public_code = 'OWNER' AND account_role.revoked_at IS NULL
            """
        )
        rotation_audit_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM v3_identity.security_audit_event
            WHERE event_code = 'session.rotated'
            """
        )

    assert old_session['session_state'] == 'ROTATED'
    assert old_session['revoked_at'] is None
    assert old_session['revocation_reason'] == 'rotated'
    assert old_session['rotated_to_session_id'] == authentication.user.session_id
    assert owner_count == 1
    assert rotation_audit_count == 1

    rotated_token = authentication.rotated_token
    assert rotated_token is not None
    logout_response = Response()
    logged_out = await auth_router.auth_logout(
        _request(
            cookie=f'{settings.auth_session_cookie_name}={rotated_token}',
        ),
        logout_response,
        pool=v3_auth_pool,
    )
    assert logged_out.authenticated is False
    assert await load_session(v3_auth_pool, rotated_token) is None
    assert 'Max-Age=0' in logout_response.headers['set-cookie']
