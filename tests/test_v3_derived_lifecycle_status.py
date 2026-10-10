import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts" / "operator" / "actions" / "v3-derived-lifecycle-status.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "chatgpt-ed-new-ops.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v3_derived_lifecycle_status_is_allowlisted_through_trusted_main_path():
    workflow = _read(WORKFLOW)

    assert "          - v3-derived-lifecycle-status\n" in workflow
    assert "|v3-derived-lifecycle-status)" in workflow
    assert "steps.request.outputs.operation == 'v3-derived-lifecycle-status'" in workflow
    assert (
        "trusted-main/scripts/operator/actions/v3-derived-lifecycle-status.sh"
        in workflow
    )
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in workflow


def test_v3_derived_lifecycle_status_has_fixed_read_only_runtime_targets():
    source = _read(ACTION)

    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    assert (
        'POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"'
        in source
    )
    workers = (
        "edfinder-ratings-v4-prod-p4",
        "edfinder-ratings-v4-prod-p4-opt1",
        "edfinder-ratings-v4-prod-p4-parallel-v1",
        "edfinder-v3-system-search-p4-opt1",
    )
    positions = [source.index(f'    "{name}",') for name in workers]
    assert positions == sorted(positions)
    assert "BEGIN READ ONLY" in source
    assert "statement_timeout" in source
    assert '"db_writes_performed": False' in source
    assert '"read_only": True' in source
    assert "ON_ERROR_STOP=1" in source


def test_v3_derived_lifecycle_status_does_not_count_derived_data_tables():
    source = _read(ACTION)

    for table in (
        "system_search",
        "system_archetype",
        "system_rating_vector",
        "body_mechanics",
        "economy_opportunity",
    ):
        assert f"count(*) FROM v3_derived.{table}" not in source


def test_v3_derived_lifecycle_status_excludes_forbidden_operations_and_secrets():
    source = _read(ACTION)

    for forbidden in (
        ".env",
        "Config.Env",
        "docker restart",
        "docker compose up",
        "docker compose down",
        "docker stop",
        "docker rm",
        "systemctl",
        "pg_dump",
        "pg_restore",
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "ALTER",
        "DROP",
        "CREATE",
        "ADMIN_TOKEN",
        "FRONTIER_CLIENT_SECRET",
        "/root/.ssh",
    ):
        assert forbidden not in source


