import heapq
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
    tmp_path: Path,
    *,
    du_failure: bool = False,
    root_df_failure: bool = False,
    volume_df_failure: bool = False,
    du_layout: str = "default",
    du_churn: bool = False,
    du_churn_once: bool = False,
    du_churn_then_deny: bool = False,
    du_permission_denied: bool = False,
    tablespace_present: bool = False,
    mount_point_failure: bool = False,
    wal_outside_pgdata: bool = False,
    df_used_drift: int = 0,
    base_scan_denied: bool = False,
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
    readlink = fake_bin / "readlink"
    readlink.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            # -f <path>; the fixture's pg_wal is a real directory inside PGDATA unless
            # WAL_OUTSIDE_PGDATA asks for the relocated case.
            target="$2"
            case "$target" in
              */pg_wal)
                if [ "$WAL_OUTSIDE_PGDATA" = '1' ]; then
                  printf '%s\\n' '/mnt/wal/pg_wal'
                else
                  printf '%s\\n' "$target"
                fi ;;
              *)
                printf '%s\\n' "$target" ;;
            esac
            """
        ),
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
              if [ "$format" = '{{.State.Running}}' ]; then
                printf '%s\\n' 'true'
              else
                printf '/var/lib/docker/volumes/edfinder-pgdata/_data\\t/var/lib/postgresql\\n'
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
            if [ "$VOLUME_DF_FAILURE" = '1' ]; then
              case "$*" in
                *'--output=source,fstype,size,used,avail'*)
                  printf '%s\\n' 'volume unavailable' >&2
                  exit 8 ;;
              esac
            fi
            case "$*" in
              *'--output=source,fstype,size,used,avail'*)
                printf 'Filesystem Type 1B-blocks Used Available\\n'
                printf '/dev/md1 ext4 1948000 1557000 292000\\n' ;;
              *'--output=target'*)
                if [ "$MOUNT_POINT_FAILURE" = '1' ]; then
                  printf '%s\\n' 'cannot resolve mount point' >&2
                  exit 9
                fi
                printf 'Mounted on\\n'
                printf '/\\n' ;;
              *'--output=used'*)
                printf 'Used\\n'
                # The action reads --output=used three times: before the root scan,
                # immediately after it, and once more to close the window.
                # DF_USED_DRIFT makes only the THIRD -- the closing -- reading differ,
                # which is the only way a test can tell which reading a summary figure
                # was derived from.
                calls=0
                if [ -f "$DF_USED_STAMP" ]; then
                  calls="$(cat "$DF_USED_STAMP")"
                fi
                calls="$(( calls + 1 ))"
                printf '%s' "$calls" > "$DF_USED_STAMP"
                if [ "$calls" -ge 3 ]; then
                  printf '%s\\n' "$(( 1557000 + DF_USED_DRIFT ))"
                else
                  printf '1557000\\n'
                fi ;;
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
            vol='/var/lib/docker/volumes/edfinder-pgdata/_data'
            data="$vol/18/docker"
            # Ordinary PostgreSQL churn: a WAL segment recycled mid-scan. du still
            # totals everything else and exits nonzero.
            if [ "$DU_CHURN_THEN_DENY" = '1' ]; then
              if [ ! -e "$DU_CHURN_STAMP" ]; then
                : > "$DU_CHURN_STAMP"
                printf "du: cannot access '%s/pg_wal/0000000100000ABC': No such file or directory\\n" "$data" >&2
              else
                printf "du: cannot read directory '/var/lib/private': Permission denied\\n" >&2
              fi
              CHURN_EXIT=1
            elif [ "$DU_CHURN_ONCE" = '1' ] && [ ! -e "$DU_CHURN_STAMP" ]; then
              : > "$DU_CHURN_STAMP"
              printf "du: cannot access '%s/pg_wal/0000000100000ABC': No such file or directory\\n" "$data" >&2
              CHURN_EXIT=1
            elif [ "$DU_CHURN" = '1' ]; then
              printf "du: cannot access '%s/pg_wal/0000000100000ABC': No such file or directory\\n" "$data" >&2
              CHURN_EXIT=1
            else
              CHURN_EXIT=0
            fi
            if [ "$DU_PERMISSION_DENIED" = '1' ]; then
              printf "du: cannot read directory '/var/lib/private': Permission denied\\n" >&2
              CHURN_EXIT=1
            fi
            # Real `du` semantics: --max-depth=N shows directories at most N levels
            # below the scanned root, so the depth-2 scan from / emits /var/lib but
            # never /var/lib/docker. Only the drill-down's depth-1 calls reach it.
            case "$*" in
              *"--max-depth=0 $data")
                printf '1465000\\t%s\\0' "$data" ;;
              *"--max-depth=1 $data/base")
                if [ "$BASE_SCAN_DENIED" = '1' ]; then
                  printf "du: cannot read directory '%s/base/16384': Permission denied\\n" "$data" >&2
                  exit 1
                fi
                # base/ in du's own metric. 16384 and 5 are the live OIDs; 16999 is
                # an orphaned directory from a dropped database, and 200 bytes sit
                # directly in base/. The live figures deliberately exceed the
                # pg_database_size totals (1,320,000 and 8,000) and pg_ls_tmpdir's 5,
                # because du counts allocated blocks and PostgreSQL sums st_size --
                # the metric difference this breakdown exists to stop reporting as
                # orphaned storage.
                printf '1321000\\t%s/base/16384\\0' "$data"
                printf '8200\\t%s/base/5\\0' "$data"
                printf '500\\t%s/base/16999\\0' "$data"
                printf '100\\t%s/base/pgsql_tmp\\0' "$data"
                printf '1330000\\t%s/base\\0' "$data" ;;
              *"--max-depth=1 $data")
                printf '1330000\\t%s/base\\0' "$data"
                printf '120000\\t%s/pg_wal\\0' "$data"
                printf '8000\\t%s/global\\0' "$data"
                printf '4000\\t%s/pg_stat\\0' "$data"
                printf '1465000\\t%s\\0' "$data" ;;
              *'--max-depth=1 /var/lib/docker/volumes')
                printf '1465000\\t%s\\0' "$vol"
                printf '1470000\\t/var/lib/docker/volumes\\0' ;;
              *'--max-depth=1 /var/lib/docker/overlay2')
                printf '1000\\t/var/lib/docker/overlay2/aaaa\\0'
                printf '1000\\t/var/lib/docker/overlay2/bbbb\\0'
                printf '38000\\t/var/lib/docker/overlay2\\0' ;;
              *'--max-depth=1 /var/lib/docker')
                printf '1470000\\t/var/lib/docker/volumes\\0'
                printf '38000\\t/var/lib/docker/overlay2\\0'
                printf '1510000\\t/var/lib/docker\\0' ;;
              *'--max-depth=1 /var/lib')
                printf '1510000\\t/var/lib/docker\\0'
                printf '5000\\t/var/lib/apt\\0'
                printf '1515000\\t/var/lib\\0' ;;
              *'--max-depth=1 /var')
                if [ "$DU_LAYOUT" = 'direct_files' ]; then
                  printf '1465000\\t/var/lib\\0'
                  printf '80000\\t/var/log\\0'
                  printf '1545000\\t/var\\0'
                else
                  printf '1515000\\t/var/lib\\0'
                  printf '30000\\t/var/log\\0'
                  printf '1545000\\t/var\\0'
                fi ;;
              *'--max-depth=1 /var/log')
                # 70,000 bytes sit directly in /var/log; the largest child is 10,000.
                printf '10000\\t/var/log/journal\\0'
                printf '80000\\t/var/log\\0' ;;
              *'--max-depth=1 /')
                printf '1545000\\t/var\\0'
                printf '12000\\t/home\\0'
                printf '1557000\\t/\\0' ;;
              *'--max-depth=2'*)
                printf '1515000\\t/var/lib\\0'
                printf '30000\\t/var/log\\0'
                printf '1545000\\t/var\\0'
                printf '12000\\t/home/claude\\0'
                printf '12000\\t/home\\0'
                printf '1557000\\t/\\0' ;;
              *)
                printf '%s\\n' "unexpected du: $*" >&2
                exit 9 ;;
            esac
            exit "$CHURN_EXIT"
            """
        ),
        encoding="utf-8",
    )
    # The drill-down bounds its child listing with a `du | sort -z | head -z` pipeline,
    # so the stub needs a real shell. The fake `du` on PATH is picked up by it, and
    # sort/head come from the system — which is what we want to exercise.
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
              *'data_directory'*)
                printf '%s\\n' '/var/lib/postgresql/18/docker' ;;
              *'AS non_default_count FROM pg_tablespace'*)
                if [ "$TABLESPACE_PRESENT" = '1' ]; then
                  printf '%s\\n' '{"non_default_count":"1"}'
                else
                  printf '%s\\n' '{"non_default_count":"0"}'
                fi ;;
              *'pg_tablespace'*)
                if [ "$TABLESPACE_PRESENT" = '1' ]; then
                  printf '%s\\n' '{"spcname":"fast_ssd","location":"/mnt/ssd/pgtbs","size_bytes":40000}'
                fi ;;
              *'pg_replication_slots'*)
                exit 0 ;;
              *'pg_prepared_xacts'*)
                printf '%s\\n' '{"prepared_transactions":0}' ;;
              *'pg_ls_waldir'*)
                printf '%s\\n' '{"segments":3,"bytes":118000}' ;;
              *"current_setting('max_wal_size')"*)
                printf '%s\\n' '{"max_wal_size":"1GB","min_wal_size":"80MB","wal_keep_size":"0","archive_mode":"off"}' ;;
              *'pg_ls_tmpdir'*)
                printf '%s\\n' '{"temp_directory_bytes":5}' ;;
              *'stats_reset'*)
                printf '%s\\n' '{"stats_reset":"2026-09-01 00:00:00+00","window_age":"40 days","stats_never_reset":false}' ;;
              *'pg_stat_database'*)
                printf '%s\\n' '{"temp_bytes":99,"temp_files":7}' ;;
              *"current_setting('log_directory')"*)
                printf '%s\\n' '{"log_directory":"log","logging_collector":"off"}' ;;
              *'pg_stat_user_indexes'*)
                printf '%s\\n' '{"schema":"v3_derived","table":"system_rating_vector","index_name":"system_rating_vector_key","index_bytes":300,"is_unique":false,"is_primary":false,"idx_scan":0,"definition":"index definition"}' ;;
              *'pg_stat_user_tables'*)
                printf '%s\\n' '{"schema":"v3_derived","name":"system_rating_vector","n_live_tup":75,"n_dead_tup":25,"last_vacuum":null,"last_autovacuum":"2026-10-10 00:00:00+00","last_analyze":"2026-10-10 00:00:00+00","estimated_dead_fraction":0.2500}' ;;
              *'pg_total_relation_size'*)
                printf '%s\\n' '{"schema":"v3_derived","name":"system_rating_vector","relkind":"r","estimated_rows":100,"table_bytes":600,"heap_bytes":500,"index_bytes":300,"toast_bytes":100,"total_bytes":1000}' ;;
              *'SELECT oid::text AS oid, datname FROM pg_database'*)
                printf '%s\\n' '{"oid":"16384","datname":"edfinder_v3_db"}'
                printf '%s\\n' '{"oid":"5","datname":"postgres"}' ;;
              *'AS operating_bytes FROM pg_database'*)
                printf '%s\\n' '{"database_count":"2","total_bytes":"1328000","operating_bytes":"1320000"}' ;;
              *'pg_database_size'*)
                printf '%s\\n' '{"datname":"edfinder_v3_db","size_bytes":1320000,"datistemplate":false,"datallowconn":true,"operating":true}'
                printf '%s\\n' '{"datname":"postgres","size_bytes":8000,"datistemplate":false,"datallowconn":true,"operating":false}' ;;
              *"to_regclass('v3_derived.search_build_chunk')"*)
                printf 'v3_derived.search_build_chunk\\tv3_derived.archetype_build_chunk\\n' ;;
              *'FROM v3_derived.search_build_chunk'*)
                printf '%s\\n' '{"generation_key":"ratings_v4_live","published":true,"chunks":"8","systems":"100"}' ;;
              *'FROM v3_derived.archetype_build_chunk'*)
                printf '%s\\n' '{"generation_key":"ratings_v4_live","published":true,"chunks":"4","systems":"100"}' ;;
              *'FROM v3_derived.build_chunk'*)
                printf '%s\\n' '{"generation_key":"ratings_v4_live","published":true,"chunks":"16","systems":"100","physical_bodies":"500","eligible_opportunities":"250"}'
                printf '%s\\n' '{"generation_key":"aaa_superseded","published":false,"chunks":"2","systems":"10","physical_bodies":"20","eligible_opportunities":"5"}' ;;
              *)
                printf '%s\\n' "unexpected query: $sql" >&2
                exit 2 ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    for executable in (hostname, pwd, readlink, docker, df, du, psql):
        executable.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    env["DU_FAILURE"] = "1" if du_failure else "0"
    env["ROOT_DF_FAILURE"] = "1" if root_df_failure else "0"
    env["VOLUME_DF_FAILURE"] = "1" if volume_df_failure else "0"
    env["DU_LAYOUT"] = du_layout
    env["DU_CHURN"] = "1" if du_churn else "0"
    env["DU_CHURN_ONCE"] = "1" if du_churn_once else "0"
    env["DU_CHURN_THEN_DENY"] = "1" if du_churn_then_deny else "0"
    env["DU_CHURN_STAMP"] = str(tmp_path / "du-churn-stamp")
    env["DU_PERMISSION_DENIED"] = "1" if du_permission_denied else "0"
    env["TABLESPACE_PRESENT"] = "1" if tablespace_present else "0"
    env["MOUNT_POINT_FAILURE"] = "1" if mount_point_failure else "0"
    env["WAL_OUTSIDE_PGDATA"] = "1" if wal_outside_pgdata else "0"
    env["BASE_SCAN_DENIED"] = "1" if base_scan_denied else "0"
    env["DF_USED_DRIFT"] = str(df_used_drift)
    env["DF_USED_STAMP"] = str(tmp_path / "df-used-stamp")
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
    assert {"path": "/var/log", "bytes": 30000} in inventory["volume_directory_usage"]
    assert inventory["databases"][0]["datname"] == "edfinder_v3_db"
    assert inventory["wal"]["bytes"] == 118000
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
    # The fixture is internally coherent: 1,320,000 + 8,000 databases, 118,000 WAL,
    # 5 temp, against a 1,330,000 base/ and a 120,000 pg_wal.
    assert inventory["summary"]["accounted_bytes"] == 1446005
    assert inventory["summary"]["unaccounted_bytes"] == 1557000 - 1446005
    assert inventory["postgres_data_directory_usage"]["bytes"] == 1465000
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    assert inventory["postgres_data_directory"] == {
        "container_path": "/var/lib/postgresql/18/docker",
        "host_path": pgdata,
        "mount_destination": "/var/lib/postgresql",
    }
    assert {"path": f"{pgdata}/base", "bytes": 1330000} in (
        inventory["postgres_data_directory_usage"]["children"]
    )
    assert inventory["postgres_data_directory_bracket"]["drift_bytes"] == 0


