from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-system-search-f1.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
AUTHORITY = ROOT / "deploy/v3-production/target-authority.json"
IDENTITY_TOOL = ROOT / "scripts/operator/v3_schema_identity.py"
MIGRATIONS = {
    "006": ROOT / "sql/v3/migrations/006_v3_derived_product_lifecycle.sql",
    "010": ROOT / "sql/v3/migrations/010_v3_system_search_body_type_counts.sql",
    "015": ROOT / "sql/v3/migrations/015_v3_derived_product_publication.sql",
}


def test_search_production_operation_is_allowlisted_through_trusted_main():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for operation in (
        "v3-system-search-f1-start",
        "v3-system-search-f1-status",
        "v3-system-search-f1-finalize",
    ):
        assert f"          - {operation}\n" in workflow
        assert operation in workflow
    assert "trusted-main/scripts/operator/actions/v3-system-search-f1.sh" in workflow
    assert ".github/ed-new-ops-requests/*.json" in workflow
    assert "ref: main" in workflow
    assert "V3 Search start requires root or passwordless sudo for the bounded worker launch" in workflow
    assert workflow.index("V3 Search start requires root or passwordless sudo") < workflow.index(
        "trusted-main/scripts/operator/actions/v3-system-search-f1.sh"
    )


def test_search_operator_pins_exact_generation_and_migration():
    source = ACTION.read_text(encoding="utf-8")
    assert 'TARGET_GENERATION_KEY="ratings_v4_prod_p4_parallel_v1"' in source
    assert 'TARGET_GENERATION_ID="cfc25d36-3bc7-4011-a465-d6460eaaf826"' in source
    assert 'TARGET_PUBLICATION_SEQUENCE="1"' in source
    assert 'TARGET_CANONICAL_SEQUENCE="4"' in source
    assert 'TARGET_CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"' in source
    assert 'TARGET_EXPECTED_SYSTEMS="198528286"' in source
    for number, migration in MIGRATIONS.items():
        assert f'MIGRATION_{number}_NAME="{migration.name}"' in source
        expected = hashlib.sha256(migration.read_bytes()).hexdigest()
        assert f'MIGRATION_{number}_SHA="{expected}"' in source
        assert f'verify_migration "$MIGRATION_{number}_NAME" "$MIGRATION_{number}_SHA" {number}' in source
    assert 'trusted migration $label source hash mismatch' in source
    assert 'migration $label live ledger hash mismatch' in source
    assert "target generation is not PUBLISHED" in source
    assert "target generation is not the current pointer" in source


def test_search_operator_is_bounded_and_cannot_publish_or_touch_canonical():
    source = ACTION.read_text(encoding="utf-8")
    assert 'TARGET_CPUS="8"' in source
    assert 'TARGET_MEMORY="32g"' in source
    assert '--memory-swap "$TARGET_MEMORY"' in source
    assert "--pids-limit 256" in source
    assert "--restart no" in source
    assert "--generation-key ratings_v4_prod_p4_parallel_v1 --follow --poll-seconds 5" in source
    assert '--expected-manifest-sha256 "$EXPECTED_MANIFEST_SHA256"' in source
    assert "publication_performed=false" in source
    assert "canonical_writes_performed=false" in source
    assert "application_service_changes_performed=false" in source
    assert "publish_derived_generation(" not in source
    assert "publish_derived_product(" not in source
    assert "docker compose" not in source
    assert "docker restart" not in source
    # The only stop allowed is of this action's own unproven worker; no
    # application or other container is ever stopped.
    assert source.count("docker stop") == source.count('docker stop --time 60 "$WORKER"') == 1
    assert "TRUNCATE " not in source
    assert "DROP TABLE" not in source
    assert "DROP SCHEMA" not in source


def test_search_worker_dependencies_are_offline_and_pinned():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    source = ACTION.read_text(encoding="utf-8")
    assert "--require-hashes -r trusted-main/deploy/v3-production/f2d-wheels.txt" in workflow
    assert "--require-hashes -r /work/deploy/v3-production/f2d-wheels.txt" in source
    assert "--only-binary=:all:" in workflow
    assert ".v3-search-wheelhouse" in workflow
    assert ".v3-search-wheelhouse" in source
    assert "--no-index" in source
    assert "--find-links /work/.v3-search-wheelhouse" in source
    assert "--target /tmp/v3-search-deps" in source
    assert 'PYTHONPATH="/tmp/v3-search-deps:/work:/work/apps/api/src"' in source


