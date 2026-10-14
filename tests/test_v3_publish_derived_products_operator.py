from __future__ import annotations

import json
import io
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from urllib.error import HTTPError
import urllib.request

import pytest
import yaml

from scripts.operator.lib.f2d_evidence import load_sealed, seal

pytestmark = pytest.mark.operator
ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-publish-derived-products.sh"
WORKFLOW = ROOT / ".github/workflows/v3-production-application-deploy.yml"
EXPECTED_NOT_READY = (
    "Finder ranking products are not available for the published generation "
    "(system_archetype=READY-unpublished, system_search=READY-unpublished)."
)


def _source() -> str:
    return ACTION.read_text(encoding="utf-8")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _function(name: str) -> str:
    source = _source()
    start = source.index(f"{name}() {{\n")
    body_start = source.index("\n", start) + 1
    following = re.search(r"^[A-Za-z_][A-Za-z0-9_]*\(\) \{", source[body_start:], re.MULTILINE)
    return source[start:body_start + following.start()] if following else source[start:]


def _python(name: str, marker: str = "") -> str:
    blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY(?:\n|$)", _function(name), re.DOTALL)
    selected = [block for block in blocks if marker in block]
    assert len(selected) == 1
    return selected[0]


def _execute(code: str, arguments: list[object], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["operator-preflight", *map(str, arguments)])
    exec(compile(code, str(ACTION), "exec"), {"__name__": "__main__"})