def test_v3_disk_inventory_fails_closed_when_the_directory_scan_fails(tmp_path):
    """The directory scan is the only evidence that locates unaccounted usage.

    Without it the receipt cannot answer its own question, so it must not be
    presented as a complete inventory.
    """
    result = _run_inventory_action(tmp_path, du_failure=True)
    assert result.returncode == 1, result.stderr or result.stdout
    receipt = json.loads(result.stdout)

    assert receipt["status"] == "stopped"
    assert receipt["failures"] == ["read_only_query_failed"]
    usage = receipt["inventory"]["volume_directory_usage"]
    reason = usage["volume_directory_usage_failed"]
    assert reason.split(":", 1)[0] in {
        "directory_total_failed",
        "directory_usage_failed",
        "drill_down_failed",
    }, reason
    assert "directory scan denied" in reason


def test_v3_disk_inventory_scans_the_whole_filesystem_not_only_the_pg_volume():
    """`df` measures the filesystem, so `du` must scan the filesystem.

    The data directory is a Docker-volume subdirectory of the same device, so
    scanning only that subdirectory would hide every sibling consumer — Docker
    layers, logs, backups — which is exactly the unaccounted usage this action
    exists to find.
    """
    source = _read(ACTION)

    assert '["df", "--output=target", mount_source]' in source
    assert '["du", "--null", "-x", "-B1", "--max-depth=2", usage_root]' in source
    assert '"volume_directory_usage_root"' in source


def test_v3_disk_inventory_records_the_index_statistics_window():
    """`idx_scan` is cumulative since the last reset, so the window must be reported."""
    source = _read(ACTION)

    assert "stats_reset::text AS stats_reset" in source
    assert '"index_statistics_window"' in source


def test_v3_disk_inventory_reads_toast_from_the_toast_relation():
    """pg_table_size already includes TOAST, so the old subtraction was always zero."""
    source = _read(ACTION)

    assert "c.reltoastrelid <> 0" in source
    assert "pg_total_relation_size(c.reltoastrelid)" in source
    assert "pg_relation_size(c.oid)::bigint AS heap_bytes" in source