def test_search_operator_only_verifies_its_required_schema_before_worker_launch():
    source = ACTION.read_text(encoding="utf-8")
    verify = source.index("require_search_schema")
    launch = source.index("docker run -d")
    assert verify < launch
    assert 'api_image="$(docker inspect -f' in source
    assert "active API image identity is empty" in source
    assert "scripts/operator/v3_production_migrate.py" not in source
    assert "install_target_schema_identity" not in source
    assert "apply_pending_migration" not in source
    assert 'dst=/work,readonly' in source


def test_search_identity_gate_and_start_receipt_precede_worker_launch():
    source = ACTION.read_text(encoding="utf-8")
    identity = source.index("require_f2d_operator_code_identity")
    target = source.index("require_target()")
    start = source[source.index("start_operation()") :]
    gate = start.index("run_capacity_gate")
    receipt = start.index("write_build_start_receipt")
    launch = start.index("docker run -d")
    assert identity < target
    assert gate < receipt < launch
    assert "capacity-gate-receipt.json" in source
    assert "build-start-receipt.json" in source
    assert "ed-finder/v3-build-start-receipt/v1" in source
    assert "pg_total_relation_size('v3_derived.system_search')" in source


def test_search_finalize_is_verified_receipted_and_vacuums_outside_transaction():
    source = ACTION.read_text(encoding="utf-8")
    finalize = source[source.index("finalize_operation()") : source.index('case "$ACTION"')]
    assert 'worker_state" = "exited"' in finalize
    assert 'worker_exit" = "0"' in finalize
    assert 'lifecycle" = "READY"' in finalize
    assert 'validation" = "VERIFIED"' in finalize
    assert "max(completed_at)" in finalize
    assert 'db_maintenance "VACUUM (ANALYZE) v3_derived.system_search;"' in finalize
    assert "timeout --signal=TERM 7200" in source
    maintenance = source[
        source.index("db_maintenance()") : source.index("search_vacuum_is_current()")
    ]
    assert "BEGIN" not in maintenance
    assert source.count("VACUUM (ANALYZE)") == 1
    assert "last_vacuum" in finalize
    assert "last_analyze" in finalize
    assert "last_vacuum > c.final_insert_at" in source
    assert "last_analyze > c.final_insert_at" in source
    assert "ed-finder/v3-build-final-receipt/v1" in finalize
    assert "idempotent_reverification" in finalize


