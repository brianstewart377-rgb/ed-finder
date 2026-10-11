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
ACTION = ROOT / "scripts" / "operator" / "actions" / "v3-disk-inventory.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "chatgpt-ed-new-ops.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v3_disk_inventory_is_allowlisted_through_trusted_main_path():
    workflow = _read(WORKFLOW)

    assert "          - v3-disk-inventory\n" in workflow
    assert "\n            v3-disk-inventory) ;;" in workflow
    assert "steps.request.outputs.operation == 'v3-disk-inventory'" in workflow
    assert "trusted-main/scripts/operator/actions/v3-disk-inventory.sh" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=~/.ssh/known_hosts" in workflow


def test_v3_disk_inventory_has_fixed_read_only_runtime_targets():
    source = _read(ACTION)

    assert 'EXPECTED_HOST = "ed-finder-prod"' in source
    assert 'EXPECTED_FQDN = "nb79a3d.mevnode.com"' in source
    assert (
        'POSTGRES_CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"'
        in source
    )
    assert "BEGIN READ ONLY" in source
    assert "statement_timeout" in source
    assert '"db_writes_performed": False' in source
    assert '"read_only": True' in source
    assert "ON_ERROR_STOP=1" in source
    assert "--max-depth=2" in source
    assert "DIRECTORY_USAGE_TIMEOUT_SECONDS = 300" in source


def test_v3_disk_inventory_excludes_mutating_operations():
    source = _read(ACTION)

    for forbidden in (
        "VACUUM",
        "REINDEX",
        "DROP ",
        "ALTER ",
        "CREATE ",
        "DELETE ",
        "UPDATE ",
        "TRUNCATE",
        "pg_terminate",
        "docker restart",
        "docker stop",
        "systemctl",
    ):
        assert forbidden not in source