def test_v3_disk_inventory_candidates_are_a_non_overlapping_partition(tmp_path):
    """Ancestors of the database must not be offered as unaccounted usage.

    `du --max-depth=2` reports a cumulative total for every directory at depth <= 2, so
    on the production layout `/var/lib` and `/var/lib/docker` both contain the whole
    ~1.3 TB database. Ranking those rows directly makes the database's own ancestors the
    largest "unaccounted" directories, which tells the operator nothing about where the
    remaining usage is -- the single question this action exists to answer. Each row must
    therefore report only the bytes no other row reports, with the measured
    data-directory size removed from whichever row contains it.
    """
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]
    candidates = summary["largest_unaccounted_directories"]
    paths = [row["path"] for row in candidates]
    by_path = {row["path"]: row["exclusive_bytes"] for row in candidates}

    # The database is 1,465,000 of the volume's 1,557,000 used bytes. Every candidate
    # OUTSIDE the data directory must be smaller than the remaining 92,000, which no
    # cumulative ancestor total is. (Inside-PGDATA rows are bounded by PGDATA's own
    # size instead, and are asserted separately below.)
    outside = [row for row in candidates if not row["inside_data_directory"]]
    assert max(row["exclusive_bytes"] for row in outside) <= 1557000 - 1465000
    # /var/lib is the deepest row a depth-2 scan from / can emit, and it holds the
    # database; only its 50,000 of non-database bytes survive the subtraction.
    assert by_path["/var/lib"] == 50000
    assert by_path["/var/log"] == 30000
    assert by_path["/home/claude"] == 12000
    # The data directory itself is never a candidate, and the only rows inside it are
    # the PostgreSQL directories accounted_bytes does not cover (see the test below).
    data_dir = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    assert data_dir not in paths
    assert all(
        row["inside_data_directory"]
        for row in candidates
        if row["path"].startswith(f"{data_dir}/")
    )
    # The partition is exact: the rows outside the data directory plus the database
    # are the used bytes.
    assert summary["non_database_directory_bytes"] == 1557000 - 1465000
    assert (
        summary["non_database_directory_bytes"] + summary["postgres_data_directory_bytes"]
        == summary["volume_used_bytes"]
    )
    # df and du measure different things; the gap is reported, not folded into a row.
    assert summary["directory_scan_root_bytes"] == 1557000
    assert summary["filesystem_minus_directory_scan_bytes"] == 0
    assert summary["filesystem_minus_directory_scan_is_significant"] is False


def test_v3_disk_inventory_drill_down_names_the_owning_directory(tmp_path):
    """The partition alone cannot name the consumer; the drill-down must.

    GNU `du --max-depth=N` shows directories at most N levels below the scanned root,
    so a depth-2 scan from `/` stops at `/var/lib` and can never emit `/var/lib/docker`,
    let alone the layer store beneath it. The partition is therefore correct but
    uninformative: it says 50,000 bytes are somewhere under /var/lib. Descending one
    bounded level at a time, subtracting the database wherever it appears, is what turns
    that into an actionable answer.
    """
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    section = json.loads(result.stdout)["inventory"]["non_database_drill_down"]
    chain = section["chain"]
    followed = [step["directory"] for step in chain]

    # 0.25 % of the 1,557,000 used bytes.
    assert section["floor_bytes"] == 3892
    # The walk reaches the layer store, which the flat scan could not name at all.
    assert followed == [
        "/",
        "/var",
        "/var/lib",
        "/var/lib/docker",
        "/var/lib/docker/overlay2",
    ]
    assert chain[-1]["followed"] is None
    assert chain[-1]["stop_reason"] == "no_child_above_floor"
    assert section["max_steps"] == 8
    assert len(chain) <= section["max_steps"]

    # At each step the database is subtracted from whichever child contains it, so the
    # walk follows the non-database bytes rather than being dragged into the database.
    docker = next(step for step in chain if step["directory"] == "/var/lib/docker")
    volumes = next(
        child for child in docker["children"] if child["path"].endswith("/volumes")
    )
    assert volumes["contains_database"] is True
    assert volumes["bytes_excluding_database"] == 1470000 - 1465000
    assert docker["followed"] == "/var/lib/docker/overlay2"


def test_v3_disk_inventory_fails_closed_without_the_data_directory_measurement():
    """The subtraction needs a measured size, not an assumed one.

    `pg_database_size` counts logical relation bytes, so using it to subtract the
    database from a `du` partition would leave a residue that reappears as phantom
    unaccounted usage. The data directory is measured with the same tool as the volume.
    """
    source = _read(ACTION)

    assert '["du", "--null", "-x", "-B1", "--max-depth=1", pgdata_host]' in source
    assert "def host_pgdata(" in source
    assert "current_setting('data_directory')" in source
    assert "postgres_data_directory_outside_mount" in source
    assert "postgres_data_directory_usage_failed" in source
    assert "postgres_data_directory_usage_unavailable" in source
    assert "volume_directory_usage_unavailable" in source
    # The partition, not a prefix blocklist, is what keeps accounted bytes out.
    assert "def exclusive_usage(" in source
    assert "accounted_prefixes" not in source


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
    assert receipt["inventory"]["summary"]["unaccounted_bytes"] == 1557000 - 1446005


def test_v3_disk_inventory_stops_cleanly_when_the_volume_measurement_failed(tmp_path):
    """A failed volume `df` must stop the section, not raise KeyError out of it.

    The mount can resolve and the `df` on it still fail, which leaves
    inventory["volume"] as an error object. Reading used_bytes from it raises KeyError,
    which is not RuntimeError and so escapes the section's handler — the action would
    scan for minutes and then die with a traceback where a structured stopped receipt
    belongs, giving the operator neither the inventory nor a reason.
    """
    result = _run_inventory_action(tmp_path, volume_df_failure=True)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    # Still exactly one line of JSON on stdout, not a partial write plus a traceback.
    assert len(result.stdout.splitlines()) == 1
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "stopped"
    inventory = receipt["inventory"]
    assert "volume_failed" in inventory["volume"]
    # The guard lives in the drill-down section, which is where the used_bytes lookup
    # is, so the root scan above it is not overwritten by this failure.
    assert (
        inventory["non_database_drill_down"]["non_database_drill_down_failed"]
        == "volume_measurement_unavailable"
    )


def test_v3_disk_inventory_stops_when_a_directory_owns_its_bytes_directly(tmp_path):
    """Following the largest child blindly can name the wrong owner.

    If /var/log holds 70,000 bytes directly in its own files and its largest
    subdirectory holds 10,000, the bytes are owned by /var/log — descending would report
    the 10,000 subdirectory as the consumer and send the operator to the wrong place.
    """
    result = _run_inventory_action(tmp_path, du_layout="direct_files")
    assert result.returncode == 0, result.stderr or result.stdout
    chain = json.loads(result.stdout)["inventory"]["non_database_drill_down"]["chain"]

    last = chain[-1]
    assert last["directory"] == "/var/log"
    assert last["own_file_bytes"] == 70000
    assert last["followed"] is None
    assert last["stop_reason"] == "directory_owns_more_directly_than_any_child"
    # The child was above the floor, so only the direct-ownership check stopped it.
    assert last["children"][0]["bytes_excluding_database"] == 10000
    assert last["children"][0]["bytes_excluding_database"] >= 3892


def test_v3_disk_inventory_keeps_unaccounted_pgdata_directories_as_candidates(tmp_path):
    """Subtracting the whole data directory removes more than accounted_bytes covers.

    accounted_bytes is the databases (base/), WAL (pg_wal) and the temp directories.
    PGDATA also holds `global`, `pg_xact`, `pg_multixact` and often log files, which
    stayed inside unaccounted_bytes while vanishing from every candidate — so the
    candidate list could not locate the value it claimed to explain.
    """
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    by_path = {
        row["path"]: row for row in summary["largest_unaccounted_directories"]
    }

    assert by_path[f"{pgdata}/global"]["exclusive_bytes"] == 8000
    assert by_path[f"{pgdata}/global"]["inside_data_directory"] is True
    # Files directly at PGDATA's root: 1,465,000 total minus 1,458,000 of children.
    root_files = f"{pgdata} (files directly in this directory)"
    assert by_path[root_files]["exclusive_bytes"] == 3000
    assert by_path[root_files]["inside_data_directory"] is True
    # pg_ls_waldir() reported 12 bytes of the 120,000-byte pg_wal directory, because it
    # lists only top-level ordinary files; the rest (archive_status, summaries) is
    # inside neither wal_bytes nor the accounted children, so it is its own candidate.
    wal_unlisted = (
        f"{pgdata}/pg_wal (subdirectories and files pg_ls_waldir does not list)"
    )
    assert by_path[wal_unlisted]["exclusive_bytes"] == 120000 - 118000
    assert by_path[wal_unlisted]["inside_data_directory"] is True
    # base/: the orphaned OID directory by PATH, and the 200 bytes sitting directly in
    # base/ as their own row. Not one lump remainder, and not inflated by the
    # du-versus-pg_database_size metric difference, which is its own summary term.
    orphan = f"{pgdata}/base/16999 (not a live database directory)"
    assert by_path[orphan]["exclusive_bytes"] == 500
    assert by_path[orphan]["inside_data_directory"] is True
    base_other = (
        f"{pgdata}/base (files directly in this directory, and entries the row cap "
        "dropped)"
    )
    assert by_path[base_other]["exclusive_bytes"] == 200
    # 18,995 under the old mixed-metric arithmetic; 1,295 of that was block rounding.
    assert summary["unaccounted_inside_data_directory_bytes"] == 17700
    assert summary["database_size_metric_difference_bytes"] == 1295
    # And the whole partition reconciles against the figure it explains, with the
    # metrological term named rather than hidden inside a candidate.
    assert (
        summary["non_database_directory_bytes"]
        + summary["unaccounted_inside_data_directory_bytes"]
        + summary["database_size_metric_difference_bytes"]
        == summary["unaccounted_bytes_at_directory_scan"]
    )
    assert summary["candidates_partition_unaccounted_at_scan"] is True
    # No drift in this fixture, so the two windows agree and the closing figure is the
    # same value.
    assert summary["post_scan_volume_drift_bytes"] == 0
    assert summary["unaccounted_bytes"] == summary["unaccounted_bytes_at_directory_scan"]
    # base/ and pg_wal are already in accounted_bytes and must not be listed again.
    assert f"{pgdata}/base" not in by_path
    assert f"{pgdata}/pg_wal" not in by_path
    # Rows outside the data directory are flagged as such, and excluded from the
    # non-database total, so the two figures never double count.
    assert by_path["/var/log"]["inside_data_directory"] is False
    assert summary["non_database_directory_bytes"] == 92000