def test_target_authority_reviews_transition_from_through_012_to_finder_lineage():
    import importlib.util

    spec = importlib.util.spec_from_file_location("v3_schema_identity_test", IDENTITY_TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document = module.build(ROOT)
    # Reproduce the installed prefix independently and assert both endpoints of
    # the through-012 -> through-012-014-010-011-013-015-016 transition.
    desired_document = dict(document)
    entries = document['migration_set_entries']
    stop = next(i for i, row in enumerate(entries) if row['ledger_name'] == '012_v3_spatial_pyramid_decouple.sql') + 1
    prefix = entries[:stop]
    document = {**document, 'migration_set_entries': prefix,
                'migration_set_identity': module.migration_set_identity(prefix)}
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    expected_sha = hashlib.sha256(payload).hexdigest()
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    transition = authority["schema_transition"]
    assert transition["from_schema_identity_sha256"] == expected_sha
    assert expected_sha == "4cae7d2be2e1909d468b82c6802b265118303cc0fe1c257c2f6c9e963f3a39f5"
    assert transition["from_migration_set_identity"] == document["migration_set_identity"]
    assert transition["from_migration_set_identity"] == "sha256:17263a9748eb936d3c6a7f3e3f75224a40d5e48e011276aedf511946abfff4fe"
    assert document["migration_set_entries"][-1]["ledger_name"] == "012_v3_spatial_pyramid_decouple.sql"
    assert [row['ledger_name'] for row in entries[stop:]] == [
        '014_v3_watchlist.sql',
        '010_v3_system_search_body_type_counts.sql',
        '011_v3_system_archetype.sql',
        '013_v3_system_search_parallel.sql',
        '015_v3_derived_product_publication.sql',
        '016_v3_governed_derived_purge.sql',
    ]
    assert transition["to_migration_set_identity"] == desired_document["migration_set_identity"]
    assert transition["to_migration_set_identity"] == "sha256:c274b55ca590265e3a111edb608ce7d907f7c7c5fcfad95cdde6e4f5433e95fc"
    desired_payload = (json.dumps(desired_document, indent=2, sort_keys=True) + "\n").encode()
    assert authority["external_authority"]["schema_identity_sha256"] == hashlib.sha256(desired_payload).hexdigest()
    assert authority["external_authority"]["schema_identity_sha256"] == "d7efe68932293813b4e5ec569a7b46d48ea660ef3de36b02c913110eedd7c4e6"
    compatible = authority['accepted_release_schema_compatibility']['compatible_migration_sets']
    # The transition was applied on 2026-10-18 (apply run 39113822236). The
    # accepted release is now the first F2d release, which requires 016: it
    # attests only the installed through-016 identity, never the superseded
    # through-012 source or the intermediate prefixes.
    intermediate = {
        module.migration_set_identity(entries[:prefix_length])
        for prefix_length in range(stop, len(entries))
    }
    assert transition['to_migration_set_identity'] in compatible
    assert not intermediate & set(compatible)


def test_search_status_is_read_only_and_reports_both_products():
    source = ACTION.read_text(encoding="utf-8")
    assert "ratings_completed_systems" in source
    assert "search_completed_systems" in source
    assert "search_product_state" in source
    assert "search_validation_status" in source
    assert "search_rows" in source
    status = source[source.index("status_operation()") :]
    assert "docker logs --tail 40" in status
    assert "INSERT " not in status
    assert "UPDATE " not in status
    assert "DELETE " not in status


def test_start_refuses_a_build_start_receipt_from_another_operator_identity():
    """A receipt written under a different attested identity is never resumed at start.

    The finalizers refuse such a receipt, so launching an irreversible build on it
    would strand the product; the start refuses first and names the reason.
    """
    source = (ROOT / "scripts/operator/actions/v3-system-search-f1.sh").read_text()
    block = source[source.index("def write_build_start_receipt") if "def write_build_start_receipt" in source else source.index("write_build_start_receipt() {"):]
    block = block[: block.index("receipt_seal() {")]
    assert "if receipt['f2d_operator_code_sha256'] != identity:" in block
    assert "raise SystemExit(3)" in block
    assert "written under another operator identity" in block


ACTIONS = {
    "search": ROOT / "scripts/operator/actions/v3-system-search-f1.sh",
    "archetype": ROOT / "scripts/operator/actions/v3-system-archetype.sh",
}


def _function_block(source: str, name: str) -> str:
    start = source.index(f"{name}() {{")
    end = source.index("\n}\n", start) + 3
    return source[start:end]


def _harness(action: str, extra: str) -> str:
    """Bash preamble: the action's helper functions with stubbed dependencies."""
    source = ACTIONS[action].read_text(encoding="utf-8")
    functions = "\n".join(
        _function_block(source, name)
        for name in (
            "fail", "preserve_worker_log", "preserved_worker_log_tail",
            "archiver_status", "require_archiver_healthy",
        )
    )
    settings = "\n".join(
        line for line in source.splitlines()
        if line.startswith(("CURRENT_OPERATION=", "ARCHIVER_", "WORKER=", "DB_WRITES_STATE=",
                            "mark_db_writes_possible()"))
    )
    return f"set -uo pipefail\n{settings}\n{functions}\n{extra}\n"


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_fail_prints_a_stopped_operation_result_on_stdout(action, tmp_path):
    # The workflow records stdout only; a refusal that went to stderr alone
    # left an empty receipt the operator could not act on.
    script = _harness(action, 'CURRENT_OPERATION="unit-op"\nfail \'bad "thing" here\'\n')
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False,
        env={**os.environ, "STATE_ROOT": str(tmp_path), "HOME": str(tmp_path)},
    )
    assert result.returncode == 64
    assert 'bad "thing" here' in result.stderr
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    assert receipt == {
        "schema_version": "ed-finder/operator-operation-result/v1",
        "operation": "unit-op", "status": "stopped", "read_only": False,
        "db_writes_performed": False, "db_writes_may_have_been_performed": False,
        "failures": ['bad "thing" here'],
    }


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_fail_after_a_launch_or_vacuum_reports_unknown_database_writes(action, tmp_path):
    # Once this invocation launched a worker or started VACUUM, a refusal
    # cannot prove what was committed before the stop: the receipt says so
    # (null / may-have-been-performed) instead of a hard-coded false.
    script = _harness(action, 'mark_db_writes_possible\nfail "after launch"\n')
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False,
        env={**os.environ, "STATE_ROOT": str(tmp_path), "HOME": str(tmp_path)},
    )
    assert result.returncode == 64
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    assert receipt["db_writes_performed"] is None
    assert receipt["db_writes_may_have_been_performed"] is True
    source = ACTIONS[action].read_text(encoding="utf-8")
    # The flip precedes the launch and the VACUUM, the two mutation points.
    assert source.index("mark_db_writes_possible\n  if ! docker run -d") > 0
    assert 'mark_db_writes_possible\n    db_maintenance "VACUUM (ANALYZE)' in source


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_identity_preflight_refusals_print_a_stopped_receipt(action, tmp_path):
    # The identity helper check and the attestation check run before anything
    # else; both must still produce the stdout receipt line.
    environment = {**os.environ, "HOME": str(tmp_path)}
    environment.pop("F2D_OPERATOR_CODE_SHA256_ATTESTED", None)
    result = subprocess.run(
        ["bash", str(ACTIONS[action]), "status", str(ROOT), "0" * 40],
        capture_output=True, text=True, check=False, env=environment,
    )
    assert result.returncode == 64
    assert "attested_identity_missing" in result.stderr
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    assert receipt["status"] == "stopped"
    assert receipt["operation"].endswith("-status")
    assert receipt["db_writes_performed"] is False
    assert "attested operator identity refused" in receipt["failures"][0]
    missing = subprocess.run(
        ["bash", str(ACTIONS[action]), "status", str(tmp_path), "0" * 40],
        capture_output=True, text=True, check=False, env=environment,
    )
    assert missing.returncode == 64
    receipt = json.loads(missing.stdout.strip().splitlines()[-1])
    assert receipt["failures"] == ["identity helper is missing or symlinked"]