def test_v3_disk_inventory_shell_syntax_is_valid():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable")
    result = subprocess.run([bash, "-n", str(ACTION)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _run_inventory_action(
    tmp_path: Path, *, du_failure: bool = False, root_df_failure: bool = False
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
    pwd.write_text("#!/bin/sh\nprintf '%s\\n' '/opt/ed-finder'\n", encoding="utf-8")
    docker = fake_bin / "docker"
    docker.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            postgres='edfinder-v3-phase4c-full-20260827_r5-postgres'
            if [ "$1" = 'inspect' ]; then
              format="$3"
              if [ "$format" = '{{.State.Running}}' ]; then
                printf '%s\\n' 'true'
              else
                printf '/srv/postgres-data\\t/var/lib/postgresql/data\\n'
              fi
              exit 0
            fi
            if [ "$1" = 'exec' ] && [ "$2" = "$postgres" ] && [ "$3" = 'sh' ]; then
              printf 'edfinder_v3\\tedfinder_v3_db\\n'
              exit 0
            fi
            if [ "$1" = 'exec' ] && [ "$2" = "$postgres" ] && [ "$3" = 'psql' ]; then
              shift 3
              exec psql "$@"
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
            if [ "$ROOT_DF_FAILURE" = '1' ]; then
              case "$*" in
                *'--output=size,used,avail /'*)
                  printf '%s\\n' 'root filesystem unavailable' >&2
                  exit 8 ;;
              esac
            fi
            case "$*" in
              *'--output=source,fstype,size,used,avail'*)
                printf 'Filesystem Type 1B-blocks Used Available\\n'
                printf '/dev/md1 ext4 1948000 1557000 292000\\n' ;;
              *)
                printf '1B-blocks Used Available\\n'
                printf '500000 200000 300000\\n' ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    du = fake_bin / "du"
    du.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            if [ "$DU_FAILURE" = '1' ]; then
              printf '%s\\n' 'directory scan denied' >&2
              exit 7
            fi
            printf '1345000\\t/srv/postgres-data/base\\n'
            printf '120000\\t/srv/postgres-data/pg_wal\\n'
            printf '50000\\t/srv/postgres-data/old-copy\\n'
            printf '1557000\\t/srv/postgres-data\\n'
            """
        ),
        encoding="utf-8",
    )
    psql = fake_bin / "psql"
    psql.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
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
              *'pg_replication_slots'*)
                exit 0 ;;
              *'pg_prepared_xacts'*)
                printf '%s\\n' '{"prepared_transactions":0}' ;;
              *'pg_ls_waldir'*)
                printf '%s\\n' '{"segments":3,"bytes":12}' ;;
              *"current_setting('max_wal_size')"*)
                printf '%s\\n' '{"max_wal_size":"1GB","min_wal_size":"80MB","wal_keep_size":"0","archive_mode":"off"}' ;;
              *'pg_ls_tmpdir'*)
                printf '%s\\n' '{"temp_directory_bytes":5}' ;;
              *'pg_stat_database'*)
                printf '%s\\n' '{"temp_bytes":99,"temp_files":7}' ;;
              *"current_setting('log_directory')"*)
                printf '%s\\n' '{"log_directory":"log","logging_collector":"off"}' ;;
              *'pg_stat_user_indexes'*)
                printf '%s\\n' '{"schema":"v3_derived","table":"system_rating_vector","index_name":"system_rating_vector_key","index_bytes":300,"is_unique":false,"is_primary":false,"idx_scan":0,"definition":"index definition"}' ;;
              *'pg_stat_user_tables'*)
                printf '%s\\n' '{"schema":"v3_derived","name":"system_rating_vector","n_live_tup":75,"n_dead_tup":25,"last_vacuum":null,"last_autovacuum":"2026-10-10 00:00:00+00","last_analyze":"2026-10-10 00:00:00+00","estimated_dead_fraction":0.2500}' ;;
              *'pg_total_relation_size'*)
                printf '%s\\n' '{"schema":"v3_derived","name":"system_rating_vector","relkind":"r","estimated_rows":100,"table_bytes":600,"index_bytes":300,"toast_bytes":100,"total_bytes":1000}' ;;
              *'pg_database_size'*)
                printf '%s\\n' '{"datname":"edfinder_v3_db","size_bytes":1345,"datistemplate":false,"datallowconn":true}'
                printf '%s\\n' '{"datname":"postgres","size_bytes":20,"datistemplate":false,"datallowconn":true}' ;;
              *"to_regclass('v3_derived.search_build_chunk')"*)
                printf 'v3_derived.search_build_chunk\\tv3_derived.archetype_build_chunk\\n' ;;
              *'FROM v3_derived.search_build_chunk'*)
                printf '%s\\n' '{"generation_key":"ratings_v4_live","chunks":"8","systems":"100"}' ;;
              *'FROM v3_derived.archetype_build_chunk'*)
                printf '%s\\n' '{"generation_key":"ratings_v4_live","chunks":"4","systems":"100"}' ;;
              *'FROM v3_derived.build_chunk'*)
                printf '%s\\n' '{"generation_key":"ratings_v4_live","chunks":"16","systems":"100","physical_bodies":"500","eligible_opportunities":"250"}' ;;
              *)
                printf '%s\\n' "unexpected query: $sql" >&2
                exit 2 ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    for executable in (hostname, pwd, docker, df, du, psql):
        executable.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    env["DU_FAILURE"] = "1" if du_failure else "0"
    env["ROOT_DF_FAILURE"] = "1" if root_df_failure else "0"
    return subprocess.run(
        [sys.executable, str(program)],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def test_v3_disk_inventory_emits_expected_read_only_receipt(tmp_path):
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    assert len(result.stdout.splitlines()) == 1
    receipt = json.loads(result.stdout)
    inventory = receipt["inventory"]

    assert receipt["status"] == "success"
    assert receipt["failures"] == []
    assert receipt["read_only"] is True
    assert receipt["db_writes_performed"] is False
    assert receipt["filesystem_writes_performed"] is False
    assert inventory["volume"]["avail_bytes"] == 292000
    assert {"path": "/srv/postgres-data/pg_wal", "bytes": 120000} in inventory[
        "volume_directory_usage"
    ]
    assert inventory["databases"][0]["datname"] == "edfinder_v3_db"
    assert inventory["wal"]["bytes"] == 12
    assert inventory["relations"][0]["name"] == "system_rating_vector"
    assert inventory["indexes"][0]["idx_scan"] == 0
    assert inventory["dead_tuples"][0]["estimated_dead_fraction"] == 0.25
    assert inventory["generation_attribution"]["ratings_v4_live"] == {
        "archetype_chunks": 4,
        "archetype_systems": 100,
        "ratings_chunks": 16,
        "ratings_eligible_opportunities": 250,
        "ratings_physical_bodies": 500,
        "ratings_systems": 100,
        "search_chunks": 8,
        "search_systems": 100,
    }
    assert inventory["summary"]["accounted_bytes"] == 1382
    assert inventory["summary"]["unaccounted_bytes"] == 1557000 - 1382


def test_v3_disk_inventory_reports_du_failure_without_stopping_receipt(tmp_path):
    result = _run_inventory_action(tmp_path, du_failure=True)
    assert result.returncode == 0, result.stderr or result.stdout
    receipt = json.loads(result.stdout)

    assert receipt["status"] == "success"
    assert receipt["failures"] == []
    assert receipt["inventory"]["volume_directory_usage"] == {
        "du_failed": "directory scan denied"
    }
    assert receipt["inventory"]["summary"]["largest_unaccounted_directories"] == []


def test_v3_disk_inventory_preserves_volume_when_root_df_fails(tmp_path):
    result = _run_inventory_action(tmp_path, root_df_failure=True)
    assert result.returncode == 1
    receipt = json.loads(result.stdout)

    assert receipt["status"] == "stopped"
    assert receipt["failures"] == ["read_only_query_failed"]
    assert receipt["inventory"]["volume"]["used_bytes"] == 1557000
    assert receipt["inventory"]["root_filesystem"] == {
        "root_filesystem_failed": "disk_usage_command_failed"
    }
    assert receipt["inventory"]["summary"]["unaccounted_bytes"] == 1557000 - 1382