def test_v3_disk_inventory_does_not_claim_a_per_index_statistics_window(tmp_path):
    """A zero idx_scan is not evidence an index is unused.

    pg_stat_reset_single_table_counters zeroes one index's idx_scan without touching
    pg_stat_database.stats_reset, and PostgreSQL records no per-index reset time.
    Presenting the database-wide value as the index's window would pair a freshly reset
    index with a months-old age — and an unused index is exactly what someone hunting
    reclaimable space would drop.
    """
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    window = json.loads(result.stdout)["inventory"]["index_statistics_window"]

    assert window["scope"] == "database"
    assert window["per_index_window_known"] is False
    assert "pg_stat_reset_single_table_counters" in window["note"]
    assert "not evidence" in window["note"]
    # The database-wide value is still reported, just not as the index's window.
    assert window["stats_reset"] == "2026-09-01 00:00:00+00"


def test_v3_disk_inventory_shares_one_scan_budget_within_the_job_timeout(tmp_path):
    """Per-call timeouts alone can exceed the operator job's 40-minute limit.

    Four fixed scans plus eight drill-down steps at the 300 s per-call limit is 60
    minutes, so a valid but slow production inventory could be killed before emitting
    any receipt. One shared wall-clock budget makes the walk stop and say why instead.
    """
    source = _read(ACTION)

    assert "DIRECTORY_SCAN_BUDGET_SECONDS = 1_500" in source
    assert "class ScanBudget" in source
    assert "def call_timeout(" in source
    assert "scan_budget_exhausted" in source
    assert "directory_scan_budget_exhausted" in source
    # The budget is created once and threaded through every scan.
    assert (
        source.count(
            "scan_budget = ScanBudget("
            "DIRECTORY_SCAN_BUDGET_SECONDS, RECONCILE_RESERVE_SECONDS)"
        )
        == 1
    )
    assert "budget=scan_budget" in source
    # The bracket closes around the drill-down, not only the filesystem scan.
    assert "bytes_after_drill_down" in source
    assert "span_drift_bytes" in source


def test_v3_disk_inventory_reconciles_pgdata_after_the_drill_down(tmp_path):
    """The drill-down runs further scans after the first bracket closed.

    Those scans compare current ancestor totals against one fixed data-directory size,
    so a database that grew in between has its growth mislabelled as non-database usage
    (and the walk can be sent into the PostgreSQL volume), while shrinkage hides real
    sibling usage — with the receipt still reporting success.
    """
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    bracket = json.loads(result.stdout)["inventory"]["postgres_data_directory_bracket"]

    assert bracket["bytes_before_filesystem_scan"] == 1465000
    assert bracket["bytes_after_filesystem_scan"] == 1465000
    assert bracket["bytes_after_drill_down"] == 1465000
    assert bracket["drift_bytes"] == 0
    assert bracket["span_drift_bytes"] == 0
    assert bracket["tolerance_bytes"] == 1 << 30


def test_v3_disk_inventory_reserves_budget_for_the_closing_reconciliation(tmp_path):
    """A walk that spent the whole budget must not take the reconciliation with it.

    The reconciliation scan is mandatory, so if the drill-down could consume the entire
    budget the closing `du_total` would raise and the section handler would overwrite
    `volume_directory_usage` -- losing both the successful filesystem scan and the
    chain's `scan_budget_exhausted` stop reason. That is exactly the partial evidence
    the budget exists to preserve, so the walk stops with the reserve unspent, and the
    reconciliation lives in its own section where a failure cannot erase the scans.
    """
    source = _read(ACTION)

    # The reserve is the closing phase's FULL per-call allowance, once per scan it
    # makes: reserving less would leave a mandatory scan running against a shortened
    # timeout, which is just a different way of failing it. The closing phase makes
    # TWO scans -- the PGDATA re-read and the depth-1 breakdown of base/ that keeps the
    # base remainder in a single metric.
    assert (
        "RECONCILE_RESERVE_SECONDS = 2 * DIRECTORY_USAGE_TIMEOUT_SECONDS" in source
    )
    # The budget OWNS the reserve. Passing it per call site meant forgetting it at four
    # of them, which unreserved the reserve without changing a line that mentioned it,
    # so there must be no per-call reserve argument left to forget.
    assert "reserve_seconds" not in source.split("def du_rows(")[1].split("def du_total")[0]
    assert "def reserve(self) -> float:" in source
    assert "return self._deadline - time.monotonic() - self.reserve()" in source
    # Exactly one place may open the reserve, and it is the closing scan.
    assert source.count("def release_reserve(self)") == 1
    assert source.count("scan_budget.release_reserve()") == 1
    release = source.index("scan_budget.release_reserve()")
    # The closing scan is the FIRST du after release_reserve(), so search from there
    # rather than from the top of the file -- the same call shape appears earlier, in
    # the opening PGDATA section.
    closing = source.index("closing_usage, pgdata_children_omitted", release)
    assert release < closing
    # The closing scan streams, so its omitted-child aggregate is available; the root
    # files figure must be reduced by it rather than silently absorbing dropped
    # children into the data directory's own files.
    assert "pgdata_children_omitted_bytes" in source
    assert (
        "- pgdata_children_omitted_bytes"
        in source.split("pgdata_root_files = (")[1].split("if pgdata_root_files")[0]
    )
    # And a step that cannot finish within what is left must not be started at all.
    assert "DRILL_DOWN_MIN_CALL_SECONDS = 30" in source
    assert "if budget.remaining() < DRILL_DOWN_MIN_CALL_SECONDS:" in source
    # An exhaustion before any step completed must still be recorded.
    assert "scan_budget_exhausted_before_first_step" in source
    assert "stopped_before_first_step" in source
    # Ordinary PostgreSQL file churn must not fail the inventory.
    assert "DU_VANISHED_MARKERS" in source
    assert "DU_ATTEMPTS = 3" in source
    assert "vanished_only" in source
    assert "tolerated_file_churn" in source
    # Its own section name, so section_failed cannot clobber the scans above it.
    assert source.count('"postgres_data_directory_reconciliation"') >= 2
    assert "postgres_data_directory_not_reconciled" in source
    # The chain is recorded before anything that can fail.
    drill_assign = source.index('inventory["non_database_drill_down"] = {')
    reconcile = source.index('inventory["postgres_data_directory_reconciliation"] = {')
    assert drill_assign < reconcile


def test_v3_disk_inventory_reports_a_reconciled_span(tmp_path):
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]

    assert inventory["postgres_data_directory_reconciliation"] == {
        "span_drift_bytes": 0,
        "tolerance_bytes": 1 << 30,
        "reconciled": True,
    }
    assert inventory["postgres_data_directory_bracket"]["span_reconciled"] is True
    assert inventory["non_database_drill_down"]["reconcile_reserve_seconds"] == 600


def test_v3_disk_inventory_tolerates_ordinary_postgres_file_churn(tmp_path):
    """A recycled WAL segment must not fail the whole inventory.

    `du` exits nonzero when any file it enumerated is gone before it is examined, and on
    a live 1.3 TB cluster that is ordinary behaviour, not a fault: PostgreSQL recycles
    WAL segments and removes temporary files continuously, and these scans run for
    minutes. Failing closed on it would make the inventory fail from normal database
    activity — the most likely way this action would fail in production. A vanished file
    is also, by definition, no longer using space, so the remaining totals are correct.
    """
    result = _run_inventory_action(tmp_path, du_churn=True)

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "success"
    inventory = receipt["inventory"]
    # The scan's figures are still produced and still reconcile.
    assert inventory["summary"]["non_database_directory_bytes"] == 92000
    assert inventory["postgres_data_directory_reconciliation"]["reconciled"] is True
    # And the churn is disclosed rather than hidden, so a reviewer can see it happened.
    churn = receipt["tolerated_file_churn"]
    assert churn, churn
    assert receipt["directory_scans_degraded"] is True
    assert all(entry["vanished_paths"] >= 1 for entry in churn)
    assert any("No such file or directory" in entry["first_diagnostic"] for entry in churn)