def test_v3_derived_lifecycle_status_shell_syntax_is_valid():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    result = subprocess.run([bash, "-n", str(ACTION)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _run_status_action(
    tmp_path: Path,
    *,
    worker_inspect_failure: str = "missing",
    empty_derived_pointer: bool = False,
    derived_product_absent: bool = False,
    spatial_relation_absent: bool = False,
    database_size_query_failure: bool = False,
    unrelated_postgres_mount: bool = False,
) -> subprocess.CompletedProcess[str]:
    source = _read(ACTION)
    body = source.split("exec \"$PYTHON_BIN\" - <<'PY'\n", 1)[1].rsplit(
        "\nPY\n", 1
    )[0]
    program = tmp_path / "action.py"
    program.write_text(body, encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    hostname = fake_bin / "hostname"
    hostname.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            if [ "${1:-}" = "-f" ]; then
              printf '%s\\n' 'nb79a3d.mevnode.com'
            else
              printf '%s\\n' 'ed-finder-prod'
            fi
            """
        ),
        encoding="utf-8",
    )
    pwd = fake_bin / "pwd"
    pwd.write_text(
        "#!/bin/sh\nprintf '%s\\n' '/opt/ed-finder'\n",
        encoding="utf-8",
    )
    docker = fake_bin / "docker"
    docker.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            postgres='edfinder-v3-phase4c-full-20260827_r5-postgres'
            if [ "$1" = 'inspect' ]; then
              format="$3"
              name="$4"
              if [ "$name" = "$postgres" ] && [ "$format" = '{{.State.Running}}' ]; then
                printf '%s\\n' 'true'
                exit 0
              fi
              case "$format" in
                *'.Mounts'*)
                  if [ "$UNRELATED_POSTGRES_MOUNT" = '1' ]; then
                    printf '/srv/unrelated-data\\t/var/lib/unrelated/data\\n'
                  else
                    printf '/srv/postgres-data\\t/var/lib/postgresql/data\\n'
                  fi
                  exit 0 ;;
              esac
              if [ "$name" = 'edfinder-v3-system-search-p4-opt1' ]; then
                case "$WORKER_INSPECT_FAILURE" in
                  missing)
                    printf 'Error: No such object: %s\\n' "$name" >&2
                    exit 1 ;;
                  daemon)
                    printf '%s\\n' 'Cannot connect to the Docker daemon' >&2
                    exit 1 ;;
                esac
              fi
              printf 'exited\\tfalse\\t0\\t2026-10-01T00:00:00Z\\n'
              exit 0
            fi
            if [ "$1" = 'exec' ] && [ "$2" = "$postgres" ] && [ "$3" = 'sh' ]; then
              printf 'edfinder_v3\\tedfinder_v3_db\\n'
              exit 0
            fi
            if [ "$1" = 'exec' ] && [ "$2" = "$postgres" ] && [ "$3" = 'psql' ]; then
              previous=''
              sql=''
              for argument in "$@"; do
                if [ "$previous" = '-c' ]; then
                  sql="$argument"
                  break
                fi
                previous="$argument"
              done
              case "$sql" in
                *"current_setting('server_version')"*)
                  printf 'edfinder_v3\\tedfinder_v3_db\\t18.4\\t180004\\n' ;;
                *'FROM v3_meta.schema_migration'*)
                  printf '%s\\n' '{"migration_name":"011_v3_system_archetype.sql","migration_sha256_hex":"aa11","applied_at":"2026-09-01 00:00:00+00"}'
                  printf '%s\\n' '{"migration_name":"013_v3_system_search_parallel.sql","migration_sha256_hex":"aa13","applied_at":"2026-09-02 00:00:00+00"}'
                  printf '%s\\n' '{"migration_name":"014_v3_watchlist.sql","migration_sha256_hex":"aa14","applied_at":"2026-09-03 00:00:00+00"}' ;;
                *'FROM v3_meta.current_canonical_generation'*)
                  printf '%s\\n' '{"generation_id":"canonical-id","generation_key":"canonical_live","relation_schema":"v3_gen_canonical_live","lifecycle_state":"PUBLISHED","publication_sequence":"4","published_at":"2026-09-01 00:00:00+00"}' ;;
                *'FROM v3_meta.canonical_generation ORDER BY created_at'*)
                  printf '%s\\n' '{"generation_id":"canonical-id","generation_key":"canonical_live","lifecycle_state":"PUBLISHED","created_at":"2026-08-01 00:00:00+00","published_at":"2026-09-01 00:00:00+00","retired_at":null,"failed_at":null,"failure_reason":null}' ;;
                *'FROM v3_meta.current_derived_generation'*)
                  if [ "$EMPTY_DERIVED_POINTER" != '1' ]; then
                    printf '%s\\n' '{"derived_generation_id":"derived-id","generation_key":"ratings_v4_canned","lifecycle_state":"PUBLISHED","canonical_generation_id":"canonical-id","publication_sequence":"1","published_at":"2026-09-02 00:00:00+00"}'
                  fi ;;
                *'FROM v3_meta.derived_generation ORDER BY created_at'*)
                  printf '%s\\n' '{"derived_generation_id":"derived-id","generation_key":"ratings_v4_canned","canonical_generation_id":"canonical-id","canonical_publication_sequence":4,"mechanics_version":"ratings-v4","scorer_version":"scorer-v4","adapter_version":"adapter-v1","lifecycle_state":"PUBLISHED","expected_systems":100,"expected_bodies":500,"created_at":"2026-08-02 00:00:00+00","validated_at":"2026-08-30 00:00:00+00","published_at":"2026-09-02 00:00:00+00","failed_at":null,"failure":null}'
                  printf '%s\\n' '{"derived_generation_id":"derived-partial-id","generation_key":"ratings_v4_partial","canonical_generation_id":"canonical-id","canonical_publication_sequence":4,"mechanics_version":"ratings-v4","scorer_version":"scorer-v4","adapter_version":"adapter-v1","lifecycle_state":"FAILED","expected_systems":100,"expected_bodies":500,"created_at":"2026-08-03 00:00:00+00","validated_at":null,"published_at":null,"failed_at":"2026-08-04 00:00:00+00","failure":"phase one\\nretry\\tpending"}' ;;
                *"to_regclass('v3_meta.derived_product')"*)
                  if [ "$DERIVED_PRODUCT_ABSENT" != '1' ]; then
                    printf 'v3_meta.derived_product\\n'
                  fi ;;
                *'FROM v3_meta.derived_product p'*)
                  printf '%s\\n' '{"derived_generation_id":"derived-id","generation_key":"ratings_v4_canned","product_code":"system_search","product_version":"search-v2","lifecycle_state":"READY","expected_rows":100,"created_at":"2026-08-03 00:00:00+00","validated_at":"2026-08-31 00:00:00+00","failed_at":null,"failure":null,"validation_sha256_hex":"beef"}' ;;
                *"to_regclass('v3_spatial.current_spatial_generation')"*)
                  if [ "$SPATIAL_RELATION_ABSENT" != '1' ]; then
                    printf 'v3_spatial.current_spatial_generation\\n'
                  fi ;;
                *'FROM v3_spatial.current_spatial_generation'*)
                  printf '%s\\n' '{"spatial_generation_id":"spatial-id","canonical_generation_id":"canonical-id","pyramid_version":"density-v1","lifecycle_state":"PUBLISHED","publication_sequence":"1","published_at":"2026-09-03 00:00:00+00"}' ;;
                *'FROM v3_spatial.spatial_generation ORDER BY created_at'*)
                  printf '%s\\n' '{"spatial_generation_id":"spatial-id","canonical_generation_id":"canonical-id","pyramid_version":"density-v1","lifecycle_state":"PUBLISHED","expected_systems":100,"created_at":"2026-08-04 00:00:00+00","validated_at":"2026-09-01 00:00:00+00","published_at":"2026-09-03 00:00:00+00","failed_at":null,"failure":null}' ;;
                *'pg_database_size'*)
                  if [ "$DATABASE_SIZE_QUERY_FAILURE" = '1' ]; then
                    printf '%s\\n' 'database size query failed' >&2
                    exit 1
                  fi
                  printf '987654321\\n' ;;
                *'pg_total_relation_size'*)
                  printf '%s\\n' '{"schema":"v3_derived","name":"system_search","estimated_rows":150,"n_live_tup":150,"table_bytes":6000,"index_bytes":3000,"total_bytes":9000}'
                  printf '%s\\n' '{"schema":"v3_derived","name":"system_archetype","estimated_rows":150,"n_live_tup":150,"table_bytes":10000,"index_bytes":5000,"total_bytes":15000}' ;;
                *'pg_indexes_size'*|*'FROM pg_index'*)
                  printf '%s\\n' '{"schema":"v3_derived","name":"system_search","index_name":"system_search_pkey","index_bytes":3000}'
                  printf '%s\\n' '{"schema":"v3_derived","name":"system_archetype","index_name":"system_archetype_key_score","index_bytes":5000}' ;;
                *"to_regclass('v3_derived.search_build_chunk')"*)
                  printf 'v3_derived.search_build_chunk\\tv3_derived.archetype_build_chunk\\n' ;;
                *"to_regclass('v3_derived.archetype_build_chunk')"*)
                  printf 'v3_derived.archetype_build_chunk\\n' ;;
                *'FROM v3_derived.search_build_chunk'*)
                  printf '%s\\n' '{"generation_key":"ratings_v4_canned","chunks":"8","systems":"100"}'
                  printf '%s\\n' '{"generation_key":"ratings_v4_partial","chunks":"4","systems":"50"}' ;;
                *'FROM v3_derived.archetype_build_chunk'*)
                  printf '%s\\n' '{"generation_key":"ratings_v4_canned","chunks":"64","systems":"100"}'
                  printf '%s\\n' '{"generation_key":"ratings_v4_partial","chunks":"32","systems":"50"}' ;;
                *'FROM v3_derived.build_chunk'*)
                  printf '%s\\n' '{"generation_key":"ratings_v4_canned","chunks":"16","systems":"100","physical_bodies":"500","eligible_opportunities":"250"}'
                  printf '%s\\n' '{"generation_key":"ratings_v4_partial","chunks":"8","systems":"50","physical_bodies":"275","eligible_opportunities":"125"}' ;;
                *)
                  printf '%s\\n' "unexpected query: $sql" >&2
                  exit 2 ;;
              esac
              exit 0
            fi
            exit 2
            """
        ),
        encoding="utf-8",
    )
    df = fake_bin / "df"
    df.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            case "$*" in
              *'--output=source,fstype,size,used,avail'*)
                printf 'Filesystem Type 1B-blocks Used Available\\n'
                printf '/dev/vdb1 ext4 200000000000 125000000000 75000000000\\n' ;;
              *)
                printf '1B-blocks Used Available\\n'
                printf '300000000000 150000000000 150000000000\\n' ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    for executable in (hostname, pwd, docker, df):
        executable.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    env["WORKER_INSPECT_FAILURE"] = worker_inspect_failure
    env["EMPTY_DERIVED_POINTER"] = "1" if empty_derived_pointer else "0"
    env["DERIVED_PRODUCT_ABSENT"] = "1" if derived_product_absent else "0"
    env["SPATIAL_RELATION_ABSENT"] = "1" if spatial_relation_absent else "0"
    env["DATABASE_SIZE_QUERY_FAILURE"] = (
        "1" if database_size_query_failure else "0"
    )
    env["UNRELATED_POSTGRES_MOUNT"] = "1" if unrelated_postgres_mount else "0"
    return subprocess.run(
        [sys.executable, str(program)],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def test_v3_derived_lifecycle_status_emits_expected_read_only_receipt(tmp_path):
    result = _run_status_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    assert len(result.stdout.splitlines()) == 1
    receipt = json.loads(result.stdout)

    assert receipt["status"] == "success"
    assert receipt["all_named_workers_stopped"] is True
    assert receipt["workers"][3]["exists"] is False
    assert receipt["workers"][3]["running"] is False
    assert (
        receipt["finder_migrations_applied"][
            "010_v3_system_search_body_type_counts.sql"
        ]
        is False
    )
    assert receipt["derived"]["generation_key"] == "ratings_v4_canned"
    assert receipt["derived_products"][0]["product_code"] == "system_search"
    assert receipt["derived_products"][0]["lifecycle_state"] == "READY"
    assert receipt["spatial"]["present"] is True
    assert receipt["spatial"]["current"]["spatial_generation_id"] == "spatial-id"
    assert receipt["footprint"]["database_size_bytes"] == 987654321
    assert any(
        relation["name"] == "system_search" and relation["total_bytes"] == 9000
        for relation in receipt["footprint"]["relations"]
    )
    assert receipt["footprint"]["rows_by_generation"]["ratings_v4_canned"] == {
        "ratings_chunks": 16,
        "ratings_systems": 100,
        "ratings_physical_bodies": 500,
        "ratings_eligible_opportunities": 250,
        "search_chunks": 8,
        "search_systems": 100,
        "archetype_chunks": 64,
        "archetype_systems": 100,
    }
    assert receipt["footprint"]["rows_by_generation"]["ratings_v4_partial"] == {
        "ratings_chunks": 8,
        "ratings_systems": 50,
        "ratings_physical_bodies": 275,
        "ratings_eligible_opportunities": 125,
        "search_chunks": 4,
        "search_systems": 50,
        "archetype_chunks": 32,
        "archetype_systems": 50,
    }
    assert receipt["footprint"]["host_disk"]["avail_bytes"] == 75000000000
    assert receipt["migration_apply_preconditions"]["ready_for_governed_plan"] is True
    assert receipt["migration_apply_preconditions"]["inspection_complete"] is True
    assert receipt["direct_db_access_performed"] is True


def test_v3_derived_lifecycle_status_preserves_json_safe_failure_text(tmp_path):
    result = _run_status_action(tmp_path)

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = json.loads(result.stdout)
    partial = next(
        generation
        for generation in receipt["derived_generations"]
        if generation["generation_key"] == "ratings_v4_partial"
    )
    assert partial["failure"] == "phase one\nretry\tpending"


def test_v3_derived_lifecycle_status_treats_no_such_object_as_absent(tmp_path):
    result = _run_status_action(tmp_path, worker_inspect_failure="missing")

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = json.loads(result.stdout)
    worker = receipt["workers"][3]
    assert worker["exists"] is False
    assert worker["running"] is False
    assert "inspect_error" not in worker
    assert receipt["all_named_workers_stopped"] is True


def test_v3_derived_lifecycle_status_fails_closed_on_unknown_worker(tmp_path):
    result = _run_status_action(tmp_path, worker_inspect_failure="daemon")

    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    worker = receipt["workers"][3]
    assert worker["exists"] is None
    assert worker["running"] is None
    assert worker["status"] is None
    assert worker["inspect_error"] == "Cannot connect to the Docker daemon"
    assert receipt["all_named_workers_stopped"] is False
    assert receipt["status"] == "stopped"
    assert "worker_state_unknown" in receipt["failures"]
    assert receipt["migration_apply_preconditions"]["ready_for_governed_plan"] is False


def test_v3_derived_lifecycle_status_requires_derived_current_pointer(tmp_path):
    result = _run_status_action(tmp_path, empty_derived_pointer=True)

    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt["derived"] is None
    assert receipt["status"] == "stopped"
    assert "current_pointer_missing" in receipt["failures"]
    assert receipt["migration_apply_preconditions"]["current_pointers_recorded"] is False
    assert receipt["migration_apply_preconditions"]["ready_for_governed_plan"] is False


def test_v3_derived_lifecycle_status_requires_derived_product_table(tmp_path):
    result = _run_status_action(tmp_path, derived_product_absent=True)

    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt["derived_product_table_present"] is False
    assert receipt["derived_products"] is None
    assert receipt["status"] == "stopped"
    assert "derived_product_table_missing" in receipt["failures"]
    assert receipt["migration_apply_preconditions"]["inspection_complete"] is False
    assert receipt["migration_apply_preconditions"]["ready_for_governed_plan"] is False


def test_v3_derived_lifecycle_status_requires_spatial_current_pointer(tmp_path):
    result = _run_status_action(tmp_path, spatial_relation_absent=True)

    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt["spatial"] == {"present": False}
    assert receipt["status"] == "stopped"
    assert "current_pointer_missing" in receipt["failures"]
    assert receipt["migration_apply_preconditions"]["current_pointers_recorded"] is False
    assert receipt["migration_apply_preconditions"]["ready_for_governed_plan"] is False


def test_v3_derived_lifecycle_status_stops_on_footprint_query_failure(tmp_path):
    result = _run_status_action(tmp_path, database_size_query_failure=True)

    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "stopped"
    assert "read_only_query_failed" in receipt["failures"]
    assert receipt["migration_apply_preconditions"]["current_pointers_recorded"] is True
    assert receipt["migration_apply_preconditions"]["inspection_complete"] is False
    assert receipt["migration_apply_preconditions"]["ready_for_governed_plan"] is False


def test_v3_derived_lifecycle_status_requires_postgres_data_mount(tmp_path):
    result = _run_status_action(tmp_path, unrelated_postgres_mount=True)

    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt["footprint"]["host_disk"] == {"mount_found": False}
    assert receipt["status"] == "stopped"
    assert "postgres_data_mount_unresolved" in receipt["failures"]
    assert receipt["migration_apply_preconditions"]["inspection_complete"] is False
    assert receipt["migration_apply_preconditions"]["ready_for_governed_plan"] is False


def test_v3_derived_lifecycle_status_attributes_footprint_proportionally(tmp_path):
    result = _run_status_action(tmp_path)

    assert result.returncode == 0, result.stderr or result.stdout
    footprint = json.loads(result.stdout)["footprint"]
    attribution = footprint["measured_footprint_attribution"]
    assert attribution["note"] == (
        "proportional attribution by chunk-receipt system counts; partial "
        "generations are flagged"
    )
    search = attribution["system_search"]
    assert search["table_total_bytes"] == 9000
    assert search["receipt_product"] == "search"
    assert search["generations"] == {
        "ratings_v4_canned": {
            "attributed_bytes": 6000,
            "share": pytest.approx(2 / 3),
            "generation_complete": True,
        },
        "ratings_v4_partial": {
            "attributed_bytes": 3000,
            "share": pytest.approx(1 / 3),
            "generation_complete": False,
        },
    }
    assert "fresh_generation_estimate" not in footprint
    assert "bytes_per_generation_if_evenly_split" not in result.stdout
    assert footprint["planned_relations_not_measurable_here"] == [
        "v3_derived.system_search (post-010 row width)",
        "v3_derived.system_archetype",
        "v3_derived.system_archetype_summary",
    ]
    assert footprint["planned_relations_not_measurable_here_note"] == (
        "size these on a disposable PostgreSQL 18 sample and extrapolate; see "
        "docs/operations/v3-finder-production-rollout-state.md"
    )