@pytest.mark.parametrize("action", sorted(ACTIONS))
@pytest.mark.parametrize(("status", "verdict"), [
    ({"archiver_failing": False, "seconds_since_last_archived": 30, "wal_unarchived_files": 500}, "healthy"),
    ({"archiver_failing": False, "seconds_since_last_archived": 7200, "wal_unarchived_files": 12}, "healthy"),
    ({"archiver_failing": True, "seconds_since_last_archived": 5, "wal_unarchived_files": 1}, "failing"),
    ({"archiver_failing": False, "seconds_since_last_archived": 7200, "wal_unarchived_files": 51}, "silent"),
    ({"archiver_failing": False, "seconds_since_last_archived": None, "wal_unarchived_files": 51}, "silent"),
    ({"archiver_failing": False, "seconds_since_last_archived": 7200, "pg_wal_files": 51}, "invalid"),
])
def test_start_refuses_an_unhealthy_wal_archiver(action, status, verdict, tmp_path):
    # A build writes hundreds of GB of WAL through pgBackRest archive-push; a
    # failing archiver, or one silent for 30 minutes while unarchived WAL
    # (.ready files, never the recycled-segment count) piles up past 50 files,
    # would fill the data volume mid-build.
    stub = (
        "db_query() { printf '%s\\n' \"$ARCHIVER_FIXTURE\"; }\n"
        'PYTHON_BIN="$(command -v python3)"\n'
        "require_archiver_healthy && echo ARCHIVER_OK\n"
    )
    script = _harness(action, stub)
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False,
        env={**os.environ, "ARCHIVER_FIXTURE": json.dumps(status),
             "STATE_ROOT": str(tmp_path), "HOME": str(tmp_path)},
    )
    if verdict == "healthy":
        assert result.returncode == 0, result.stderr
        assert "ARCHIVER_OK" in result.stdout
    else:
        assert result.returncode == 64
        receipt = json.loads(result.stdout.strip().splitlines()[-1])
        assert receipt["status"] == "stopped"
        assert receipt["failures"][0].startswith(f"wal_archiver_unhealthy:{verdict}")


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_start_reads_archiver_health_before_the_capacity_gate_and_launch(action):
    source = ACTIONS[action].read_text(encoding="utf-8")
    start = source[source.index("start_operation()") : source.index("status_operation()")]
    status = source[source.index("status_operation()") : source.index("finalize_operation()")]
    assert start.index("require_archiver_healthy") < start.index("run_capacity_gate")
    assert start.index("run_capacity_gate") < start.index("docker run -d")
    assert "pg_stat_archiver" in source
    assert "pg_ls_archive_statusdir()" in source
    assert "LIKE '%.ready'" in source
    assert "'pg_wal_files'" not in source
    assert "archiver_status=" in status
    assert "BEGIN READ ONLY" in _function_block(source, "archiver_status")


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_crashed_worker_logs_are_preserved_before_removal_and_reported(action, tmp_path):
    source = ACTIONS[action].read_text(encoding="utf-8")
    # Every `docker rm` of the worker is preceded by a log capture; status
    # reports the newest capture so the downloadable receipt explains a crash.
    for index in [i for i in range(len(source)) if source.startswith('docker rm "$WORKER"', i)]:
        preceding = source[max(0, index - 200) : index]
        assert "preserve_worker_log" in preceding
    status = source[source.index("status_operation()") : source.index("finalize_operation()")]
    assert "preserved_worker_log_tail" in status
    stub = (
        "docker() { printf 'line one\\nline two\\n'; }\n"
        "preserve_worker_log\n"
        "ls \"$STATE_ROOT\"\n"
        "preserved_worker_log_tail\n"
    )
    result = subprocess.run(
        ["bash", "-c", _harness(action, stub)], capture_output=True, text=True, check=False,
        env={**os.environ, "STATE_ROOT": str(tmp_path), "HOME": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    captured = [path for path in tmp_path.iterdir() if path.name.startswith("worker-log.")]
    assert len(captured) == 1
    assert oct(captured[0].stat().st_mode & 0o777) == "0o600"
    assert "preserved_worker_log_tail:" in result.stdout
    assert "  line two" in result.stdout


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_start_proof_window_is_ten_minutes(action):
    source = ACTIONS[action].read_text(encoding="utf-8")
    assert "for _ in $(seq 1 300)" in source
    assert "for _ in $(seq 1 30)" not in source
    assert "sleep 2" in source


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_a_failed_worker_launch_stops_with_a_receipt_and_preserved_logs(action, tmp_path):
    # `docker run -d` failing under set -e used to exit the action before
    # fail()/preserve_worker_log ran: no stdout receipt, no logs. The launch
    # is guarded; a created-but-failed container's log is kept first.
    source = ACTIONS[action].read_text(encoding="utf-8")
    start = source[source.index("start_operation() {") : source.index("status_operation() {")]
    begin = start.index("  mark_db_writes_possible\n  if ! docker run -d")
    end = start.index("  rm -f -- \"$env_file\"\n  trap - EXIT\n", start.index("fail \"worker_launch_failed\"", begin))
    segment = start[begin:end]
    assert 'fail "worker_launch_failed"' in segment
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  run) echo "daemon refused" >&2; exit 125;;\n'
        '  inspect) exit "$INSPECT_EXIT";;\n'
        "  logs) echo created-container-log;;\n"
        "esac\n",
        encoding="utf-8",
    )
    (fake_bin / "docker").chmod(0o755)
    env_file = tmp_path / "builder.env"
    for inspect_exit, expect_log in (("1", False), ("0", True)):
        env_file.write_text("X=1\n", encoding="utf-8")
        script = _harness(
            action,
            "WORKER=w REPO_ROOT=/nonexistent SOURCE_SHA=x api_image=img\n"
            f'env_file="{env_file}"\n'
            "TARGET_GENERATION_KEY=k TARGET_GENERATION_ID=g TARGET_CPUS=1 TARGET_MEMORY=1g\n"
            "OPERATION_LABEL=l WORKER_NETWORK=n F2D_IDENTITY=i\n"
            "run_segment() {\n" + segment + "\n  echo UNREACHABLE\n}\nrun_segment\n",
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, check=False,
            env={**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                 "STATE_ROOT": str(tmp_path), "HOME": str(tmp_path),
                 "INSPECT_EXIT": inspect_exit},
        )
        assert result.returncode == 64, result.stderr
        assert "UNREACHABLE" not in result.stdout
        receipt = json.loads(result.stdout.strip().splitlines()[-1])
        assert receipt["status"] == "stopped"
        assert receipt["failures"] == ["worker_launch_failed"]
        # The launch was attempted, so the receipt cannot claim no writes.
        assert receipt["db_writes_performed"] is None
        logs = sorted(tmp_path.glob("worker-log.*.txt"))
        assert bool(logs) is expect_log
        for path in logs:
            assert "created-container-log" in path.read_text(encoding="utf-8")
            path.unlink()
        # The DSN-bearing env file never outlives a failed launch.
        assert not env_file.exists()


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_no_adjacent_duplicate_log_preservation(action):
    source = ACTIONS[action].read_text(encoding="utf-8")
    lines = [line.strip() for line in source.splitlines()]
    assert not any(
        lines[i] == "preserve_worker_log" and lines[i + 1] == "preserve_worker_log"
        for i in range(len(lines) - 1)
    )