def test_v3_disk_inventory_still_fails_closed_on_an_unreadable_directory(tmp_path):
    """Tolerating churn must not tolerate a scan that did not measure what it claims.

    A permission error means part of the tree was never counted, so the totals are
    wrong rather than merely smaller. Only a vanished-file diagnostic is tolerable.
    """
    result = _run_inventory_action(tmp_path, du_permission_denied=True)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "stopped"
    reason = receipt["inventory"]["volume_directory_usage"]["volume_directory_usage_failed"]
    assert "Permission denied" in reason


def test_v3_disk_inventory_retries_churn_and_prefers_a_clean_scan(tmp_path):
    """A churned total can be wrong, not merely smaller, so it must not be accepted first.

    PostgreSQL recycles WAL by *renaming* a segment, so a path `du` enumerated and then
    could not stat may still occupy the same space under its new name. Accepting that
    output undercounts storage — the dangerous direction for a reclaim decision — so a
    churn failure is a reason to retry, and a clean rerun must win. The churn here
    happens once; the retry succeeds and no degraded figure is reported.
    """
    result = _run_inventory_action(tmp_path, du_churn_once=True)

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = json.loads(result.stdout)
    # The clean attempt was used, so nothing is recorded as tolerated or degraded.
    assert receipt["tolerated_file_churn"] == []
    assert receipt["directory_scans_degraded"] is False
    assert receipt["inventory"]["summary"]["non_database_directory_bytes"] == 92000


def test_v3_disk_inventory_flags_a_scan_that_churned_every_attempt(tmp_path):
    """When no attempt comes back clean, the figures are used but marked."""
    result = _run_inventory_action(tmp_path, du_churn=True)

    assert result.returncode == 0, result.stderr or result.stdout
    receipt = json.loads(result.stdout)
    churn = receipt["tolerated_file_churn"]
    assert churn
    # Reported at the top level, after every scan including the closing reconciliation:
    # a snapshot taken inside a section would have missed a degraded closing scan.
    assert receipt["directory_scans_degraded"] is True
    assert any(e["scan"] == "directory_total_failed" for e in churn), churn
    for entry in churn:
        # Every attempt was used before the output was accepted.
        assert entry["attempts"] == 3
        assert entry["accepted_possibly_undercounting"] is True


def test_v3_disk_inventory_rejects_a_non_churn_failure_after_churn(tmp_path):
    """A real failure on a retry must not be answered with the earlier churned output.

    Attempt one churns, so its partial output is held in case every attempt churns.
    Attempt two hits a permission error — a real fault. Returning the saved output then
    would report success from a measurement taken *before* the failure was even seen.
    """
    result = _run_inventory_action(tmp_path, du_churn_then_deny=True)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "stopped"
    reason = receipt["inventory"]["volume_directory_usage"]["volume_directory_usage_failed"]
    assert "Permission denied" in reason
    # The churned attempt was discarded, not reported as a tolerated success.
    assert receipt["tolerated_file_churn"] == []
    assert receipt["directory_scans_degraded"] is False


def test_v3_disk_inventory_keeps_statistics_directories_locatable(tmp_path):
    """pg_stat and pg_stat_tmp are not inside accounted_bytes, so they must be candidates.

    accounted_bytes is the per-database storage pg_database_size sums (base/), WAL
    (pg_wal) and the temporary directory — which is base/pgsql_tmp, inside base. The
    cluster-level statistics directories are covered by none of those, so excluding them
    from the candidates removed their bytes from every row while leaving them inside
    unaccounted_bytes: the summary would claim a figure it could not locate.
    """
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    by_path = {row["path"]: row for row in summary["largest_unaccounted_directories"]}

    assert by_path[f"{pgdata}/pg_stat"]["exclusive_bytes"] == 4000
    assert by_path[f"{pgdata}/pg_stat"]["inside_data_directory"] is True
    # Only base and the WAL directories are genuinely accounted for elsewhere.
    assert f"{pgdata}/base" not in by_path
    assert f"{pgdata}/pg_wal" not in by_path
    # global 8,000 + pg_stat 4,000 + root files 3,000 + pg_wal's unlisted 2,000
    # + base/'s orphaned 16999 at 500 + base/'s own 200 = everything accounted_bytes
    # does not cover, in du's metric. The remaining 1,295 of the old figure was the
    # du-versus-pg_database_size difference and is now its own summary term.
    assert summary["unaccounted_inside_data_directory_bytes"] == 17700


def test_v3_disk_inventory_records_that_no_tablespaces_break_the_accounting(tmp_path):
    """The single-filesystem assumption is now evidence, not an assumption."""
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]

    assert inventory["tablespaces"] == {
        "non_default": [],
        "non_default_count": 0,
        "non_default_limit": 50,
        "non_default_truncated": False,
        "single_filesystem_accounting_valid": True,
    }


def test_v3_disk_inventory_refuses_a_partition_when_a_tablespace_exists(tmp_path):
    """pg_database_size spans tablespaces; the scan covers one filesystem.

    A tablespace on another device is subtracted from this volume despite consuming
    none of it, and one elsewhere on the same device is counted twice — inside
    accounted_bytes and again as an outside candidate. Rather than present arithmetic
    that assumes something untrue, the summary refuses and names what it found.
    """
    result = _run_inventory_action(tmp_path, tablespace_present=True)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "stopped"
    inventory = receipt["inventory"]
    assert inventory["tablespaces"]["single_filesystem_accounting_valid"] is False
    assert inventory["tablespaces"]["non_default"][0]["spcname"] == "fast_ssd"
    assert (
        inventory["summary"]["summary_failed"]
        == "tablespaces_present_single_filesystem_accounting_invalid"
    )
    # The evidence above the summary is preserved, so the operator can still see the
    # scans and decide what to measure.
    assert inventory["non_database_drill_down"]["chain"]
    assert isinstance(inventory["volume_directory_usage"], list)


def test_v3_disk_inventory_brackets_the_root_scan_with_filesystem_usage(tmp_path):
    """The PGDATA bracket cannot see a sibling consumer growing during the root scan."""
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    bracket = json.loads(result.stdout)["inventory"]["volume_used_bracket"]

    assert bracket["bytes_before_filesystem_scan"] == 1557000
    assert bracket["bytes_after_filesystem_scan"] == 1557000
    assert bracket["drift_bytes"] == 0
    assert bracket["reconciled"] is True


def test_v3_disk_inventory_does_not_blame_reserved_blocks_for_the_residual():
    """Reserved blocks explain size - (used + available), never used - du.

    They remain free blocks that ordinary users cannot allocate, so they never enter
    `used`. Listing them as a cause would send an operator to tune the reserved-block
    percentage, which cannot close this residual.
    """
    source = _read(ACTION)
    method = source[source.index('"method": ('):]

    assert "Reserved blocks are NOT a cause" in method
    assert "size minus (used + available)" in method
    assert "reserved blocks and blocks held by deleted-but-open files" not in source


def test_v3_disk_inventory_keeps_the_complete_pgdata_child_list_for_accounting():
    """Truncating before accounting hides a large directory behind the root-files row."""
    source = _read(ACTION)

    assert "pgdata_children_all = sorted(" in source
    assert "pgdata_children_all[:40]" in source
    assert "pgdata_children = pgdata_children_all" in source
    assert '"child_count": len(pgdata_children_all)' in source
    # The summary must not read the truncated receipt view.
    assert 'inventory["postgres_data_directory_usage"]["children"]' not in source


def test_v3_disk_inventory_stops_cleanly_when_the_mount_point_cannot_resolve(tmp_path):
    """`usage_root` is read by a later section than the one that assigns it.

    A failed `df --output=target` records the directory-usage failure and leaves the
    name unassigned; the drill-down section's guard then reads it and raises NameError,
    which is not RuntimeError and so escapes the section handler — a traceback where
    the structured fail-closed receipt belongs.
    """
    result = _run_inventory_action(tmp_path, mount_point_failure=True)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "NameError" not in result.stderr
    assert len(result.stdout.splitlines()) == 1
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "stopped"
    inventory = receipt["inventory"]
    assert (
        inventory["volume_directory_usage"]["volume_directory_usage_failed"]
        == "directory_usage_mount_point_unresolved"
    )
    # The dependent section stops with its own reason rather than crashing.
    assert (
        inventory["non_database_drill_down"]["non_database_drill_down_failed"]
        == "volume_directory_usage_unavailable"
    )


def test_v3_disk_inventory_bounds_the_index_inventory():
    """Capping the relations does not cap their indexes.

    PostgreSQL documents no limit on indexes per table, so one relation could make the
    receipt — and the memory used to parse it — arbitrarily large.
    """
    source = _read(ACTION)

    assert "INDEX_INVENTORY_LIMIT = 200" in source
    assert "LIMIT {INDEX_INVENTORY_LIMIT + 1}" in source
    assert 'inventory["indexes_truncated"]' in source
    assert 'inventory["indexes_limit"] = INDEX_INVENTORY_LIMIT' in source


