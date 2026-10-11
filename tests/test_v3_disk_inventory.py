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
                printf 'Mounted on\\n'
                printf '/\\n' ;;
              *'--output=used'*)
                printf 'Used\\n'
                printf '1557000\\n' ;;
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
                printf '1465000\\t%s\\n' "$data" ;;
              *"--max-depth=1 $data")
                printf '1330000\\t%s/base\\n' "$data"
                printf '120000\\t%s/pg_wal\\n' "$data"
                printf '8000\\t%s/global\\n' "$data"
                printf '4000\\t%s/pg_stat\\n' "$data"
                printf '1465000\\t%s\\n' "$data" ;;
              *'--max-depth=1 /var/lib/docker/volumes')
                printf '1465000\\t%s\\n' "$vol"
                printf '1470000\\t/var/lib/docker/volumes\\n' ;;
              *'--max-depth=1 /var/lib/docker/overlay2')
                printf '1000\\t/var/lib/docker/overlay2/aaaa\\n'
                printf '1000\\t/var/lib/docker/overlay2/bbbb\\n'
                printf '38000\\t/var/lib/docker/overlay2\\n' ;;
              *'--max-depth=1 /var/lib/docker')
                printf '1470000\\t/var/lib/docker/volumes\\n'
                printf '38000\\t/var/lib/docker/overlay2\\n'
                printf '1510000\\t/var/lib/docker\\n' ;;
              *'--max-depth=1 /var/lib')
                printf '1510000\\t/var/lib/docker\\n'
                printf '5000\\t/var/lib/apt\\n'
                printf '1515000\\t/var/lib\\n' ;;
              *'--max-depth=1 /var')
                if [ "$DU_LAYOUT" = 'direct_files' ]; then
                  printf '1465000\\t/var/lib\\n'
                  printf '80000\\t/var/log\\n'
                  printf '1545000\\t/var\\n'
                else
                  printf '1515000\\t/var/lib\\n'
                  printf '30000\\t/var/log\\n'
                  printf '1545000\\t/var\\n'
                fi ;;
              *'--max-depth=1 /var/log')
                # 70,000 bytes sit directly in /var/log; the largest child is 10,000.
                printf '10000\\t/var/log/journal\\n'
                printf '80000\\t/var/log\\n' ;;
              *'--max-depth=1 /')
                printf '1545000\\t/var\\n'
                printf '12000\\t/home\\n'
                printf '1557000\\t/\\n' ;;
              *'--max-depth=2'*)
                printf '1515000\\t/var/lib\\n'
                printf '30000\\t/var/log\\n'
                printf '1545000\\t/var\\n'
                printf '12000\\t/home/claude\\n'
                printf '12000\\t/home\\n'
                printf '1557000\\t/\\n' ;;
              *)
                printf '%s\\n' "unexpected du: $*" >&2
                exit 9 ;;
            esac
            exit "$CHURN_EXIT"
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
              *'data_directory'*)
                printf '%s\\n' '/var/lib/postgresql/18/docker' ;;
              *'pg_tablespace'*)
                if [ "$TABLESPACE_PRESENT" = '1' ]; then
                  printf '%s\\n' '{"spcname":"fast_ssd","location":"/mnt/ssd/pgtbs","size_bytes":40000}'
                fi ;;
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
    env["VOLUME_DF_FAILURE"] = "1" if volume_df_failure else "0"
    env["DU_LAYOUT"] = du_layout
    env["DU_CHURN"] = "1" if du_churn else "0"
    env["DU_CHURN_ONCE"] = "1" if du_churn_once else "0"
    env["DU_CHURN_THEN_DENY"] = "1" if du_churn_then_deny else "0"
    env["DU_CHURN_STAMP"] = str(tmp_path / "du-churn-stamp")
    env["DU_PERMISSION_DENIED"] = "1" if du_permission_denied else "0"
    env["TABLESPACE_PRESENT"] = "1" if tablespace_present else "0"
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
    assert '["du", "-x", "-B1", "--max-depth=2", usage_root]' in source
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

    assert '["du", "-x", "-B1", "--max-depth=1", pgdata_host]' in source
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
    assert receipt["inventory"]["summary"]["unaccounted_bytes"] == 1557000 - 1382


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
    assert by_path[wal_unlisted]["exclusive_bytes"] == 120000 - 12
    assert by_path[wal_unlisted]["inside_data_directory"] is True
    assert summary["unaccounted_inside_data_directory_bytes"] == (
        8000 + 4000 + 3000 + (120000 - 12)
    )
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

    # The reserve is the closing scan's FULL per-call allowance: reserving less would
    # leave the mandatory scan running against a shortened timeout, which is just a
    # different way of failing it.
    assert "RECONCILE_RESERVE_SECONDS = DIRECTORY_USAGE_TIMEOUT_SECONDS" in source
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
    closing = source.index("pgdata_final = du_total(pgdata_host, scan_budget)")
    assert release < closing
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
    assert inventory["non_database_drill_down"]["reconcile_reserve_seconds"] == 300


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
    # global 8,000 + pg_stat 4,000 + root files 3,000 + pg_wal's unlisted 119,988
    # = the whole PGDATA remainder, i.e. everything accounted_bytes does not cover.
    assert summary["unaccounted_inside_data_directory_bytes"] == (
        8000 + 4000 + 3000 + (120000 - 12)
    )


def test_v3_disk_inventory_records_that_no_tablespaces_break_the_accounting(tmp_path):
    """The single-filesystem assumption is now evidence, not an assumption."""
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]

    assert inventory["tablespaces"] == {
        "non_default": [],
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
