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


def test_v3_derived_lifecycle_status_emits_expected_read_only_receipt(tmp_path):
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
                  printf '/srv/postgres-data\\t/var/lib/postgresql/data\\n'
                  exit 0 ;;
              esac
              if [ "$name" = 'edfinder-v3-system-search-p4-opt1' ]; then
                exit 1
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
                  printf '011_v3_system_archetype.sql\\taa11\\t2026-09-01 00:00:00+00\\n'
                  printf '013_v3_system_search_parallel.sql\\taa13\\t2026-09-02 00:00:00+00\\n'
                  printf '014_v3_watchlist.sql\\taa14\\t2026-09-03 00:00:00+00\\n' ;;
                *'FROM v3_meta.current_canonical_generation'*)
                  printf 'canonical-id\\tcanonical_live\\tv3_gen_canonical_live\\tPUBLISHED\\t4\\t2026-09-01 00:00:00+00\\n' ;;
                *'FROM v3_meta.canonical_generation ORDER BY created_at'*)
                  printf '%s\\n' 'canonical-id\tcanonical_live\tPUBLISHED\t2026-08-01 00:00:00+00\t2026-09-01 00:00:00+00\t\\N\t\\N\t\\N' ;;
                *'FROM v3_meta.current_derived_generation'*)
                  printf 'derived-id\\tratings_v4_canned\\tPUBLISHED\\tcanonical-id\\t1\\t2026-09-02 00:00:00+00\\n' ;;
                *'FROM v3_meta.derived_generation ORDER BY created_at'*)
                  printf '%s\\n' 'derived-id\tratings_v4_canned\tcanonical-id\t4\tratings-v4\tscorer-v4\tadapter-v1\tPUBLISHED\t198528286\t500000000\t2026-08-02 00:00:00+00\t2026-08-30 00:00:00+00\t2026-09-02 00:00:00+00\t\\N\t\\N' ;;
                *"to_regclass('v3_meta.derived_product')"*)
                  printf 'v3_meta.derived_product\\n' ;;
                *'FROM v3_meta.derived_product p'*)
                  printf '%s\\n' 'derived-id\tratings_v4_canned\tsystem_search\tsearch-v2\tREADY\t198528286\t2026-08-03 00:00:00+00\t2026-08-31 00:00:00+00\t\\N\t\\N\tbeef' ;;
                *"to_regclass('v3_spatial.current_spatial_generation')"*)
                  printf 'v3_spatial.current_spatial_generation\\n' ;;
                *'FROM v3_spatial.current_spatial_generation'*)
                  printf 'spatial-id\\tcanonical-id\\tdensity-v1\\tPUBLISHED\\t1\\t2026-09-03 00:00:00+00\\n' ;;
                *'FROM v3_spatial.spatial_generation ORDER BY created_at'*)
                  printf '%s\\n' 'spatial-id\tcanonical-id\tdensity-v1\tPUBLISHED\t198528286\t2026-08-04 00:00:00+00\t2026-09-01 00:00:00+00\t2026-09-03 00:00:00+00\t\\N\t\\N' ;;
                *'pg_database_size'*)
                  printf '987654321\\n' ;;
                *'pg_total_relation_size'*)
                  printf 'v3_derived\\tsystem_search\\t198528286\\t198500000\\t6000000000\\t2000000000\\t8000000000\\n'
                  printf 'v3_derived\\tsystem_archetype\\t1590000000\\t1589000000\\t30000000000\\t9000000000\\t39000000000\\n' ;;
                *'pg_indexes_size'*|*'FROM pg_index'*)
                  printf 'v3_derived\\tsystem_search\\tsystem_search_pkey\\t2000000000\\n'
                  printf 'v3_derived\\tsystem_archetype\\tsystem_archetype_key_score\\t3000000000\\n' ;;
                *"to_regclass('v3_derived.search_build_chunk')"*)
                  printf 'v3_derived.search_build_chunk\\tv3_derived.archetype_build_chunk\\n' ;;
                *"to_regclass('v3_derived.archetype_build_chunk')"*)
                  printf 'v3_derived.archetype_build_chunk\\n' ;;
                *'FROM v3_derived.search_build_chunk'*)
                  printf 'ratings_v4_canned\\t8\\t198528286\\n' ;;
                *'FROM v3_derived.archetype_build_chunk'*)
                  printf 'ratings_v4_canned\\t64\\t198528286\\n' ;;
                *'FROM v3_derived.build_chunk'*)
                  printf 'ratings_v4_canned\\t16\\t198528286\\n' ;;
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
    result = subprocess.run(
        [sys.executable, str(program)],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
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
        relation["name"] == "system_search" and relation["total_bytes"] == 8000000000
        for relation in receipt["footprint"]["relations"]
    )
    assert receipt["footprint"]["rows_by_generation"]["ratings_v4_canned"] == {
        "ratings_chunks": 16,
        "ratings_systems": 198528286,
        "search_chunks": 8,
        "search_systems": 198528286,
        "archetype_chunks": 64,
        "archetype_systems": 198528286,
    }
    assert receipt["footprint"]["host_disk"]["avail_bytes"] == 75000000000
    assert receipt["footprint"]["fresh_generation_estimate"]["method"]
    assert receipt["migration_apply_preconditions"]["ready_for_governed_plan"] is True
    assert receipt["direct_db_access_performed"] is True