def test_v3_disk_inventory_reports_an_untruncated_index_inventory(tmp_path):
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]

    assert inventory["indexes_truncated"] is False
    assert inventory["indexes_limit"] == 200


def test_v3_disk_inventory_closes_the_measurement_window_last():
    """Every input to the summary must describe one state.

    The accounted-size queries (databases, WAL, temporary directory) originally all ran
    after the closing reconciliation, so a concurrent derived build or WAL change could
    make accounted_bytes describe a later state than the directory totals and produce a
    wrong — or negative — unaccounted_bytes while the receipt reported success.
    """
    source = _read(ACTION)

    # The reconciliation now runs after the database figures and before the summary.
    databases = source.index("    database_total_rows = psql_json(")
    reconcile = source.index('inventory["postgres_data_directory_reconciliation"] = {')
    summary = source.index('inventory["summary"] = {')
    assert databases < reconcile < summary
    # And the summary uses the reconciled reading, not the opening df.
    # The CLOSING reading, validated across the whole window — not the post-root-scan
    # one, which is only validated against the opening value.
    assert 'volume_used = used_bracket["bytes_after_window"]' in source
    assert 'used_bracket["bytes_after_filesystem_scan"]' not in source
    assert "volume_used_window_not_closed" in source
    assert "volume_used_not_reconciled" in source
    assert 'volume_used = inventory["volume"]["used_bytes"]' not in source


def test_v3_disk_inventory_separates_the_pgdata_scan_from_the_root_scan():
    """A PGDATA scan failure must not discard the completed host-level scan."""
    source = _read(ACTION)

    assert (
        source.count('section_failed(failures, inventory, "volume_directory_usage", exc)')
        == 1
    )
    assert (
        source.count(
            'section_failed(failures, inventory, "postgres_data_directory_usage", exc)'
        )
        == 1
    )
    # The root scan's handler comes before the PGDATA scan, so they cannot share one.
    root_handler = source.index(
        'section_failed(failures, inventory, "volume_directory_usage", exc)'
    )
    pgdata_scan = source.index('"postgres_data_directory_usage_failed",')
    assert root_handler < pgdata_scan


def test_v3_disk_inventory_distinguishes_failed_tablespace_inspection(tmp_path):
    """"Never inspected" and "tablespaces found" are different facts.

    section_failed leaves an error object, which is still a dict, so a missing validity
    flag was read as "tablespaces found" — telling the operator tablespaces exist when
    they were never successfully inspected.
    """
    source = _read(ACTION)

    assert "tablespace_section.get(\"single_filesystem_accounting_valid\"), bool" in source
    assert 'tablespace_section["single_filesystem_accounting_valid"]' in source
    # The truthiness test that conflated the two cases is gone.
    assert 'if not tablespace_section.get("single_filesystem_accounting_valid")' not in source


def test_v3_disk_inventory_reserve_survives_the_sql_phase():
    """The reserve must be an allowance, not a slice of an advancing deadline.

    Between the scans and the closing measurement, the database, WAL, relation, index,
    attribution and tablespace queries run without touching the budget while the wall
    clock keeps moving — so they could consume the protected 300 s and the closing scan
    would be denied by time it never asked for.
    """
    source = _read(ACTION)

    # Both closing figures now come from ONE scan, so two walks cannot each consume
    # more than half the single reserve or observe different states.
    assert "postgres_data_directory_usage_total_missing" in source
    assert source.count("pgdata_final = du_total(") == 0
    release = source[source.index("def release_reserve(self)") :]
    release = release[: release.index("\n    def ")]
    assert "self._reserved = False" in release
    assert "self._deadline = time.monotonic() + self.reserve_seconds" in release


def test_v3_disk_inventory_rechecks_the_filesystem_when_closing(tmp_path):
    """A sibling consumer can change during the drill-down and the SQL inventory."""
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    bracket = json.loads(result.stdout)["inventory"]["volume_used_bracket"]

    assert bracket["bytes_before_filesystem_scan"] == 1557000
    assert bracket["bytes_after_window"] == 1557000
    assert bracket["window_drift_bytes"] == 0
    assert bracket["reconciled"] is True
    assert "volume_changed_during_window" in _read(ACTION)


def test_v3_disk_inventory_treats_pg_xlog_as_unexpected_storage():
    """pg_ls_waldir() measures the live WAL directory, which on PostgreSQL 18 is pg_wal.

    Subtracting wal_bytes from a stale pg_xlog would treat it as measured: smaller than
    the live WAL it vanishes from the candidates, larger and only its excess shows — and
    a directory full of old WAL is exactly the reclaimable space this action looks for.
    """
    source = _read(ACTION)

    assert (
        'for name, subtract in (("pg_wal", wal_for_subtraction), ("pg_xlog", 0)):'
        in source
    )
    # The WAL figure comes from the same state as the directory breakdown: otherwise
    # ordinary top-level WAL growth within the accepted drift is labelled
    # "subdirectories pg_ls_waldir does not list" — normal WAL reported as unexpected.
    assert 'inventory["wal"]["bytes_at_window_close"]' in source
    assert "wal_bytes_not_reconciled" in source
    assert "not the live WAL directory on PostgreSQL 18; unexpected storage" in source


def test_v3_disk_inventory_workflow_elevates_the_whole_filesystem_scan():
    """As the non-root operator account, `du` cannot read root-owned mode-0700 paths.

    The action fails closed on permission errors by design, so without the same
    root/passwordless-sudo handoff the other privileged steps use, the governed
    inventory could never produce a receipt at all.
    """
    workflow = _read(Path(".github/workflows/chatgpt-ed-new-ops.yml"))

    assert "V3 disk inventory requires root or passwordless sudo" in workflow
    step = workflow[workflow.index("v3-disk-inventory.sh") - 1500 :]
    step = step[: step.index("v3-disk-inventory.sh") + 40]
    assert "sudo -n bash -s" in step
    assert 'if [ \\"\\$(id -u)\\" -eq 0 ]' in step


def test_v3_disk_inventory_parses_paths_containing_newlines(tmp_path):
    """A directory whose NAME contains a newline must not stop the inventory.

    `splitlines()` fragments that `du` record, the fragment without a tab raises
    directory_usage_output_invalid, and the governed scan stops even though it
    succeeded. The whole-filesystem scan covers operator-uncontrolled paths, so this is
    reachable without anything being wrong.
    """
    source = _read(ACTION)

    assert 'for record in stdout.split("\\0"):' in source
    assert "splitlines()" not in source.split("def parse_du(")[1].split("def ")[0]
    # Every du invocation asks for NUL-delimited output.
    assert source.count('["du", "--null", "-x", "-B1"') == 6
    assert '["du", "-x", "-B1"' not in source


def test_v3_disk_inventory_reports_candidates_hidden_by_the_display_limit(tmp_path):
    """The totals sum the complete list, so the hidden tail must be disclosed."""
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]

    assert summary["candidate_count"] >= len(summary["largest_unaccounted_directories"])
    assert summary["candidates_omitted"] == max(0, summary["candidate_count"] - 10)
    # With the fixture's candidates all shown, nothing is omitted — but the fields are
    # present so an operator never has to infer whether the list is complete.
    assert summary["candidates_omitted_bytes"] == 0


def test_v3_disk_inventory_refuses_when_wal_lives_outside_pgdata(tmp_path):
    """pg_wal can be relocated with initdb --waldir or a symlink.

    `du` does not dereference symlinks, so a same-filesystem target appears as an
    outside candidate while its bytes are also subtracted, and an external-filesystem
    target is subtracted from a volume it does not occupy. The arithmetic assumes the
    WAL directory is inside PGDATA, so it verifies that rather than assuming it.
    """
    result = _run_inventory_action(tmp_path, wal_outside_pgdata=True)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["wal"]["resolved_host_directory"] == "/mnt/wal/pg_wal"
    assert inventory["wal"]["directory_inside_pgdata"] is False
    assert inventory["summary"]["summary_failed"] == "wal_directory_outside_pgdata"
    # The evidence above the summary survives, as with the tablespace refusal.
    assert isinstance(inventory["volume_directory_usage"], list)


def test_v3_disk_inventory_records_wal_inside_pgdata(tmp_path):
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    wal = json.loads(result.stdout)["inventory"]["wal"]

    assert wal["directory_inside_pgdata"] is True
    assert wal["container_directory"] == "/var/lib/postgresql/18/docker/pg_wal"