def _json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("attestation", "reason"),
    ((None, "attested_identity_missing"), ("0" * 64, "attested_identity_mismatch")),
)
def test_identity_refusal_precedes_host_database_and_image_access(
    attestation: str | None, reason: str, tmp_path: Path
) -> None:
    # A fake Docker records any accidental access before the identity gate.
    docker = tmp_path / "docker"
    accessed = tmp_path / "docker-accessed"
    docker.write_text('#!/bin/sh\nprintf accessed > "$ACCESS_LOG"\nexit 99\n')
    docker.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = str(tmp_path) + os.pathsep + environment["PATH"]
    environment["ACCESS_LOG"] = str(accessed)
    environment.pop("F2D_OPERATOR_CODE_SHA256_ATTESTED", None)
    if attestation is not None:
        environment["F2D_OPERATOR_CODE_SHA256_ATTESTED"] = attestation
    result = subprocess.run(
        ["bash", str(ACTION), "run", str(ROOT), "0" * 40, "github:tester/run-1"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 64
    assert reason in result.stderr
    assert not accessed.exists()
    assert "unexpected hostname" not in result.stderr
    source = _source()
    assert source.index("require_f2d_operator_code_identity") < source.index("require_target()")
    assert source.index("require_f2d_operator_code_identity") < source.index("db_query()")
    # Actions may source only the identity helper, never another action.
    assert re.findall(r'^source\s+(.+)$', source, re.MULTILINE) == ['"$IDENTITY_HELPER"']


def test_publisher_pins_host_generation_stage_and_actor() -> None:
    source = _source()
    for declaration in (
        'TARGET_HOSTNAME="ed-finder-prod"',
        'TARGET_FQDN="nb79a3d.mevnode.com"',
        'POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"',
        'DATABASE_USER="edfinder_v3"',
        'DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"',
        'COMPOSE_PROJECT="edfinder-v3-production"',
        'WORKER_NETWORK="edfinder-v3-phase4c-full-20260827_r5-network"',
        'TARGET_GENERATION_KEY="ratings_v4_prod_p4_parallel_v1"',
        'TARGET_GENERATION_ID="cfc25d36-3bc7-4011-a465-d6460eaaf826"',
        'TARGET_PUBLICATION_SEQUENCE="1"',
    ):
        assert declaration in source
    assert '/var/tmp/edfinder-v3-publish-"$SOURCE_SHA"' in source
    assert ".v3-publish-source-sha" in source
    assert ".v3-probe-wheelhouse" in source
    assert "^[A-Za-z0-9._@:/-]{1,128}$" in source
    assert "current_derived_generation" in source
    assert "PUBLISHED" in source


def test_worker_is_bounded_and_keeps_dsn_off_command_line() -> None:
    source = _source()
    for required in (
        "timeout --signal=TERM --kill-after=30s 1800 docker run",
        "--cpus 2",
        "--memory 4g",
        "--read-only",
        "--tmpfs /tmp",
        "dst=/work,readonly",
        "dst=/publish",
        '"psycopg[binary]==3.3.4"',
        "--no-index",
        "--find-links /work/.v3-probe-wheelhouse",
        '--env-file "$ENV_FILE"',
        "scripts/v3_publish_derived_products.py",
    ):
        assert required in source
    assert "DATABASE_URL=%s" in source
    assert "chmod 600" in source
    assert not re.search(r"--env\s+[\"']?[A-Z_]*DATABASE_URL=", source)
    assert "default_transaction_read_only" not in source


def test_plan_statements_come_from_active_api_and_dense_spatial_anchor() -> None:
    source = _source()
    assert 'docker exec -i "$API" /app/.venv/bin/python -' in source
    assert '< "$REPO_ROOT/scripts/v3_plan_probe_statements.py"' in source
    assert "--dense-anchor" in source
    assert "v3_spatial.current_spatial_generation" in source
    assert "max(c.level)" in source
    assert "ORDER BY c.system_count DESC, c.cell_key ASC" in source
    assert "statements_sha256" in source


def test_operation_has_sealed_failure_and_committed_evidence() -> None:
    source = _source()
    for field in (
        "ed-finder/v3-publish-derived-products/v1",
        "seal(",
        "publication_performed",
        "db_writes_performed",
        "canonical_writes_performed",
        "application_service_changes_performed",
        "plan_probe_receipt",
        "content_sha256",
        "derived_product_publication_audit",
        "published_at",
        "image_digest",
        "f2d_operator_code_sha256",
    ):
        assert field in source


def test_deployment_lock_covers_both_image_checks_commit_and_receipt() -> None:
    flow = _function("run_operation")
    ordered = (
        "require_generation", "acquire_deployment_lock", "require_products",
        "load_attestation", "read_image", "check_image", "probe_pairs",
        "require_manifest_identities", "require_maintenance",
        "timeout --signal=TERM --kill-after=30s 1800 docker run", "ready-to-commit.json",
        'read_image > "$RUN_DIR/image-last.json"', "write_decision commit",
        'wait "$WORKER_PID"', "verify_postcommit", 'write_result 0 ""',
    )
    positions = [flow.index(item) for item in ordered]
    assert positions == sorted(positions)
    lock = _function("acquire_deployment_lock")
    assert "['external_authority']['receipt_directory']" in lock
    assert "'/var/lib/ed-finder/v3-production/receipts'" in lock
    assert 'exec {DEPLOY_LOCK_FD}>>"$receipt_directory/deploy.lock"' in lock
    assert 'flock -n "$DEPLOY_LOCK_FD"' in lock
    assert "flock -u" not in _source()
    cleanup = _function("cleanup")
    assert cleanup.index('wait "$WORKER_PID"') < cleanup.index("exec {DEPLOY_LOCK_FD}>&-")
    assert "trap cleanup EXIT" in flow
    # A READY product under an old API refuses before launching the write worker.
    assert flow.index("check_image") < flow.index("timeout --signal=TERM --kill-after=30s 1800 docker run")


def test_refusal_codes_identify_each_go_live_gate() -> None:
    source = _source()
    for code, item in (
        (70, "deployment_lock_held"), (71, "products_not_ready_verified_unpublished"),
        (72, "publication_already_happened"), (73, "active_api_digest_not_attested"),
        (74, "behavioural_probe_pairs"), (75, "product_manifest_code_or_model_identity"),
        (76, "build_final_receipts_or_live_maintenance"),
        (79, "database_target_identity_mismatch"),
        (80, "postcommit_live_finder_verification"),
    ):
        assert f"refuse {code} {item}" in source
    assert "host_abort=77" in source
    assert "host_abort=78" in source
    assert "write_decision abort active_api_digest_changed" in source
    assert 'refuse "$host_abort" host_commit_handshake_abort' in source


@pytest.mark.parametrize("field", ("ranking_version", "ranking_sha256", "f2d_operator_code_sha256"))
def test_missing_release_attestation_refuses_before_publication(
    field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = {
        "ranking_version": "ranking-fixture-v1", "ranking_sha256": "a" * 64,
        "f2d_operator_code_sha256": "b" * 64,
        "images": {"backend": "registry/api@sha256:" + "c" * 64},
    }
    del value[field]
    authority = _json(tmp_path / "authority.json", {"accepted_release_schema_compatibility": value})
    with pytest.raises(SystemExit, match=field):
        _execute(_python("load_attestation"), [authority, "b" * 64], monkeypatch)


def test_old_api_digest_refuses_even_with_ready_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attestation = _json(tmp_path / "attestation.json", {"images": {"backend": "registry/api@sha256:" + "a" * 64}})
    image = _json(tmp_path / "image.json", {"image_digest": "registry/api@sha256:" + "b" * 64})
    with pytest.raises(SystemExit, match="differs from accepted release"):
        _execute(_python("check_image"), [attestation, image], monkeypatch)


@pytest.mark.parametrize("statuses", ((503, 422, 503, 422), (200, 422, 503, 422)))
def test_probe_pairs_issue_exact_requests_and_record_every_status(
    statuses: tuple[int, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = []

    def request(request, *, timeout):
        assert timeout == 15
        requests.append(request)
        raise HTTPError(
            request.full_url, statuses[len(requests) - 1], "fixture", None,
            io.BytesIO(json.dumps({"detail": EXPECTED_NOT_READY}).encode()),
        )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: SimpleNamespace(open=request))
    path = tmp_path / "statuses.json"
    if statuses[0] == 200:
        with pytest.raises(SystemExit, match="behavioural_probe_pairs_failed"):
            _execute(_python("probe_pairs"), [path], monkeypatch)
    else:
        _execute(_python("probe_pairs"), [path], monkeypatch)
    assert [item.full_url for item in requests] == [
        "http://127.0.0.1:58080/api/archetypes/rankings?archetype=paradise&offset=9999&limit=1",
        "http://127.0.0.1:58080/api/archetypes/rankings?archetype=paradise&offset=9999&limit=2",
        "http://127.0.0.1:58080/api/local/search",
        "http://127.0.0.1:58080/api/local/search",
    ]
    assert [item.get_method() for item in requests] == ["GET", "GET", "POST", "POST"]
    assert [json.loads(item.data) for item in requests[2:]] == [
        {"galaxy_wide": True, "sort_by": "development", "from": 9999, "size": 1},
        {"galaxy_wide": True, "sort_by": "development", "from": 9999, "size": 2},
    ]
    rows = json.loads(path.read_text())
    assert [row["status"] for row in rows] == list(statuses)
    assert [row["detail"] for row in rows] == [EXPECTED_NOT_READY] * 4
    assert [row["reason_verified"] for row in rows] == [True, None, True, None]


@pytest.mark.parametrize("index", (0, 2))
@pytest.mark.parametrize("payload", (
    b'{"detail":"database connection failed"}',
    b'{"detail":"Finder ranking products are not available for the published generation '
    b'(system_archetype=MISSING, system_search=MISSING)."}',
    b'{}', b'[]', b'not json', b'\xff',
))
def test_probe_pairs_refuse_unverified_not_ready_reason_before_write_worker(
    index: int, payload: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = []

    def request(request, *, timeout):
        current = len(requests)
        requests.append(request)
        body = payload if current == index else json.dumps({"detail": EXPECTED_NOT_READY}).encode()
        raise HTTPError(request.full_url, (503, 422, 503, 422)[current], "fixture", None, io.BytesIO(body))

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: SimpleNamespace(open=request))
    path = tmp_path / "statuses.json"
    with pytest.raises(SystemExit, match="behavioural_probe_pairs_failed"):
        _execute(_python("probe_pairs"), [path], monkeypatch)
    rows = json.loads(path.read_text())
    assert len(rows) == 4
    assert rows[index]["status"] == 503
    assert rows[index]["reason_verified"] is False
    assert rows[2 - index]["reason_verified"] is True
    flow = _function("run_operation")
    assert flow.index("probe_pairs || refuse 74 behavioural_probe_pairs") < flow.index(
        "timeout --signal=TERM --kill-after=30s 1800 docker run"
    )


def test_probe_pairs_refuse_oversized_response_with_bounded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sizes = []

    class Oversized(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 64 * 1024 + 1
            sizes.append(size)
            return b" " * size

    def request(request, *, timeout):
        status = 503 if "limit=1" in request.full_url or b'"size": 1' in (request.data or b'') else 422
        raise HTTPError(request.full_url, status, "fixture", None, Oversized())

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: SimpleNamespace(open=request))
    path = tmp_path / "statuses.json"
    with pytest.raises(SystemExit, match="behavioural_probe_pairs_failed"):
        _execute(_python("probe_pairs"), [path], monkeypatch)
    assert len(sizes) == 4
    assert all(row["status"] is None for row in json.loads(path.read_text()))


@pytest.mark.parametrize("mismatch", (None, "search", "archetype", "checkout_model", "api_model"))
def test_checkout_and_api_model_must_match_product_manifest_identities(
    mismatch: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {
        "search_code_sha256": {"scripts/v3_system_search.py": "a" * 64},
        "archetype_code_sha256": {"scripts/v3_system_archetype.py": "b" * 64},
        "model_file_sha256": "c" * 64,
    }
    products = [
        {"product_code": "system_search", "manifest": {"code_sha256": expected["search_code_sha256"]}},
        {"product_code": "system_archetype", "manifest": {
            "code_sha256": expected["archetype_code_sha256"], "model_file_sha256": "c" * 64,
        }},
    ]
    if mismatch == "search":
        products[0]["manifest"]["code_sha256"] = {"scripts/v3_system_search.py": "d" * 64}
    elif mismatch == "archetype":
        products[1]["manifest"]["code_sha256"] = {"scripts/v3_system_archetype.py": "d" * 64}
    elif mismatch == "checkout_model":
        expected["model_file_sha256"] = "d" * 64
    _json(tmp_path / "products.json", products)
    _json(tmp_path / "checkout-identities.json", expected)
    (tmp_path / "api-model.sha256").write_text(("d" if mismatch == "api_model" else "c") * 64 + "  /app/shared_contracts/v3_system_archetype_model.py\n")
    code = _python("require_manifest_identities", "Search manifest code identity mismatch")
    if mismatch:
        with pytest.raises(SystemExit, match="mismatch"):
            _execute(code, [tmp_path], monkeypatch)
    else:
        _execute(code, [tmp_path], monkeypatch)


@pytest.mark.parametrize("defect", (None, "last_vacuum", "last_analyze", "live_old", "identity", "manifest", "seal"))
def test_build_final_receipts_require_current_identity_manifest_and_maintenance(
    defect: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    products = ["system_search", "system_archetype"]
    _json(tmp_path / "products.json", [{"product_code": p, "manifest_sha256": "a" * 64} for p in products])
    live = [{"product_code": p, "last_vacuum": "2026-10-14T12:00:02+00:00", "last_analyze": "2026-10-14T12:00:02+00:00"} for p in products]
    if defect == "live_old":
        live[0]["last_analyze"] = "2026-10-14T12:00:00+00:00"
    _json(tmp_path / "live-maintenance.json", live)
    receipts = []
    for product in products:
        body = {
            "schema_version": "ed-finder/v3-build-final-receipt/v1", "product_code": product,
            "derived_generation_id": "fixture-generation", "manifest_sha256": "a" * 64,
            "lifecycle_state": "READY", "validation_status": "VERIFIED",
            "f2d_operator_code_sha256": "b" * 64,
            "final_insert_at": "2026-10-14T12:00:00+00:00",
            "last_vacuum": "2026-10-14T12:00:01+00:00",
            "last_analyze": "2026-10-14T12:00:01+00:00",
        }
        if product == "system_search":
            if defect in {"last_vacuum", "last_analyze"}:
                body[defect] = "2026-10-14T11:59:59+00:00"
            elif defect == "identity":
                body["f2d_operator_code_sha256"] = "c" * 64
            elif defect == "manifest":
                body["manifest_sha256"] = "c" * 64
        sealed = seal(body)
        if defect == "seal" and product == "system_search":
            sealed["last_vacuum"] = "2026-10-14T12:00:03+00:00"
        receipts.append(_json(tmp_path / f"{product}.json", sealed))
    code = _python("require_maintenance")
    arguments = [tmp_path, *receipts, "fixture-generation", "b" * 64]
    if defect == "seal":
        with pytest.raises(ValueError, match="content_sha256 mismatch"):
            _execute(code, arguments, monkeypatch)
    elif defect:
        with pytest.raises(SystemExit):
            _execute(code, arguments, monkeypatch)
    else:
        _execute(code, arguments, monkeypatch)
        assert len(json.loads((tmp_path / "maintenance.json").read_text())) == 2


@pytest.mark.parametrize("decision", ("commit", "abort"))
def test_host_commit_decision_is_atomic_private_and_explicit(
    decision: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _execute(_python("write_decision"), [tmp_path, decision, "image_changed"], monkeypatch)
    path = tmp_path / "commit-decision.json"
    assert path.stat().st_mode & 0o777 == 0o600
    value = json.loads(path.read_text())
    assert value == ({"decision": "commit"} if decision == "commit" else {"decision": "abort", "reason": "image_changed"})
    assert not (tmp_path / ".commit-decision.tmp").exists()


def test_preflight_refusal_receipt_is_sealed_and_reports_no_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _execute(_python("write_result"), [tmp_path, 75, "identity_mismatch", "b" * 64, "github:tester/run-1", "false", "fixture", "fixture-id", 1], monkeypatch)
    receipt = load_sealed(tmp_path / "action-receipt.json")
    envelope = json.loads(capsys.readouterr().out)
    assert receipt["failures"] == ["identity_mismatch"]
    assert envelope["status"] == "refused"
    assert envelope["read_only"] is False
    for field in ("db_writes_performed", "publication_performed", "canonical_writes_performed", "application_service_changes_performed"):
        assert envelope[field] is False


def test_workflow_requires_authority_gate_protected_approval_and_concurrency() -> None:
    workflow = _workflow()
    dispatch = workflow[True]["workflow_dispatch"]["inputs"]
    assert dispatch["operation"]["options"].count("publish-finder-products") == 1
    assert dispatch["release_run_id"]["required"] is False
    assert workflow["concurrency"] == {
        "group": "v3-production-application-authority",
        "cancel-in-progress": False,
    }
    jobs = workflow["jobs"]
    assert "github.ref == 'refs/heads/main'" in jobs["guard"]["if"]
    prepare = jobs["prepare"]
    assert prepare["if"] == "inputs.operation != 'inventory'"
    assert any(
        "python scripts/operator/v3_production_deploy.py --operation authority-gate"
        in step.get("run", "")
        and not step.get("if")
        for step in prepare["steps"]
    )
    protected = jobs["production-operation"]
    assert protected["environment"] == "v3-production"
    assert "prepare" in protected["needs"]
    assert protected["if"] == "inputs.operation != 'inventory'"
    for job in (prepare, protected):
        for step in job["steps"]:
            if "candidate" in step.get("name", "").lower() or "release run ID" in step.get("name", ""):
                assert "inputs.operation != 'publish-finder-products'" in step.get("if", "")


def test_publication_steps_use_production_credentials_attestation_and_receipt() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["production-operation"]["steps"]
    publication = [
        step for step in steps
        if "inputs.operation == 'publish-finder-products'" in step.get("if", "")
    ]
    assert len(publication) >= 4
    text = yaml.safe_dump(publication)
    assert "ED_NEW_OPERATOR_" not in text
    assert "V3_PRODUCTION_SSH_KEY" in text
    assert "V3_PRODUCTION_HOST" in text
    assert "V3_PRODUCTION_PORT" in text
    assert "V3_PRODUCTION_USER" in text
    assert "V3_PRODUCTION_SSH_KNOWN_HOSTS" in text
    assert "ssh-keyscan" not in text
    for option in ("StrictHostKeyChecking=yes", "UserKnownHostsFile=~/.ssh/known_hosts", "IdentitiesOnly=yes"):
        assert option in text
    for required in (
        "/var/tmp/edfinder-v3-publish-",
        ".v3-publish-source-sha",
        ".v3-probe-wheelhouse",
        "deploy/v3-production/target-authority.json",
        "accepted_release_schema_compatibility",
        "f2d_operator_code_sha256",
        "F2D_OPERATOR_CODE_SHA256_ATTESTED",
        "github:${{ github.actor }}/run-${{ github.run_id }}",
        "v3-publish-derived-products.sh",
        "--preserve-env=F2D_OPERATOR_CODE_SHA256_ATTESTED",
        "tee",
    ):
        assert required in text
    assert "DATABASE_URL" not in text
    artifact = next(step for step in publication if step.get("with", {}).get("name") == "v3-publish-derived-products-operation")
    assert artifact["if"].startswith("always()")
    assert artifact["with"]["retention-days"] == 90


def test_identity_manifest_registers_both_publisher_execution_surfaces() -> None:
    entries = [
        line for line in (ROOT / "deploy/v3-production/f2d-operator-code.txt").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert entries == sorted(entries)
    assert "scripts/operator/actions/v3-publish-derived-products.sh" in entries
    assert "scripts/v3_publish_derived_products.py" in entries


def test_real_program_ready_schema_is_accepted_by_host_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import v3_publish_derived_products as publisher
    from tests.test_v3_publish_derived_products import Connection, invoke, stub_probe

    stub_probe(monkeypatch)
    connection = Connection()
    original_wait = publisher._wait_for_decision

    def host(directory: Path, timeout: int) -> None:
        ready = json.loads((directory / "ready-to-commit.json").read_text())
        generation = ready["generation"]
        _execute(_python("validate_ready"), [
            directory / "ready-to-commit.json", generation["generation_key"],
            generation["derived_generation_id"], generation["publication_sequence"],
        ], monkeypatch)
        publisher.atomic_json(directory / "commit-decision.json", {"decision": "commit"})
        original_wait(directory, timeout)

    monkeypatch.setattr(publisher, "_wait_for_decision", host)
    receipt = invoke(connection, tmp_path)
    assert receipt["exit_code"] == 0
    assert receipt["publication_performed"] is True
    assert connection.committed == list(publisher.PRODUCTS)


@pytest.mark.parametrize("defect", ("generation", "published_at", "plan_probe_receipt_sha256"))
def test_malformed_ready_handshake_refuses_commit(
    defect: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = {
        "generation": {"generation_key": "fixture", "derived_generation_id": "fixture-id",
                       "publication_sequence": 1, "lifecycle_state": "PUBLISHED", "is_current": True},
        "products": ["system_search", "system_archetype"],
        "published_at": {code: "2026-10-14T12:00:00+00:00" for code in ("system_search", "system_archetype")},
        "plan_probe_receipt_sha256": "a" * 64,
    }
    if defect == "generation":
        value["generation"]["is_current"] = False
    elif defect == "published_at":
        value["published_at"]["system_archetype"] = "2026-10-14T12:00:01+00:00"
    else:
        value[defect] = "malformed"
    path = _json(tmp_path / "ready.json", value)
    with pytest.raises(SystemExit):
        _execute(_python("validate_ready"), [path, "fixture", "fixture-id", 1], monkeypatch)


@pytest.mark.parametrize("already_published,verified,expected", [(True, True, 72), (False, False, 71)])
def test_host_product_state_refuses_republication_or_unverified_build(
    already_published: bool, verified: bool, expected: int,
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [{"product_code": code, "lifecycle_state": "READY",
             "validation_status": "VERIFIED" if verified else "FAILED",
             "published_at": "2026-10-14T12:00:00Z" if already_published and code == "system_search" else None}
            for code in ("system_search", "system_archetype")]
    path = _json(tmp_path / "products.json", rows)
    with pytest.raises(SystemExit) as refusal:
        _execute(_python("require_products"), [path], monkeypatch)
    assert refusal.value.code == expected


def test_partial_preflight_evidence_still_yields_sealed_failure_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "attestation.json").write_text("")
    _execute(_python("write_result"), [tmp_path, 73, "attestation_invalid", "b" * 64,
                                      "github:tester/run-1", "false", "fixture", "fixture-id", 1], monkeypatch)
    receipt = load_sealed(tmp_path / "action-receipt.json")
    envelope = json.loads(capsys.readouterr().out)
    assert receipt["attestation"] == {"evidence_unreadable": True}
    assert envelope["exit_code"] == 73
    assert envelope["publication_performed"] is False


@pytest.mark.parametrize("host,user,database,query,network,persisted", [
    ("edfinder-v3-phase4c-full-20260827_r5-postgres", "edfinder_v3",
     "edfinder_v3_phase4c_full_20260827_r5", "", {"IPAddress": "172.30.0.2"}, True),
    ("172.30.0.2", "edfinder_v3", "edfinder_v3_phase4c_full_20260827_r5",
     "?sslmode=require", {"IPAddress": "172.30.0.2"}, True),
    ("wrong-postgres", "edfinder_v3", "edfinder_v3_phase4c_full_20260827_r5",
     "", {"IPAddress": "172.30.0.2"}, False),
    ("172.30.0.3", "edfinder_v3", "edfinder_v3_phase4c_full_20260827_r5",
     "", {"IPAddress": "172.30.0.2"}, False),
    ("172.30.0.2", "wrong_user", "edfinder_v3_phase4c_full_20260827_r5",
     "", {"IPAddress": "172.30.0.2"}, False),
    ("172.30.0.2", "edfinder_v3", "wrong_database",
     "", {"IPAddress": "172.30.0.2"}, False),
    ("172.30.0.2", "edfinder_v3", "edfinder_v3_phase4c_full_20260827_r5",
     "?host=wrong-postgres", {"IPAddress": "172.30.0.2"}, False),
    ("172.30.0.2", "edfinder_v3", "edfinder_v3_phase4c_full_20260827_r5",
     "?hostaddr=172.30.0.3", {"IPAddress": "172.30.0.2"}, False),
    ("172.30.0.2", "edfinder_v3", "edfinder_v3_phase4c_full_20260827_r5",
     "?dbname=wrong_database", {"IPAddress": "172.30.0.2"}, False),
    ("172.30.0.2", "edfinder_v3", "edfinder_v3_phase4c_full_20260827_r5",
     "?user=wrong_user", {"IPAddress": "172.30.0.2"}, False),
    ("172.30.0.2", "edfinder_v3", "edfinder_v3_phase4c_full_20260827_r5",
     "?service=other-target", {"IPAddress": "172.30.0.2"}, False),
    ("edfinder-v3-phase4c-full-20260827_r5-postgres", "edfinder_v3",
     "edfinder_v3_phase4c_full_20260827_r5", "", None, False),
], ids=["container-name", "network-ip", "wrong-host", "wrong-ip", "wrong-user",
        "wrong-database", "host-override", "hostaddr-override", "database-override",
        "user-override", "service-override", "missing-network"])
def test_api_dsn_is_bound_to_pinned_database_user_and_network_without_logging(
    host, user, database, query, network, persisted, tmp_path,
):
    # All credentials here are synthetic. Exercise the actual shell function
    # with Docker mocked; the DSN may leave it only into a private captured file.
    dsn = f"postgresql://{user}:private-test-password@{host}/{database}{query}"
    private = tmp_path / "dsn"
    environment = {
        **os.environ, "PYTHON_BIN": sys.executable,
        "POSTGRES_CONTAINER": "edfinder-v3-phase4c-full-20260827_r5-postgres",
        "WORKER_NETWORK": "edfinder-v3-phase4c-full-20260827_r5-network",
        "DATABASE_NAME": "edfinder_v3_phase4c_full_20260827_r5",
        "DATABASE_USER": "edfinder_v3", "TEST_DSN": dsn,
        "TEST_NETWORK": json.dumps(network), "PRIVATE_DSN_FILE": str(private),
    }
    script = '''set -euo pipefail
fail() { printf '%s\\n' "$*" >&2; exit 64; }
docker() {
  if [ "$4" = test-api ]; then
    printf 'DATABASE_URL=%s\\n' "$TEST_DSN"
  elif [ "$4" = "$POSTGRES_CONTAINER" ]; then
    [[ "$3" == *"$WORKER_NETWORK"* ]] || return 91
    printf '%s\\n' "$TEST_NETWORK"
  else
    return 91
  fi
}
''' + _function("api_database_url") + '\napi_database_url test-api > "$PRIVATE_DSN_FILE"\n'
    result = subprocess.run(["bash", "-c", script], env=environment,
                            capture_output=True, text=True, check=False)
    assert result.returncode == (0 if persisted else 79), result.stderr
    assert result.stdout == ""
    assert dsn not in result.stderr and "private-test-password" not in result.stderr
    assert private.read_text() == (dsn if persisted else "")


def _live_identity_fixture(tmp_path: Path) -> dict:
    identity = {
        "derived_generation_id": "fixture-id", "publication_sequence": 1,
        "ranking_version": "ranking-fixture-v1", "ranking_sha256": "a" * 64,
        "archetype_version": "archetype-fixture-v1",
        "archetype_manifest_sha256": "b" * 64, "archetype_model_sha256": "c" * 64,
    }
    _json(tmp_path / "attestation.json", {
        key: identity[key] for key in ("ranking_version", "ranking_sha256")
    })
    _json(tmp_path / "products.json", [{
        "product_code": "system_archetype",
        "manifest": {"archetype_model_sha256": identity["archetype_model_sha256"]},
    }])
    _json(tmp_path / "postcommit.json", [{
        "product_code": "system_archetype", "product_version": identity["archetype_version"],
        "manifest_sha256": identity["archetype_manifest_sha256"],
    }])
    return identity


@pytest.mark.parametrize("endpoint", (0, 1))
@pytest.mark.parametrize("defect", (
    None, "status", "empty-results", "malformed", "oversized", "unreachable",
    "derived_generation_id", "publication_sequence", "ranking_version", "ranking_sha256",
    "archetype_version", "archetype_manifest_sha256", "archetype_model_sha256",
    "mismatch:derived_generation_id", "mismatch:publication_sequence", "mismatch:ranking_version",
    "mismatch:ranking_sha256", "mismatch:archetype_version", "mismatch:archetype_manifest_sha256",
    "mismatch:archetype_model_sha256",
))
def test_postcommit_live_finder_requires_results_and_complete_matching_identity(
    endpoint: int, defect: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _live_identity_fixture(tmp_path)
    requests = []
    read_sizes = []

    class Response(io.BytesIO):
        status = 200

        def read(self, size=-1):
            assert 0 < size <= 64 * 1024 + 1
            read_sizes.append(size)
            return super().read(size)

    def request(request, *, timeout):
        assert timeout == 15
        index = len(requests)
        requests.append(request)
        envelope = {"ranking": dict(identity), "results": [{"system_id64": "42"}]}
        if index == endpoint and defect:
            if defect == "unreachable":
                raise OSError("fixture unavailable")
            if defect == "status":
                raise HTTPError(request.full_url, 503, "fixture", None, io.BytesIO(b"{}"))
            if defect == "malformed":
                return Response(b"not json")
            if defect == "oversized":
                return Response(b" " * (64 * 1024 + 1))
            if defect == "empty-results":
                envelope["results"] = []
            elif defect.startswith("mismatch:"):
                field = defect.split(":", 1)[1]
                envelope["ranking"][field] = 2 if field == "publication_sequence" else "wrong"
            else:
                del envelope["ranking"][defect]
        return Response(json.dumps(envelope).encode())

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: SimpleNamespace(open=request))
    code = _python("verify_live_finder")
    if defect:
        with pytest.raises(SystemExit) as refusal:
            _execute(code, [tmp_path, "fixture", "fixture-id", 1], monkeypatch)
        assert refusal.value.code == 80
    else:
        _execute(code, [tmp_path, "fixture", "fixture-id", 1], monkeypatch)
    assert [item.full_url for item in requests] == [
        "http://127.0.0.1:58080/api/archetypes/rankings?archetype=paradise&offset=0&limit=1",
        "http://127.0.0.1:58080/api/local/search",
    ]
    assert [item.get_method() for item in requests] == ["GET", "POST"]
    assert json.loads(requests[1].data) == {
        "galaxy_wide": True, "sort_by": "development", "from": 0, "size": 1,
    }
    evidence = json.loads((tmp_path / "live-finder.json").read_text())
    assert evidence["generation"]["generation_key"] == "fixture"
    assert evidence["expected_identity"] == identity
    assert len(evidence["responses"]) == 2
    assert bool(evidence["failures"]) == bool(defect)
    healthy = evidence["responses"][1 - endpoint]
    assert healthy["status"] == 200 and healthy["identity"] == identity
    assert all(healthy["checks"].values())
    if not defect:
        assert all(row["identity"] == identity for row in evidence["responses"])
    assert read_sizes


def test_live_finder_failure_after_commit_is_receipted_as_published_unhealthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    checks = {"responses": [{"status": 200, "identity": {"archetype_model_sha256": None}}],
              "failures": ["rankings:archetype_model_sha256"]}
    _json(tmp_path / "live-finder.json", checks)
    _execute(_python("write_result"), [tmp_path, 80, "postcommit_live_finder_verification",
             "b" * 64, "github:tester/run-1", "true", "fixture", "fixture-id", 1], monkeypatch)
    receipt = load_sealed(tmp_path / "action-receipt.json")
    envelope = json.loads(capsys.readouterr().out)
    assert receipt["status"] == envelope["status"] == "published_unhealthy"
    assert receipt["exit_code"] == envelope["exit_code"] == 80
    assert receipt["live_finder_verification"] == checks
    assert "rankings:archetype_model_sha256" in receipt["failures"]
    assert receipt["publication_performed"] is True and receipt["db_writes_performed"] is True
    assert envelope["publication_performed"] is True and envelope["db_writes_performed"] is True


def test_live_finder_check_runs_after_database_verification_and_fails_protected_step() -> None:
    flow = _function("run_operation")
    assert flow.index("verify_postcommit") < flow.index("verify_live_finder") < flow.index('write_result 0 ""')
    assert "verify_live_finder || refuse 80 postcommit_live_finder_verification" in flow
    assert "verify_postcommit || refuse 80 postcommit_audit_verification" in flow
    assert "exit \"$code\"" in _function("refuse")
    assert "rollback" not in flow[flow.index("verify_postcommit"):].lower()
    steps = _workflow()["jobs"]["production-operation"]["steps"]
    step = next(step for step in steps if "< scripts/operator/actions/v3-publish-derived-products.sh" in step.get("run", ""))
    assert "set -euo pipefail" in step["run"]
    assert step.get("continue-on-error", False) is False