def test_v3_disk_inventory_bounds_each_drill_down_child_listing():
    """A high-fan-out directory must not make memory unbounded.

    /var/lib/docker/overlay2 can hold thousands of layers; `du --max-depth=1` emits one
    record per immediate child, and run() captures the whole output before du_rows()
    parses and sorts it — so neither the step cap nor the timeout bounds memory. The cap
    has to happen before Python sees the output.
    """
    source = _read(ACTION)

    assert "DRILL_DOWN_CHILD_LIMIT = 200" in source
    assert "DU_DEFAULT_KEEP = 4000" in source
    # Bounded by streaming top-k in Python, NOT by a shell pipeline. A `du | sort |
    # head` pipeline bounds memory but spills sort's temporary files to $TMPDIR, which
    # this action promises it never does; returns head's exit status rather than du's,
    # because the nested shell does not inherit pipefail; and leaves du walking after a
    # timeout, because subprocess kills only the immediate child.
    assert "| sort -z" not in source
    assert "head -z" not in source
    assert '"bash",' not in source
    assert "def du_stream(" in source
    assert "heapq.heapreplace(kept, item)" in source
    assert "start_new_session=True" in source
    assert "os.killpg(os.getpgid(process.pid), signal.SIGKILL)" in source
    # The omitted children's bytes are returned and used, not discarded.
    assert "own_file_bytes = here_total - child_total - omitted_child_bytes" in source
    assert '"children_omitted_by_cap": omitted_children,' in source


def test_v3_disk_inventory_top_k_keeps_the_largest_and_totals_the_rest():
    """The cap must keep the largest records and account for the rest.

    A directory's own total includes all its children, so it is always the largest
    record and always survives -- losing it raises drill_down_total_missing. And the
    bytes of the dropped children have to come back as an aggregate, or they would be
    attributed to the directory's own files.
    """
    keep = 3
    kept: list[tuple[int, str]] = []
    omitted = [0, 0]
    records = [(10_000, "/root")] + [(100 - i, f"/root/child-{i:02d}") for i in range(20)]
    for size, path in records:
        item = (size, path)
        if len(kept) < keep:
            heapq.heappush(kept, item)
        elif item > kept[0]:
            dropped = heapq.heapreplace(kept, item)
            omitted[0] += 1
            omitted[1] += dropped[0]
        else:
            omitted[0] += 1
            omitted[1] += size

    survivors = sorted(kept, key=lambda item: (-item[0], item[1]))
    assert survivors[0] == (10_000, "/root")
    assert [s[0] for s in survivors] == [10_000, 100, 99]
    assert omitted[0] == len(records) - keep
    # Nothing is lost: the survivors plus the omitted aggregate are the whole input.
    assert sum(s[0] for s in survivors) + omitted[1] == sum(size for size, _ in records)


def test_v3_disk_inventory_decodes_undecodable_paths(tmp_path):
    """A path byte sequence invalid in the host locale must not raise."""
    source = _read(ACTION)

    assert 'errors="surrogateescape"' in source
    run_body = source[source.index("def run(") :]
    run_body = run_body[: run_body.index("\ndef ")]
    assert "text=True" in run_body
    assert 'errors="surrogateescape"' in run_body


def test_v3_disk_inventory_measures_pgdata_detail_at_window_close(tmp_path):
    """Accepting drift must mean measuring every part of the arithmetic after it.

    PGDATA movement inside the 0.5 % tolerance is several GiB on this cluster, so
    computing the inside-PGDATA candidates from the opening total and children while
    the database, WAL and filesystem figures come from the closing state could leave
    them differing from unaccounted_bytes by the whole accepted drift.
    """
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    summary = inventory["summary"]

    assert inventory["postgres_data_directory_usage"]["measured_at"] == "window_close"
    assert (
        inventory["postgres_data_directory_usage"]["bytes"]
        == inventory["postgres_data_directory_bracket"]["bytes_after_drill_down"]
    )
    # The partition still closes exactly against the figure it explains, with the
    # du-versus-pg_database_size difference named rather than absorbed.
    assert (
        summary["non_database_directory_bytes"]
        + summary["unaccounted_inside_data_directory_bytes"]
        + summary["database_size_metric_difference_bytes"]
        == summary["unaccounted_bytes_at_directory_scan"]
    )


def test_v3_disk_inventory_bounds_generation_attribution(tmp_path):
    """Generation manifests are never deleted, so attribution grows without bound.

    The statement timeout caps execution, not rows or the serialized receipt, so as
    retained generations accumulate the result and the receipt grow indefinitely.
    """
    source = _read(ACTION)
    assert "GENERATION_ATTRIBUTION_LIMIT = 50" in source
    assert source.count("LIMIT {GENERATION_ATTRIBUTION_LIMIT + 1}") == 3

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["generation_attribution_limit"] == 50
    assert inventory["generation_attribution_truncated"] is False


def test_v3_disk_inventory_names_the_post_scan_drift_instead_of_hiding_it(tmp_path):
    """The candidates partition the SCAN window, and the receipt must say so.

    The candidates are du measurements from the scan window; unaccounted_bytes is a
    closing df reading minus SQL-phase totals. Presenting the first as a partition of
    the second let up to the whole reconciliation tolerance -- several GiB on this
    volume -- hide inside a candidate or go quietly missing from one, in a receipt
    reporting success. df, du and six SQL queries cannot be read atomically on a live
    multi-terabyte cluster, so the difference is named rather than pretended away.
    """
    result = _run_inventory_action(tmp_path, df_used_drift=9000)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]

    assert summary["post_scan_volume_drift_bytes"] == 9000
    # The closing figure includes the drift; the scan-window figure does not.
    assert summary["unaccounted_bytes"] == 1566000 - 1446005
    assert summary["unaccounted_bytes_at_directory_scan"] == 1557000 - 1446005
    assert (
        summary["unaccounted_bytes"]
        == summary["unaccounted_bytes_at_directory_scan"]
        + summary["post_scan_volume_drift_bytes"]
    )
    # The asserted identity is against the scan-window figure, and it holds even with
    # 9,000 bytes of drift -- which is the whole point: the drift is outside the
    # partition rather than inside a candidate.
    assert (
        summary["candidate_total_bytes"]
        + summary["database_size_metric_difference_bytes"]
        == summary["unaccounted_bytes_at_directory_scan"]
    )
    assert summary["candidates_partition_unaccounted_at_scan"] is True
    assert "cannot be read atomically" in summary["method"]


def test_v3_disk_inventory_bounds_the_tablespace_refusal_path(tmp_path):
    """The fail-closed guard must not be the thing that fails.

    Non-default tablespaces make this action refuse to present a partition at all, so
    the refusal needs only a count. Returning a row per tablespace -- each costing a
    pg_tablespace_size walk -- let the safety path itself exhaust the client and
    produce no structured stopped receipt, which is the one outcome a fail-closed
    guard cannot have.
    """
    source = _read(ACTION)
    assert "TABLESPACE_INVENTORY_LIMIT = 50" in source
    assert "LIMIT {TABLESPACE_INVENTORY_LIMIT}" in source
    # Validity comes from the COUNT, never from the bounded sample: a truncated list
    # is still a cluster with tablespaces.
    assert '"single_filesystem_accounting_valid": non_default_tablespace_count == 0' in (
        source
    )

    result = _run_inventory_action(tmp_path, tablespace_present=True)
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["tablespaces"]["non_default_count"] == 1
    assert inventory["tablespaces"]["non_default_truncated"] is False
    assert inventory["tablespaces"]["single_filesystem_accounting_valid"] is False
    # And the partition is still refused, naming what was found.
    assert (
        inventory["summary"]["summary_failed"]
        == "tablespaces_present_single_filesystem_accounting_invalid"
    )


def test_v3_disk_inventory_keeps_the_operating_database_inside_its_bound(tmp_path):
    """The bound may drop rows, but never the one row the reader came for.

    Size-only ordering drops the operating database's detailed entry on a cluster with
    more than 50 larger databases, leaving a summary that reports an
    operating_database_bytes figure with no corresponding row in the list it is drawn
    from. Same failure as bounding the published generation out of the attribution
    table.
    """
    source = _read(ACTION)
    assert "ORDER BY (datname=current_database()) DESC, " in source
    assert "operating_database_row_missing" in source

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    databases = json.loads(result.stdout)["inventory"]["databases"]
    operating = [row for row in databases if row["operating"]]
    assert [row["datname"] for row in operating] == ["edfinder_v3_db"]


def test_v3_disk_inventory_breaks_base_down_in_one_metric(tmp_path):
    """base/'s remainder must not be two different measurements subtracted.

    GNU du reports allocated filesystem blocks; pg_database_size sums each entry's
    st_size. Subtracting the latter from the former made ordinary per-file block
    rounding -- across tens of thousands of relation files -- into a standing
    "orphaned storage under base/" candidate, in the one receipt whose entire purpose
    is to say what can be reclaimed. The fixture's live directories deliberately
    exceed the pg_database_size totals for exactly that reason.
    """
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    breakdown = inventory["postgres_base_directory_breakdown"]
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"

    assert breakdown["available"] is True
    assert breakdown["metric"] == "du_allocated_blocks"
    assert breakdown["bytes"] == 1330000
    # Live OIDs 16384 and 5, measured by du: 1,321,000 + 8,200.
    assert breakdown["live_database_directory_bytes"] == 1329200
    assert breakdown["temporary_directory_bytes"] == 100
    assert breakdown["unreferenced_directory_bytes"] == 500
    assert [row["path"] for row in breakdown["unreferenced_entries"]] == [
        f"{pgdata}/base/16999"
    ]
    assert breakdown["other_bytes"] == 200

    # The metric difference is its own figure, explicitly not reclaimable:
    # (1,329,200 + 100) du against (1,320,000 + 8,000 + 5) st_size.
    summary = inventory["summary"]
    assert summary["database_size_metric_difference_bytes"] == 1295
    method = summary["method"]
    assert "allocated filesystem blocks" in method
    assert "is not reclaimable" in method


def test_v3_disk_inventory_emits_no_base_candidate_without_the_breakdown(tmp_path):
    """An unexplained gap is honest; a fabricated reclaim target is not.

    The breakdown needs the complete set of live database OIDs. With a partial set a
    live database's directory would be reported as orphaned storage -- the worst
    error this receipt can make -- so the base/ rows are omitted entirely, the reason
    is recorded, and the partition closure is reported as unknown rather than
    asserted against a figure that cannot be computed.
    """
    source = _read(ACTION)
    assert '"reason": "live_database_oids_unbounded"' in source
    assert '"reason": "base_child_not_measured"' in source
    assert '"reason": "scan_budget_exhausted"' in source
    # Unavailable means no claim, not a claim of zero.
    assert "metric_difference = None" in source
    assert "None\n            if metric_difference is None" in source
    # And the OID set is only accepted when it is provably complete: bounded by the
    # same limit as the row list, and cross-checked against the SQL count.
    assert (
        "len(oid_rows) > DATABASE_INVENTORY_LIMIT or len(oid_rows) != database_count"
        in source
    )

    # A failed base scan refines one candidate; it must not take the reconciliation --
    # and so the whole summary -- down with it.
    result = _run_inventory_action(tmp_path, base_scan_denied=True)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    breakdown = inventory["postgres_base_directory_breakdown"]
    assert breakdown["available"] is False
    assert "Permission denied" in breakdown["reason"]
    # The receipt is still complete and still reconciled...
    assert inventory["postgres_data_directory_reconciliation"]["reconciled"] is True
    summary = inventory["summary"]
    assert "summary_failed" not in summary
    # ...but makes NO base claim, and says the closure is unknown rather than
    # asserting it against a metric difference it could not compute.
    assert summary["database_size_metric_difference_bytes"] is None
    assert summary["candidates_partition_unaccounted_at_scan"] is None
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    paths = [row["path"] for row in summary["largest_unaccounted_directories"]]
    assert not any(path.startswith(f"{pgdata}/base") for path in paths)


def test_v3_disk_inventory_pairs_the_df_du_residual_with_its_own_window(tmp_path):
    """The df/du residual must use the df reading taken beside its du scan.

    du runs once, near the start; df is read again at the close, after the drill-down
    and the whole SQL inventory. Subtracting the early du total from the late df
    reading charges everything written or freed in between to the residual -- and the
    residual's entire meaning is "filesystem metadata and blocks held by
    deleted-but-open files", so the contamination is indistinguishable from the
    signal it is supposed to measure. An operator reading a flagged residual would go
    looking for a backend holding a dropped relation open that does not exist.

    unaccounted_bytes legitimately uses the CLOSING reading, because the database and
    WAL totals it subtracts are themselves closing figures. So the two must differ,
    and the receipt must report both.
    """
    source = _read(ACTION)
    assert "residual = volume_used_at_scan - du_root_bytes" in source
    assert "volume_used_at_scan_unavailable" in source

    # 9,000 of drift between the post-scan reading and the closing one, well inside the
    # 1 GiB floor tolerance, so the window still reconciles and the action succeeds.
    result = _run_inventory_action(tmp_path, df_used_drift=9000)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    summary = inventory["summary"]

    assert inventory["volume_used_bracket"]["bytes_after_filesystem_scan"] == 1557000
    assert inventory["volume_used_bracket"]["bytes_after_window"] == 1566000
    # unaccounted_bytes: the closing reading.
    assert summary["volume_used_bytes"] == 1566000
    assert summary["unaccounted_bytes"] == 1566000 - 1446005
    # The residual: the reading from the du scan's own moment, so it stays 0 rather
    # than inventing 9,000 bytes of deleted-but-open storage.
    assert summary["volume_used_bytes_at_directory_scan"] == 1557000
    assert summary["directory_scan_root_bytes"] == 1557000
    assert summary["filesystem_minus_directory_scan_bytes"] == 0
    assert summary["filesystem_minus_directory_scan_is_significant"] is False
    # The method must say which window each figure came from, or the two readings in
    # one summary are just a contradiction.
    assert (
        "volume_used_bytes_at_directory_scan minus directory_scan_root_bytes"
        in (summary["method"])
    )


def test_v3_disk_inventory_bounds_the_database_list_without_bounding_the_total(
    tmp_path,
):
    """pg_database is unbounded, but accounted_bytes must not be.

    Bounding the row list and then summing THAT list in Python would understate
    accounted_bytes, and unaccounted_bytes is volume_used minus accounted -- so every
    database dropped by the bound would appear as reclaimable space. The totals are
    therefore computed in SQL across every row, and the bound applies only to what
    the receipt displays.
    """
    source = _read(ACTION)
    assert "DATABASE_INVENTORY_LIMIT = 50" in source
    assert "LIMIT {DATABASE_INVENTORY_LIMIT + 1}" in source
    # Totals in SQL, over all of pg_database, with no LIMIT on that query.
    totals = source.split("database_total_rows = psql_json(")[1].split(
        "if len(database_total_rows)"
    )[0]
    assert "coalesce(sum(pg_database_size(oid)),0)" in totals
    assert "LIMIT" not in totals
    # Identified by the connection rather than an interpolated name.
    assert "datname=current_database()" in source
    # And no Python-side sum over the bounded list may survive.
    assert 'for row in database_rows if row["datname"] != db_name' not in source
    assert (
        "other_databases_bytes = database_total_bytes - operating_database_bytes"
        in source
    )
    # A failed section must reach the summary as a RuntimeError, not a TypeError from
    # iterating the failure dict.
    assert "database_sizes_unavailable" in source

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["database_count"] == 2
    assert inventory["database_total_bytes"] == 1328000
    assert inventory["database_inventory_limit"] == 50
    assert inventory["database_inventory_truncated"] is False
    assert inventory["summary"]["operating_database_bytes"] == 1320000
    assert inventory["summary"]["other_databases_bytes"] == 8000


def test_v3_disk_inventory_always_retains_the_published_generation(tmp_path):
    """The bound must never drop the one generation whose bytes are live.

    Generation keys carry no chronology, so lexicographic order puts the published
    generation anywhere -- including past the limit. A receipt that bounded it away
    would show an operator a complete-looking attribution table in which every
    listed generation is superseded, which reads as a licence to reclaim all of
    them. Both the SQL ordering and the union performed here must retain it.
    """
    source = _read(ACTION)
    # The SQL sorts the published generation first, in all three product queries.
    assert (
        source.count(
            "ORDER BY (p.derived_generation_id IS NOT NULL) DESC, g.generation_key "
        )
        == 3
    )
    assert source.count("LEFT JOIN v3_meta.current_derived_generation p ") == 3
    # And the union re-sorts for the receipt, so it must re-add it explicitly.
    assert "if published_key is not None and published_key not in dict(kept):" in source
    # A singleton that yields two published keys is a broken assumption, not a
    # row to pick between.
    assert "chunk_receipt_published_generation_ambiguous" in source

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    # The fixture's superseded generation sorts BEFORE the published one.
    assert list(inventory["generation_attribution"]) == [
        "aaa_superseded",
        "ratings_v4_live",
    ]
    assert inventory["generation_attribution_published_generation"] == "ratings_v4_live"
    assert inventory["generation_attribution_published_generation_retained"] is True


def test_v3_disk_inventory_reconciles_wal_bytes_at_window_close(tmp_path):
    """The WAL figure must come from the same state as the directory breakdown."""
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]

    assert inventory["wal"]["bytes_at_window_close"] == 118000
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    by_path = {
        row["path"]: row
        for row in inventory["summary"]["largest_unaccounted_directories"]
    }
    wal_unlisted = (
        f"{pgdata}/pg_wal (subdirectories and files pg_ls_waldir does not list)"
    )
    # 120,000 measured at close minus 118,000 of listed WAL at close.
    assert by_path[wal_unlisted]["exclusive_bytes"] == 2000


def test_v3_disk_inventory_documents_the_unlisted_base_remainder():
    """The description must not say base/ is covered in full.

    pg_database_size scans base/<database OID>, so an orphaned directory from a
    dropped database is inside no accounted figure — and is among the most reclaimable
    things this receipt can find, so being told it is already counted is the worst
    possible framing.
    """
    doc = _read(Path("docs/operations/v3-finder-production-rollout-state.md"))

    assert "scans `base/<database OID>`, not the whole directory" in doc
    assert "Any remaining\n`base/` bytes are reported separately" in doc
    assert "must not be dismissed as already counted" in doc
