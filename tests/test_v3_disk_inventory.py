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
    du_below_df: bool = False,
    wal_separate_filesystem: bool = False,
    pgdata_grew: int = 0,
    pgdata_after_grew: int = 0,
    wal_nested_mount: bool = False,
    pgdata_inner_mount: bool = False,
    database_grew: int = 0,
    volume_used_drift: int = 0,
    wal_at_window_close: int = 118000,
    nested_mount_mode: str = "none",
    root_scan_truncated: bool = False,
) -> subprocess.CompletedProcess[str]:
    source = _read(ACTION)
    body = source.split("exec \"$PYTHON_BIN\" -I -B - <<'PY'\n", 1)[1].rsplit(
        "\nPY\n", 1
    )[0]
    usage_root = "/"
    mounts_file = tmp_path / "proc-mounts"
    mounts_lines = ["/dev/root / ext4 rw,relatime 0 0"]
    if nested_mount_mode in {"same_device", "stat_failure"}:
        scan_root = tmp_path / "scan-root"
        scan_root.mkdir()
        usage_root = str(scan_root)
        nested = scan_root / "nested"
        if nested_mount_mode == "same_device":
            nested.mkdir()
        mounts_lines.extend(
            [
                f"/dev/root {scan_root} ext4 rw,relatime 0 0",
                f"/dev/nested {nested} ext4 rw,relatime 0 0",
            ]
        )
    elif nested_mount_mode == "different_device":
        different_device_path = next(
            path
            for path in (Path("/proc"), Path("/dev"), Path("/sys"))
            if path.exists() and path.stat().st_dev != Path("/").stat().st_dev
        )
        mounts_lines.append(
            f"proc {different_device_path} proc rw,nosuid,nodev,noexec 0 0"
        )
    elif nested_mount_mode not in {"none", "unreadable"}:
        raise ValueError(f"unsupported nested_mount_mode: {nested_mount_mode}")
    if nested_mount_mode != "unreadable":
        mounts_file.write_text("\n".join(mounts_lines) + "\n", encoding="utf-8")
    body = body.replace(
        'PROC_MOUNTS = "/proc/mounts"', f"PROC_MOUNTS = {str(mounts_file)!r}"
    )
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
    stat_bin = fake_bin / "stat"
    stat_bin.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            # -c %d <path>: the st_dev the kernel gives `du -x` to decide whether to
            # descend. Same device for PGDATA and pg_wal unless
            # WAL_SEPARATE_FILESYSTEM asks for the mounted-at-the-canonical-path case,
            # which `readlink -f` cannot distinguish from an ordinary subdirectory.
            target="$3"
            case "$target" in
              */pg_wal)
                if [ "$WAL_SEPARATE_FILESYSTEM" = '1' ]; then
                  printf '%s\\n' '2049'
                else
                  printf '%s\\n' '2048'
                fi ;;
              *)
                printf '%s\\n' '2048' ;;
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
                if [ "$PGDATA_INNER_MOUNT" = '1' ]; then
                  # A mount covering an ANCESTOR of PGDATA, beneath the outer
                  # /var/lib/postgresql mount. The old name heuristic selected the
                  # outer mount and mapped PGDATA into its hidden underlying tree.
                  printf '/mnt/pg18\\t/var/lib/postgresql/18\\n'
                fi
                if [ "$WAL_NESTED_MOUNT" = '1' ]; then
                  # A second mount attached at pg_wal's canonical destination inside
                  # the container. From the host, that path is an ordinary (empty)
                  # directory in the PGDATA volume on PGDATA's own device, so neither
                  # readlink nor stat can tell it apart from a real subdirectory.
                  printf '/mnt/fast-wal\\t/var/lib/postgresql/18/docker/pg_wal\\n'
                fi
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
                printf '/dev/md1 ext4 1948000 %s 292000\\n' "$(( 1557000 + ROOT_SCAN_EXTRA ))" ;;
              *'--output=target'*)
                if [ "$MOUNT_POINT_FAILURE" = '1' ]; then
                  printf '%s\\n' 'cannot resolve mount point' >&2
                  exit 9
                fi
                printf 'Mounted on\\n'
                printf '%s\\n' "$USAGE_ROOT" ;;
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
                  printf '%s\\n' "$(( 1557000 + ROOT_SCAN_EXTRA + DF_USED_DRIFT ))"
                elif [ "$calls" -eq 1 ]; then
                  # VOLUME_USED_DRIFT moves only the reading taken BEFORE the root
                  # walk, so before and after differ by it -- the width of the window
                  # the du total was measured across.
                  printf '%s\\n' "$(( 1557000 + ROOT_SCAN_EXTRA + VOLUME_USED_DRIFT ))"
                else
                  printf '%s\\n' "$(( 1557000 + ROOT_SCAN_EXTRA ))"
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
                # Called twice, bracketing the root walk. PGDATA_AFTER_GREW drifts only
                # the SECOND reading, which is the one the outside candidates subtract
                # from the ancestor holding the data directory -- large enough and that
                # ancestor's exclusive size goes negative.
                calls=0
                if [ -f "$PGDATA_DEPTH0_STAMP" ]; then
                  calls="$(cat "$PGDATA_DEPTH0_STAMP")"
                fi
                calls="$(( calls + 1 ))"
                printf '%s' "$calls" > "$PGDATA_DEPTH0_STAMP"
                if [ "$calls" -ge 2 ]; then
                  printf '%s\\t%s\\0' "$(( 1465000 + PGDATA_AFTER_GREW ))" "$data"
                else
                  printf '1465000\\t%s\\0' "$data"
                fi ;;
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
                # PGDATA_GREW drifts ONLY this closing root total, not the depth-0
                # calls that bracket the root walk, so the scan-side and closing
                # data-directory figures differ by exactly that much.
                printf '1330000\\t%s/base\\0' "$data"
                printf '120000\\t%s/pg_wal\\0' "$data"
                if [ "$DU_LAYOUT" = 'pg_xlog' ]; then
                  printf '9000\\t%s/pg_xlog\\0' "$data"
                fi
                printf '8000\\t%s/global\\0' "$data"
                printf '4000\\t%s/pg_stat\\0' "$data"
                printf '%s\\t%s\\0' "$(( 1465000 + PGDATA_GREW ))" "$data" ;;
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
                if [ "$ROOT_SCAN_EXTRA" -gt 0 ]; then
                  printf '5000\\t/synthetic\\0'
                  i=1
                  while [ "$i" -le 4001 ]; do
                    printf '1\\t/synthetic/child-%04d\\0' "$i"
                    i="$(( i + 1 ))"
                  done
                fi
                if [ "$DU_BELOW_DF" = '1' ]; then
                  # du totals 1,547,000 against df's 1,557,000 used: the ordinary ext4
                  # case -- filesystem metadata and blocks held by deleted-but-open
                  # files. /home shrinks to keep the root's own files at zero so the
                  # partition stays exact.
                  printf '2000\\t/home/claude\\0'
                  printf '2000\\t/home\\0'
                  printf '%s\\t/\\0' "$(( 1547000 + ROOT_SCAN_EXTRA ))"
                else
                  printf '12000\\t/home/claude\\0'
                  printf '12000\\t/home\\0'
                  printf '%s\\t/\\0' "$(( 1557000 + ROOT_SCAN_EXTRA ))"
                fi ;;
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
              *'AS lost_slots FROM pg_replication_slots'*)
                printf '%s\\n' '{"slots":"0","inactive_slots":"0","wal_retaining_slots":"0","wal_beyond_max_wal_size_slots":"0","lost_slots":"0"}' ;;
              *'pg_replication_slots'*)
                case "$sql" in
                  *"(wal_status = 'extended') DESC NULLS LAST, (wal_status = 'reserved') DESC NULLS LAST"*)
                    exit 0 ;;
                  *)
                    printf '%s\\n' 'slot ordering missing NULLS LAST' >&2
                    exit 3 ;;
                esac ;;
              *'pg_prepared_xacts'*)
                printf '%s\\n' '{"prepared_transactions":0}' ;;
              *'pg_ls_waldir'*)
                wal_calls=0
                if [ -f "$WAL_QUERY_STAMP" ]; then
                  wal_calls="$(cat "$WAL_QUERY_STAMP")"
                fi
                wal_calls="$(( wal_calls + 1 ))"
                printf '%s' "$wal_calls" > "$WAL_QUERY_STAMP"
                if [ "$wal_calls" -ge 2 ]; then
                  printf '{"segments":3,"bytes":%s}\\n' "$WAL_AT_WINDOW_CLOSE"
                else
                  printf '%s\\n' '{"segments":3,"bytes":118000}'
                fi ;;
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
                printf '%s\\n' '{"schema":"v3_derived","table":"system_rating_vector","index_name":"system_rating_vector_key","index_bytes":300,"is_unique":false,"is_primary":false,"idx_scan":0,"definition":"index definition","definition_length":16,"definition_truncated":false}' ;;
              *'pg_stat_user_tables'*)
                printf '%s\\n' '{"schema":"v3_derived","name":"system_rating_vector","n_live_tup":75,"n_dead_tup":25,"last_vacuum":null,"last_autovacuum":"2026-10-10 00:00:00+00","last_analyze":"2026-10-10 00:00:00+00","total_bytes":1000,"estimated_dead_fraction":0.2500,"estimated_dead_bytes":150}' ;;
              *'pg_total_relation_size'*)
                printf '%s\\n' '{"schema":"v3_derived","name":"system_rating_vector","relkind":"r","estimated_rows":100,"table_bytes":600,"heap_bytes":500,"index_bytes":300,"toast_bytes":100,"total_bytes":1000}' ;;
              *'SELECT oid::text AS oid, datname FROM pg_database'*)
                printf '%s\\n' '{"oid":"16384","datname":"edfinder_v3_db"}'
                printf '%s\\n' '{"oid":"5","datname":"postgres"}' ;;
              *'AS operating_bytes FROM pg_database'*)
                # Asked twice: once in the SQL phase and once at window close. Only
                # the CLOSING read drifts, so a test can tell which one the summary
                # used.
                dbcalls=0
                if [ -f "$DB_TOTAL_STAMP" ]; then
                  dbcalls="$(cat "$DB_TOTAL_STAMP")"
                fi
                dbcalls="$(( dbcalls + 1 ))"
                printf '%s' "$dbcalls" > "$DB_TOTAL_STAMP"
                if [ "$dbcalls" -ge 2 ]; then
                  printf '{"database_count":"2","total_bytes":"%s","operating_bytes":"%s"}\\n' "$(( 1328000 + DATABASE_GREW ))" "$(( 1320000 + DATABASE_GREW ))"
                else
                  printf '%s\\n' '{"database_count":"2","total_bytes":"1328000","operating_bytes":"1320000"}'
                fi ;;
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
    for executable in (hostname, pwd, readlink, stat_bin, docker, df, du, psql):
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
    env["WAL_SEPARATE_FILESYSTEM"] = "1" if wal_separate_filesystem else "0"
    env["PGDATA_GREW"] = str(pgdata_grew)
    env["PGDATA_AFTER_GREW"] = str(pgdata_after_grew)
    env["WAL_NESTED_MOUNT"] = "1" if wal_nested_mount else "0"
    env["PGDATA_INNER_MOUNT"] = "1" if pgdata_inner_mount else "0"
    env["VOLUME_USED_DRIFT"] = str(volume_used_drift)
    env["WAL_AT_WINDOW_CLOSE"] = str(wal_at_window_close)
    env["WAL_QUERY_STAMP"] = str(tmp_path / "wal-query-stamp")
    env["DATABASE_GREW"] = str(database_grew)
    env["DB_TOTAL_STAMP"] = str(tmp_path / "db-total-stamp")
    env["PGDATA_DEPTH0_STAMP"] = str(tmp_path / "pgdata-depth0-stamp")
    env["BASE_SCAN_DENIED"] = "1" if base_scan_denied else "0"
    env["DU_BELOW_DF"] = "1" if du_below_df else "0"
    env["DF_USED_DRIFT"] = str(df_used_drift)
    env["DF_USED_STAMP"] = str(tmp_path / "df-used-stamp")
    env["USAGE_ROOT"] = usage_root
    env["ROOT_SCAN_EXTRA"] = "5000" if root_scan_truncated else "0"
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
    # And the claim says what it covers. The shell spools a here-document above the
    # pipe-buffer size to an unlinked temporary file before the interpreter starts, so
    # an unqualified `false` overclaimed. Measured under bash 5.2.21: a 126 KB
    # here-document gives `stdin -> /tmp/sh-thd.* (deleted)` where a 62-byte one gives
    # `pipe:[...]`. The write holds this program's own text and no host data, and it
    # cannot be removed while the control plane pipes one script over SSH, so the
    # receipt reports it rather than covering it.
    assert "unlinked temporary file" in receipt["filesystem_writes_scope"]
    assert (
        "creates, modifies and deletes no file and no file content"
        in receipt["filesystem_writes_scope"]
    )
    # The second unavoidable side effect: du's reads update directory access times
    # under the kernel default. Measured from the host's mount options, not assumed.
    assert "ACCESS TIMES" in receipt["filesystem_writes_scope"]
    atime = inventory["volume"]["atime"]
    assert atime["available"] is True
    assert atime["atime_policy"] in {
        "noatime",
        "nodiratime",
        "relatime",
        "strictatime",
    }
    assert isinstance(atime["directory_atime_writes_suppressed"], bool)
    assert inventory["volume"]["avail_bytes"] == 292000
    assert {"path": "/var/log", "bytes": 30000} in inventory["volume_directory_usage"]
    assert inventory["directory_scan_same_device_mounts"] == {
        "available": True,
        "safe_to_scan": True,
        "mount_points_below_root": 0,
        "same_device_mount_count": 0,
        "same_device_mount_paths": [],
        "same_device_mount_paths_truncated": False,
    }
    assert inventory["volume_directory_usage_scan"] == {
        "record_limit": 4000,
        "records_retained": 6,
        "records_omitted_by_cap": 0,
        "omitted_record_cumulative_bytes": 0,
        "omitted_record_bytes_may_overlap": True,
        "path_attribution_complete": True,
    }
    assert inventory["databases"][0]["datname"] == "edfinder_v3_db"
    assert inventory["wal"]["bytes"] == 118000
    assert inventory["wal"]["unlisted_directory_classification"] == {
        "available": False,
        "reason": "live_wal_cannot_be_snapshotted_read_only",
    }
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
    assert inventory["summary"]["directory_scan_path_attribution_complete"] is True
    assert inventory["summary"]["candidate_list_incomplete_reasons"] == []


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
    # The root walk still scans the whole filesystem at depth 2.
    assert '"--max-depth=2",\n            usage_root,' in source
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
    inventory = json.loads(result.stdout)["inventory"]
    summary = inventory["summary"]
    assert inventory["volume_directory_usage_scan"]["records_omitted_by_cap"] == 0
    assert inventory["volume_directory_usage_scan"]["path_attribution_complete"] is True
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
    assert summary["directory_scan_path_attribution_complete"] is True
    assert summary["candidate_list_incomplete_reasons"] == []


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
    inventory = json.loads(result.stdout)["inventory"]
    summary = inventory["summary"]
    assert inventory["volume_directory_usage_scan"]["records_omitted_by_cap"] == 0
    assert inventory["volume_directory_usage_scan"]["path_attribution_complete"] is True
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
    # A live pg_wal directory cannot be snapshotted read-only, so no aggregate
    # difference is classified as reclaimable.
    wal_unlisted = (
        f"{pgdata}/pg_wal (subdirectories and files pg_ls_waldir does not list)"
    )
    assert wal_unlisted not in by_path
    # base/: the orphaned OID directory by PATH, and the 200 bytes sitting directly in
    # base/ as their own row. Not one lump remainder, and not inflated by the
    # du-versus-pg_database_size metric difference, which is its own summary term.
    # NUMERIC, so it is reported with its classification stated honestly rather than
    # asserted: a database being created copies its base/<oid> tree before its
    # pg_database row is visible to other transactions, so no number of catalog reads
    # can prove a numeric directory unreferenced. Its bytes still belong in the
    # partition -- they are real and unaccounted -- so the row is emitted, not hidden.
    orphan = (
        f"{pgdata}/base/16999 (numeric name not in the live database set; may be a "
        "database still being created -- not proven reclaimable)"
    )
    assert by_path[orphan]["exclusive_bytes"] == 500
    assert by_path[orphan]["inside_data_directory"] is True
    assert by_path[orphan]["proven_unreferenced"] is False
    base_other = f"{pgdata}/base (files directly in this directory)"
    assert by_path[base_other]["exclusive_bytes"] == 200
    # Aggregate pg_wal content is not classified; its direct 2,000-byte difference
    # from the final SQL total is a measurement width, not a candidate.
    assert summary["unaccounted_inside_data_directory_bytes"] == 15700
    assert summary["database_size_metric_difference_bytes"] == 1295
    # And the candidate list accounts for the figure it explains, to within what
    # these measurements can resolve. The only unresolved width in this fixture is the
    # du-versus-st_size width plus the direct PGDATA-WAL-to-final-SQL width.
    assert summary["candidate_shortfall_bytes"] == 3295
    assert summary["measurement_uncertainty_bytes"] == 3295
    assert {
        "term": "pg_wal_pgdata_walk_to_window_close",
        "bytes": 2000,
        "path": f"{pgdata}/pg_wal",
    } in summary["measurement_uncertainty_terms"]
    assert summary["candidate_list_complete"] is True
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True
    assert summary["directory_scan_path_attribution_complete"] is True
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

    assert "ACTION_BUDGET_SECONDS = 1_800" in source
    assert "NON_SCAN_AND_RECEIPT_BUDGET_SECONDS = 240" in source
    assert "RECONCILE_RESERVE_SECONDS = 2 * DIRECTORY_USAGE_TIMEOUT_SECONDS" in source
    assert "ACTION_BUDGET_SECONDS\n    - RECONCILE_RESERVE_SECONDS" in source
    assert "- NON_SCAN_AND_RECEIPT_BUDGET_SECONDS" in source
    assert "DIRECTORY_SCAN_BUDGET_SECONDS" not in source
    assert 960 + 600 + 240 == 1800
    assert "timeout-minutes: 40" in _read(WORKFLOW)
    assert "class ScanBudget" in source
    assert "def call_timeout(" in source
    assert "scan_budget_exhausted" in source
    assert "directory_scan_budget_exhausted" in source
    # The budget is created once and threaded through every scan.
    assert (
        source.count(
            "scan_budget = ScanBudget("
            "DIRECTORY_SCAN_WALK_SECONDS, RECONCILE_RESERVE_SECONDS)"
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
    assert "RECONCILE_RESERVE_SECONDS = 2 * DIRECTORY_USAGE_TIMEOUT_SECONDS" in source
    assert "WAL_DIRECTORY_SCAN_SECONDS" not in source
    # The budget OWNS the reserve. Passing it per call site meant forgetting it at four
    # of them, which unreserved the reserve without changing a line that mentioned it,
    # so there must be no per-call reserve argument left to forget.
    assert "reserve_seconds" not in source.split("def du_rows(")[1].split("def du_total")[0]
    assert "def charge_scan_elapsed(self, elapsed: float)" in source
    assert "self.walk_seconds_remaining -= charged" in source
    assert "self._current_closing_seconds_remaining -= charged" in source
    assert "future_closing = self.closing_scan_seconds_remaining" in source
    assert "overall = action_remaining() - non_scan_left - future_closing" in source
    # Bounded by the ACTION deadline and the independent non-scan/receipt ledger.
    assert "ACTION_BUDGET_SECONDS = 1_800" in source
    assert "NON_SCAN_AND_RECEIPT_BUDGET_SECONDS = 240" in source
    assert "non_scan_and_receipt_seconds_remaining()" in source
    assert "return min(own, overall)" in source
    # And every subprocess is measured against it, so no single call can carry the
    # action past the point where a receipt is still possible.
    assert 'raise RuntimeError("action_deadline_exceeded")' in source
    # The reserve is opened once per closing scan, and there are exactly two: PGDATA
    # and base/. A third release and an over-release are refused.
    assert source.count("def begin_closing_scan(") == 1
    assert source.count("scan_budget.begin_closing_scan(") == 2
    assert "self._closing_releases >= 2" in source
    assert "seconds > self.closing_scan_seconds_remaining" in source
    # Sub-second remainders are not rounded into an overspend.
    assert "math.ceil" not in source
    assert "max(1, min(" not in source
    release = source.index("scan_budget.begin_closing_scan()")
    # The closing scan is the FIRST du after begin_closing_scan(), so search from there
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
    budget = inventory["non_database_drill_down"]
    assert budget["action_budget_seconds"] == 1800
    assert budget["directory_scan_walk_budget_seconds"] == 960
    assert budget["closing_scan_budget_seconds"] == 600
    assert budget["non_scan_and_receipt_budget_seconds"] == 240
    assert budget["closing_scan_seconds_remaining_after_walk"] == 600
    assert budget["directory_scan_walk_seconds_remaining_after_walk"] <= 960
    assert budget["non_scan_and_receipt_seconds_remaining_after_walk"] <= 240


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
    # global 8,000 + pg_stat 4,000 + root files 3,000 + base/'s orphaned 16999
    # at 500 + base/'s own 200. Aggregate pg_wal content is deliberately not classified.
    assert summary["unaccounted_inside_data_directory_bytes"] == 15700


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
    closing_pgdata = source.index("closing_usage, pgdata_children_omitted")
    closing_base = source.index("base_usage, base_omitted, base_omitted_bytes")
    final_wal = source.index("    closing_wal = psql_json(")
    assert closing_pgdata < closing_base < final_wal < summary
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
    assert "budget.charge_scan_elapsed(time.monotonic() - attempt_started)" in source
    assert "finally:" in source.split("def du_stream(", 1)[1].split("def du_rows(", 1)[0]

    body = source.split("exec \"$PYTHON_BIN\" -I -B - <<'PY'\n", 1)[1].rsplit(
        "\nPY\n", 1
    )[0]
    definitions = body.split("receipt: dict[str, Any] = {", 1)[0]
    namespace: dict[str, object] = {}
    exec(compile(definitions, "budget-test.py", "exec"), namespace)

    class FakeTime:
        now = 0.0

        def monotonic(self) -> float:
            return self.now

    clock = FakeTime()
    namespace["time"] = clock
    namespace["ACTION_STARTED"] = 0.0
    namespace["ACTION_DEADLINE"] = 1800.0
    namespace["directory_scan_seconds_charged"] = 0.0
    budget = namespace["ScanBudget"](960, 600)
    assert budget.remaining() == 960

    # A 100-second walk consumes only the walk ledger.
    clock.now = 100.0
    budget.charge_scan_elapsed(100.0)
    assert budget.remaining() == 860
    # A later 100 seconds of SQL consumes only the 240-second non-scan bucket; it does
    # not silently steal either 300-second closing allowance.
    clock.now = 200.0
    assert namespace["non_scan_and_receipt_seconds_remaining"]() == 140
    assert budget.remaining() == 860
    budget.begin_closing_scan()
    assert budget.remaining() == 300
    clock.now = 450.0
    budget.charge_scan_elapsed(250.0)
    clock.now = 500.0
    assert namespace["non_scan_and_receipt_seconds_remaining"]() == 90
    budget.begin_closing_scan()
    assert budget.remaining() == 300


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


def test_v3_disk_inventory_treats_pg_xlog_as_unexpected_storage(tmp_path):
    """pg_ls_waldir() measures the live WAL directory, which on PostgreSQL 18 is pg_wal.

    Subtracting wal_bytes from a stale pg_xlog would treat it as measured: smaller than
    the live WAL it vanishes from the candidates, larger and only its excess shows — and
    a directory full of old WAL is exactly the reclaimable space this action looks for.
    """
    result = _run_inventory_action(tmp_path, du_layout="pg_xlog")
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    rows = {
        row["path"]: row
        for row in inventory["summary"]["largest_unaccounted_directories"]
    }
    pg_xlog = (
        f"{pgdata}/pg_xlog "
        "(not the live WAL directory on PostgreSQL 18; unexpected storage)"
    )
    assert rows[pg_xlog]["exclusive_bytes"] == 9000
    assert rows[pg_xlog]["inside_data_directory"] is True
    # pg_ls_waldir() describes pg_wal only; none of its 118,000 bytes may be
    # subtracted from the independent stale pg_xlog directory.
    assert rows[pg_xlog]["exclusive_bytes"] != 9000 - 118000


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
    # Every du invocation asks for NUL-delimited output. The root walk uses a
    # multi-line argv literal, while the other calls use compact literals.
    assert source.count('["du", "--null", "-x", "-B1"') == 5
    assert source.count('"du",\n            "--null",') == 1
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
    root_scan = source.split("usage_full, root_rows_omitted, root_rows_omitted_bytes", 1)[1]
    root_scan = root_scan.split("volume_used_after =", 1)[0]
    assert "= du_stream(" in root_scan
    assert "keep=DU_DEFAULT_KEEP" in root_scan
    assert "du_rows(" not in root_scan
    # The omitted children's bytes are returned and used, not discarded.
    assert "own_file_bytes = here_total - child_total - omitted_child_bytes" in source
    assert '"children_omitted_by_cap": omitted_children,' in source


def test_v3_disk_inventory_discloses_root_scan_truncation(tmp_path):
    result = _run_inventory_action(tmp_path, root_scan_truncated=True)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    scan = inventory["volume_directory_usage_scan"]
    assert scan == {
        "record_limit": 4000,
        "records_retained": 4000,
        "records_omitted_by_cap": 8,
        "omitted_record_cumulative_bytes": 8,
        "omitted_record_bytes_may_overlap": True,
        "path_attribution_complete": False,
    }
    summary = inventory["summary"]
    assert summary["directory_scan_path_attribution_complete"] is False
    assert summary["candidate_list_complete"] is False
    assert summary["candidate_list_incomplete_reasons"] == [
        "volume_directory_usage_scan_truncated"
    ]
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is None
    assert all(
        row["exclusive_bytes"] != scan["omitted_record_cumulative_bytes"]
        for row in summary["largest_unaccounted_directories"]
    )
    assert all(
        term["bytes"] != scan["omitted_record_cumulative_bytes"]
        for term in summary["measurement_uncertainty_terms"]
    )


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
    # The shortfall is judged against declared measurement widths; no live read-only
    # sequence is claimed to close exactly.
    assert abs(summary["candidate_shortfall_bytes"]) <= summary[
        "measurement_uncertainty_bytes"
    ]
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True


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
    # The candidate comparison is against the scan-window figure, so the 9,000 bytes
    # of drift do not have to be explained by a candidate -- which is the whole point.
    # It becomes a width instead: the volume moved by that much across the window.
    assert summary["candidate_shortfall_bytes"] == 3295
    assert {
        "term": "volume_used_across_window",
        "bytes": 9000,
    } in summary["measurement_uncertainty_terms"]
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True
    assert (
        "no instant at which all of these could be read together" in summary["method"]
    )


def test_v3_disk_inventory_pairs_the_scan_df_reading_in_time_not_just_in_name(tmp_path):
    """The paired df reading must be taken before the second 1.3 TB walk, not after.

    `pgdata_after` is another full traversal of the data directory -- minutes on this
    cluster. Reading df after it meant the "post-scan" reading described a filesystem
    state minutes newer than the root scan it is subtracted from, so everything
    written or freed during that second walk was charged to filesystem metadata and
    deleted-but-open files. Pairing has to be in time, not merely in name.
    """
    source = _read(ACTION)
    scan = source.index('"directory_usage_failed"')
    df_after = source.index("volume_used_after = df_used_bytes(mount_source)", scan)
    pgdata_after = source.index("pgdata_after = du_total(pgdata_host", scan)
    assert scan < df_after < pgdata_after


def test_v3_disk_inventory_keeps_the_base_breakdown_to_one_snapshot(tmp_path):
    """base/'s total and base/'s children must come from the same walk.

    The breakdown's children are measured by the base scan; using base's size from the
    earlier PGDATA walk mixed two snapshots minutes apart. A shrink in between then
    appeared as reclaimable "files directly in base/", and growth drove other_bytes
    negative, both in a receipt reporting success. The two measurements must also agree
    within tolerance, because the candidate partition subtracts base as an accounted
    child measured by the PGDATA walk and adds these figures back -- beyond tolerance
    they describe different directories.
    """
    source = _read(ACTION)
    # The total comes from the base scan's own root row...
    base_block = source.split("base_total = next(")[1].split("live_bytes = 0")[0]
    assert "for row in base_usage" in base_block
    # ...and other_bytes is built from it, not from the PGDATA walk's row.
    other = source.split("other_bytes = (")[1].split(")")[0]
    assert "base_total" in other
    assert 'base_row["bytes"]' not in other
    # Drift between the two is refused, not absorbed.
    assert 'abs(base_total - base_row["bytes"]) > tolerance' in source
    assert '"reason": "base_directory_changed_during_scan"' in source
    assert '"reason": "base_directory_total_missing"' in source
    # A database created or dropped between the OID query and the base scan would make
    # a live directory look orphaned, so the set is re-read and required unchanged.
    assert "oid_rows_after = psql_json(" in source
    assert "oids_after != set(live_database_oids)" in source
    assert '"reason": "live_database_oids_changed_during_base_scan"' in source


def test_v3_disk_inventory_keeps_row_capped_entries_in_the_partition(tmp_path):
    """Subtracting the omitted aggregate without adding it back deletes those bytes.

    Both caps had the same hole. For PGDATA, the outside partition has already removed
    the entire data-directory total, so children dropped by the cap left the partition
    altogether once they were also subtracted from the root-file remainder. For base/,
    with at most 50 live databases allowed, a base/ with thousands of entries is
    overwhelmingly the unexpected directories this inventory exists to find -- the
    worst possible place for a silent gap. Each cap now emits an aggregate candidate
    saying how many entries it covers and that their paths were not retained.
    """
    source = _read(ACTION)
    assert "if pgdata_children_omitted_bytes > 0:" in source
    assert "further children the row " in source
    assert 'if base_breakdown["entries_omitted_bytes"] > 0:' in source
    assert "further entries " in source
    assert source.count("paths not retained") == 2
    # The remainder rows no longer claim to cover them.
    assert (
        "(files directly in this directory, and entries the row cap dropped)"
        not in source
    )


def test_v3_disk_inventory_includes_the_df_du_residual_in_the_closure(tmp_path):
    """Every candidate is a du measurement; the figure they explain starts from df.

    So the candidates sum towards directory_scan_root_bytes while
    unaccounted_bytes_at_directory_scan starts from volume_used_bytes_at_directory_scan,
    and the gap between those two IS filesystem_minus_directory_scan_bytes. Asserting
    the closure without it made the flag false on ANY real filesystem -- df and du
    always differ by metadata and blocks held by deleted-but-open files -- so a
    perfectly exact inventory would have reported that its own candidates did not
    partition the figure they explain. The default fixture has df == du, which is the
    one place that error is invisible, so this case makes them differ.
    """
    result = _run_inventory_action(tmp_path, du_below_df=True)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]

    # du totals 1,547,000 against df's 1,557,000 used.
    assert summary["directory_scan_root_bytes"] == 1547000
    assert summary["volume_used_bytes_at_directory_scan"] == 1557000
    assert summary["filesystem_minus_directory_scan_bytes"] == 10000
    # /home shrank by 10,000 with it, so the outside total drops by the same amount.
    assert summary["non_database_directory_bytes"] == 82000
    assert summary["unaccounted_inside_data_directory_bytes"] == 15700
    assert summary["database_size_metric_difference_bytes"] == 1295

    # The residual, WAL movement and metric difference are widths, not candidates.
    assert summary["candidate_shortfall_bytes"] == 13295
    assert {
        "term": "filesystem_minus_directory_scan",
        "bytes": 10000,
    } in summary["measurement_uncertainty_terms"]
    assert summary["measurement_uncertainty_bytes"] == 13295
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True


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

    # Both observations must hold: the opening one proves none existed when the scans
    # began, the closing one proves none appeared while they ran -- which is when
    # pg_database_size would have started including bytes outside this filesystem,
    # bytes then subtracted from volume_used, with the negative base metric difference
    # able to keep the closure true. A successful receipt understating unaccounted
    # space is the one error this section exists to rule out.
    assert '"tablespaces_at_window_close"' in source
    assert "closing_tablespaces_unavailable" in source
    assert 'closing_tablespaces["single_filesystem_accounting_valid"]' in source

    result = _run_inventory_action(tmp_path, tablespace_present=True)
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["tablespaces"]["non_default_count"] == 1
    assert inventory["tablespaces_at_window_close"]["non_default_count"] == 1
    assert inventory["tablespaces"]["non_default_truncated"] is False
    assert inventory["tablespaces"]["single_filesystem_accounting_valid"] is False
    # And the partition is still refused, naming what was found.
    assert (
        inventory["summary"]["summary_failed"]
        == "tablespaces_present_single_filesystem_accounting_invalid"
    )


def test_v3_disk_inventory_carries_negative_remainders_as_uncertainty(tmp_path):
    """A remainder that comes out negative must be named, not dropped.

    Every remainder here is a measured total minus figures measured by a different
    instrument or at a different moment -- WAL recycled between the directory walk and
    pg_ls_waldir(), base/ changing between the two walks, children the row cap dropped
    -- so each can come out negative. A negative cannot be a candidate, since there is
    no negative storage to reclaim, and a shrink once turned WAL that had already been
    recycled into an "unlisted storage" candidate. Dropping it with `if x > 0` instead
    made the receipt silent about a quantity it had measured. It is recorded as a
    measurement width, which is what a difference between two readings of one thing
    actually is. One shared helper, because the same mistake was found at four sites.
    """
    source = _read(ACTION)
    assert "def remainder(path: str, value: int, *, term: str) -> None:" in source
    assert "uncertainty_terms: list[dict[str, Any]] = []" in source
    # A width has no direction, so the helper takes the magnitude.
    assert 'entry: dict[str, Any] = {"term": term, "bytes": abs(bytes_)}' in source
    # Every remainder goes through it, and none keeps its own positive-only filter.
    assert source.count("        remainder(") + source.count("    remainder(") >= 4
    assert "if wal_unlisted > 0:" not in source
    assert "if pgdata_root_files > 0:" not in source
    assert 'if base_breakdown["other_bytes"] > 0:' not in source
    assert "if tail > 0:" not in source
    # The accepted base drift is a term too: the add-backs come from the base walk
    # while the outer partition removed base as measured by the PGDATA walk, so any
    # drift inside the tolerance shifted the candidate total by exactly that amount.
    assert 'uncertain("base_directory_scan_drift", base_drift,' in source
    assert (
        'base_drift = base_breakdown["bytes_at_pgdata_scan"] - base_breakdown["bytes"]'
        in source
    )
    # And every width is summed into the figure the shortfall is judged against.
    assert (
        "measurement_uncertainty = sum(item[\"bytes\"] for item in uncertainty_terms)"
        in source
    )

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]
    # The coherent fixture still has a direct, non-reclaimable 2,000-byte WAL width,
    # followed by the du-versus-st_size metric width.
    assert [item["term"] for item in summary["measurement_uncertainty_terms"]] == [
        "pg_wal_pgdata_walk_to_window_close",
        "database_size_du_versus_st_size"
    ]
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True


def test_v3_disk_inventory_partitions_across_a_row_cap_ancestor_gap():
    """The retained set is a bounded top-k, so it is not ancestor-closed.

    The cap can keep a child while dropping its parent -- two equal-sized rows either
    side of the cutoff, the tie-break keeping the child. Subtracting only when the
    immediate parent survived then counted that child's bytes twice: once as its own
    row and again inside whichever ancestor the cap did keep, inflating the candidate
    total and breaking the closure after a scan that succeeded.
    """
    source = _read(ACTION)
    block = source.split("def exclusive_usage(")[1].split("\ndef ")[0]
    # Nearest surviving ancestor, not immediate parent.
    assert "while ancestor != \"/\":" in block
    assert "if ancestor in totals:" in block
    assert "parent = path.rsplit" not in block
    assert '"directory_scan_path_attribution_complete"' in source

    # Exercise the function itself on an ancestor gap: /var/lib dropped by the cap.
    namespace: dict[str, object] = {"Any": object}
    exec(  # noqa: S102 - running the action's own helper is the point of the test
        "from typing import Any\n" + source[source.index("def exclusive_usage(") :]
        .split("\ndef ")[0],
        namespace,
    )
    exclusive_usage = namespace["exclusive_usage"]
    rows = [
        {"path": "/", "bytes": 1000},
        {"path": "/var", "bytes": 900},
        {"path": "/var/lib/docker", "bytes": 800},
    ]
    result = exclusive_usage(rows)  # type: ignore[operator]
    # 800 is attributed to /var even though /var/lib is missing, so the exclusive
    # sizes still sum to the scanned root's total exactly once.
    assert result == {"/": 100, "/var": 100, "/var/lib/docker": 800}
    assert sum(result.values()) == 1000


def test_v3_disk_inventory_uses_the_conservative_end_of_the_pgdata_bracket(tmp_path):
    """The root walk visits PGDATA at an unknown instant inside itself.

    `pgdata_after` is a separate full traversal started only once the whole walk had
    finished, so the footprint actually inside `usage_full` is known only to lie within
    the bracket. The two errors are not symmetric: subtracting too little inflates the
    ancestor with database bytes, so the receipt points at a sibling directory as
    reclaimable space that is really the live database; subtracting too much merely
    understates genuine sibling space. Only the first can tell an operator to reclaim
    the database from somewhere else, so the maximum is the conservative choice.
    """
    # PGDATA reads 1,465,000 before the walk and 1,440,000 after -- it shrank by 25,000
    # while the walk was running, so `usage_full` holds the larger earlier footprint.
    result = _run_inventory_action(tmp_path, pgdata_after_grew=-25000)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]
    by_path = {
        row["path"]: row for row in summary["largest_unaccounted_directories"]
    }

    # The larger end is used, so /var/lib keeps its 50,000 rather than being inflated
    # to 75,000 by 25,000 bytes of removed database.
    assert summary["postgres_data_directory_bytes_used_for_outside_rows"] == 1465000
    assert by_path["/var/lib"]["exclusive_bytes"] == 50000
    # And the width of what cannot be resolved is stated rather than implied -- both
    # on its own and as a term in the figure the shortfall is judged against.
    assert summary["postgres_data_directory_within_walk_uncertainty_bytes"] == 25000
    assert {
        "term": "postgres_data_directory_bracket",
        "bytes": 25000,
    } in summary["measurement_uncertainty_terms"]
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True


def test_v3_disk_inventory_rejects_a_mount_nested_inside_pgdata(tmp_path):
    """Neither a path test nor a device test can see a mount nested inside PGDATA.

    A volume or bind attached at pg_wal's canonical destination hides a directory that
    still exists in the PGDATA volume, and from the host `stat` and `du` inspect THAT
    underlying directory -- typically empty and on PGDATA's own device. So the device
    check reports "same filesystem", `du -x` walks the empty placeholder, and
    pg_ls_waldir()'s bytes are subtracted from a footprint that never contained them.
    The container's own mount list is the only place the nesting is visible.
    """
    source = _read(ACTION)
    assert "def postgres_mounts() -> list[tuple[str, str]]:" in source
    assert "and not nested_mounts" in source
    # The mount PROVIDING PGDATA must not count as nested inside it.
    assert "if target == mount_destination.rstrip(\"/\"):" in source

    result = _run_inventory_action(tmp_path, wal_nested_mount=True)
    receipt = json.loads(result.stdout)
    wal = receipt["inventory"]["wal"]
    assert wal["nested_container_mounts"] == [
        {
            "source": "/mnt/fast-wal",
            "destination": "/var/lib/postgresql/18/docker/pg_wal",
        }
    ]
    # readlink agrees and the device agrees -- only the mount list disagrees.
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    assert wal["resolved_host_directory"] == f"{pgdata}/pg_wal"
    assert wal["same_filesystem_as_data_directory"] is True
    assert wal["directory_inside_pgdata"] is False
    assert receipt["inventory"]["summary"] == {
        "summary_failed": "wal_directory_outside_pgdata"
    }
    assert receipt["status"] == "stopped"


def test_v3_disk_inventory_carries_a_negative_outside_remainder(tmp_path):
    """The ancestor holding the data directory can go negative, and must not vanish.

    `pgdata_after` is subtracted from that ancestor's exclusive size, and it is
    measured at a different instant than `usage_full`, so PGDATA growing in between can
    drive the ancestor negative -- by up to the bracket tolerance, which is 1 GiB.
    Dropping it with a positive-only filter put that much outside the partition in a
    receipt whose closure flag would then be false. Same hazard as the inside
    remainders; this was the fifth site of the same `if x > 0`.
    """
    source = _read(ACTION)
    assert (
        'uncertain("outside_directory_negative_remainder", size, path)' in source
    )
    # The comprehension that could only drop a negative is gone.
    assert (
        'if path != data_dir and not path.startswith(f"{data_dir}/") and size > 0'
        not in source
    )

    # /var/lib totals 1,515,000 and PGDATA reads 1,520,000 on the second bracket
    # reading, so that ancestor's exclusive size is -5,000. Drift of 55,000 is well
    # inside the 1 GiB tolerance, so the run still reconciles and succeeds.
    result = _run_inventory_action(tmp_path, pgdata_after_grew=55000)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]

    paths = [row["path"] for row in summary["largest_unaccounted_directories"]]
    assert "/var/lib" not in paths
    # Recorded as a width, by magnitude: 5,000 bytes of this ancestor's size cannot be
    # resolved between the two readings, and that is what the receipt says.
    assert {
        "term": "outside_directory_negative_remainder",
        "bytes": 5000,
        "path": "/var/lib",
    } in summary["measurement_uncertainty_terms"]
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True


def test_v3_disk_inventory_ranks_dead_tuples_by_reclaimable_bytes(tmp_path):
    """The table holding the most reclaimable dead space need not be the largest.

    Dead tuples ARE reclaimable space, so drawing them from the top 20 relations by
    total size hid the moderate table that is mostly dead behind huge tables that are
    almost all live -- and with no truncation flag to say anything had been left out.
    Exactly the defect found for the index inventory, in a section where the omission
    costs more, because this is the one that says what vacuuming would return.

    Ranked by estimated dead BYTES rather than dead tuple count: the count says nothing
    about row width, so a million tiny dead rows would outrank a thousand wide ones.
    """
    source = _read(ACTION)
    assert "DEAD_TUPLE_INVENTORY_LIMIT = 100" in source
    dead_query = source.split("dead_tuple_rows = psql_json(")[1].split(
        'inventory["dead_tuples"]'
    )[0]
    # Every user table, not the largest relations, and ordered by dead bytes.
    assert "WITH largest AS" not in dead_query
    assert "FROM pg_stat_user_tables s " in dead_query
    assert "pg_table_size(s.relid)::numeric * s.n_dead_tup" in dead_query
    assert "DESC NULLS LAST" in dead_query
    assert "LIMIT {DEAD_TUPLE_INVENTORY_LIMIT + 1}" in dead_query
    # numeric throughout, so no intermediate can overflow the way a bigint product
    # would on a large table.
    assert "::numeric" in dead_query
    # The now-unused relations CTE is gone rather than left as dead code in a
    # production action.
    assert "largest_relations_sql" not in source

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["dead_tuple_inventory_limit"] == 100
    assert inventory["dead_tuple_inventory_truncated"] is False
    assert inventory["dead_tuple_inventory_scope"] == (
        "all_user_tables_ranked_by_estimated_dead_bytes"
    )
    assert inventory["dead_tuples"][0]["estimated_dead_bytes"] == 150


def test_v3_disk_inventory_ranks_indexes_globally_before_capping(tmp_path):
    """A large index on a relation outside the top 20 was invisible and unreported.

    The 21st relation can be mostly one very large index while the first 20 are larger
    only because of heap data. Drawing indexes from the largest relations meant that
    index was absent while indexes_truncated still said false -- an omission with no
    indication it happened, in a receipt about reclaiming space.
    """
    source = _read(ACTION)
    index_query = source.split('inventory["indexes"] = psql_json(')[1].split(
        'inventory["indexes_truncated"]'
    )[0]
    assert "WITH largest AS" not in index_query
    assert "FROM pg_index x JOIN pg_class i ON i.oid=x.indexrelid" in index_query
    assert "ORDER BY pg_relation_size(i.oid) DESC" in index_query

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["index_inventory_scope"] == "all_user_indexes_ranked_by_size"
    assert inventory["index_inventory_limit"] == 200
    assert inventory["indexes_truncated"] is False


def test_v3_disk_inventory_writes_no_bytecode():
    """The receipt states filesystem_writes_performed: false unconditionally.

    Without -B, importing `platform` or any stdlib module whose bytecode cache is
    missing or stale writes .pyc files -- and this action runs as root. A read-only
    claim has to be true to be worth making.
    """
    source = _read(ACTION)
    assert '"$PYTHON_BIN" -I -B -c' in source
    assert "exec \"$PYTHON_BIN\" -I -B - <<'PY'" in source
    # -I is the load-bearing flag, not -B. Without isolated mode CPython prepends the
    # working directory to sys.path, and the workflow runs `cd /opt/ed-finder` then
    # escalates with `sudo -n bash -s`, so a planted top-level platform.py in that
    # checkout would execute AS ROOT during the version probe. -B only stops bytecode
    # writes. Asserted as a pair so neither can be dropped while the other stays.
    assert source.count('"$PYTHON_BIN" -I -B') == 2
    assert '"filesystem_writes_performed":false' in source
    # The one write that -B cannot prevent is the shell's own here-document spool, and
    # the receipt names it rather than leaving the claim unqualified. The two early
    # stopped receipts need no such note: bash spools a here-document when it reaches
    # that command, and both of them exit before the exec.
    assert '"filesystem_writes_scope": (' in source


def test_v3_disk_inventory_keeps_pgdata_drift_out_of_outside_candidates(tmp_path):
    """Database churn must never be presented as reclaimable storage on a sibling path.

    `usage_full` holds the data directory's footprint as it was during the root walk,
    so subtracting the CLOSING size from its ancestor charged the intervening database
    churn to a sibling path: a shrink inflated an outside candidate such as /var/lib by
    the removed database bytes, growth suppressed it and could drive it negative.
    post_scan_volume_drift_bytes does not undo that -- it is a volume-level term and
    says nothing about which path the bytes were attributed to -- so the receipt could
    report success, and a true closure, while pointing an operator at a sibling
    directory as reclaimable space that is actually the live database moving.
    """
    source = _read(ACTION)
    # The CONSERVATIVE end of the bracket. pgdata_after is a separate traversal
    # started after the whole root walk, not a measurement of PGDATA at the moment the
    # walk visited it, so the footprint in usage_full is only known to lie within the
    # bracket. Subtracting too little inflates the ancestor with database bytes;
    # subtracting too much merely understates sibling space. Only the first can tell
    # an operator to reclaim the database from somewhere else.
    assert "pgdata_scan_side = max(pgdata_before, pgdata_after)" in source
    assert "exclusive[container] -= pgdata_scan_side" in source
    assert "postgres_data_directory_scan_side_size_unavailable" in source
    assert (
        'uncertain("postgres_data_directory_scan_to_close_drift", -pgdata_span,'
        in source
    )

    # PGDATA grows by 7,000 between the root walk and the closing scan.
    result = _run_inventory_action(tmp_path, pgdata_grew=7000)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    summary = inventory["summary"]
    by_path = {
        row["path"]: row for row in summary["largest_unaccounted_directories"]
    }

    # /var/lib is the ancestor holding the data directory. Its exclusive size is
    # unchanged by the growth -- 1,515,000 less the 1,465,000 measured beside the walk.
    # Under the closing figure it would have been 43,000, and the receipt would have
    # shown 7,000 bytes of live database as sibling storage.
    assert by_path["/var/lib"]["exclusive_bytes"] == 50000
    assert summary["non_database_directory_bytes"] == 92000
    # The growth lands inside the data directory, where it belongs: 3,000 of root files
    # plus the 7,000 the closing scan now sees.
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    assert by_path[f"{pgdata} (files directly in this directory)"][
        "exclusive_bytes"
    ] == 10000
    # And the deliberate difference between the two sides is named as a width, so the
    # 7,000 bytes are visible in the receipt rather than implied by a number that does
    # not add up.
    assert {
        "term": "postgres_data_directory_scan_to_close_drift",
        "bytes": 7000,
        "path": pgdata,
    } in summary["measurement_uncertainty_terms"]
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True


def test_v3_disk_inventory_detects_wal_mounted_at_its_canonical_path(tmp_path):
    """A path test cannot see a separate filesystem mounted where pg_wal belongs.

    A Docker volume or bind mount attached directly at pg_wal's canonical destination
    is not a symlink, so `readlink -f` returns exactly the expected pathname and the
    path test says "inside". But the PGDATA walk uses `du -x`, which does not cross
    filesystem boundaries, so that WAL's bytes are not in the PGDATA total -- while
    the summary still subtracts pg_ls_waldir()'s figure from this volume. The result
    is a successful receipt whose partition is invalid, invisible to the path check.

    Device identity is the right test because `stat -c %d` reads the same st_dev the
    kernel gives `du -x` to decide whether to descend, so it tests exactly the property
    the arithmetic depends on rather than enumerating mount kinds and hoping the list
    is complete.
    """
    source = _read(ACTION)
    assert '"stat", "-c", "%d"' in source
    assert "wal_same_filesystem is True" in source

    # Normal layout: same device, so the partition is presented.
    same = tmp_path / "same-device"
    same.mkdir()
    result = _run_inventory_action(same)
    assert result.returncode == 0, result.stderr or result.stdout
    wal = json.loads(result.stdout)["inventory"]["wal"]
    assert wal["same_filesystem_as_data_directory"] is True
    assert wal["directory_inside_pgdata"] is True

    # Mounted at the canonical path: readlink agrees, the device does not.
    mounted = tmp_path / "mounted-at-canonical-path"
    mounted.mkdir()
    result = _run_inventory_action(mounted, wal_separate_filesystem=True)
    receipt = json.loads(result.stdout)
    wal = receipt["inventory"]["wal"]
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    assert wal["resolved_host_directory"] == f"{pgdata}/pg_wal"
    assert wal["host_device"] == 2049
    assert wal["data_directory_device"] == 2048
    assert wal["same_filesystem_as_data_directory"] is False
    assert wal["directory_inside_pgdata"] is False
    # And the partition is refused rather than presented, as for a relocated pg_wal.
    assert receipt["inventory"]["summary"] == {
        "summary_failed": "wal_directory_outside_pgdata"
    }
    assert receipt["status"] == "stopped"


def test_v3_disk_inventory_distinguishes_an_unknown_count_from_zero(tmp_path):
    """"We did not look that far" and "there is nothing there" are different facts.

    The products have different histories, so a generation retained by one
    attribution query can fall beyond another product's row cap. Its absence from
    that product then means the cap cut it off -- but a zero was emitted, which makes
    a superseded generation look as though it holds none of that product's data. That
    is exactly the judgement someone deciding what to reclaim would act on, and only
    one of the two readings is a licence to do it.
    """
    source = _read(ACTION)
    assert "product_truncated: dict[str, bool] = {}" in source
    assert (
        "product_truncated[product] = len(rows) > GENERATION_ATTRIBUTION_LIMIT"
        in source
    )
    assert "unknown = values is None and product_truncated.get(product, False)" in source
    # The ratings body counts take the same rule rather than being left behind.
    assert 'ratings_unknown = ratings_counts is None and product_truncated.get(' in source

    # The fixture is not truncated, so absence still means zero and the receipt is
    # unchanged -- which is what makes null a signal rather than noise.
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    attribution = json.loads(result.stdout)["inventory"]["generation_attribution"]
    assert attribution["aaa_superseded"]["search_chunks"] == 0
    assert attribution["aaa_superseded"]["ratings_physical_bodies"] == 20


def test_v3_disk_inventory_never_classifies_live_wal_from_equal_endpoints(tmp_path):
    """Equal sequential readings do not make a live, non-monotonic directory atomic."""
    source = _read(ACTION)
    assert "reclosing_wal = psql_json(" not in source
    assert "wal_snapshot_stable = wal_bytes_at_close == wal_bytes_after_scan" not in source
    assert "max(wal_bytes_at_close, wal_bytes_after_scan)" not in source
    assert "wal_dir_bytes_at_sql" not in source
    assert "wal_unlisted =" not in source
    for deleted_field in (
        "directory_bytes_beside_sql_read",
        "listed_bytes_before_directory_scan",
        "listed_bytes_after_directory_scan",
        "listed_bytes_for_candidate",
        "directory_paired_to_one_snapshot",
        "listed_bytes_scan_bracket_width",
    ):
        assert deleted_field not in source

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["wal"]["unlisted_directory_classification"] == {
        "available": False,
        "reason": "live_wal_cannot_be_snapshotted_read_only",
    }
    assert not any(
        "subdirectories and files pg_ls_waldir does not list" in row["path"]
        for row in inventory["summary"]["largest_unaccounted_directories"]
    )


def test_v3_disk_inventory_keeps_recycled_wal_out_of_candidates(tmp_path):
    """Already-removed WAL must not be reported as reclaimable storage.

    The closing walk visits `pg_wal` at some point inside its own traversal, and
    `pg_ls_waldir()` runs after the walk finishes. WAL recycled in between leaves the
    walk holding the LARGER figure, so `wal_unlisted` came out positive and was
    emitted as an "unlisted subdirectories and files" candidate -- WAL that had
    already been removed, presented as space to reclaim. And because the smaller SQL
    value also feeds `accounted_bytes`, the closure stayed true while it happened, so
    nothing caught it. Only the negative sign took the drift path, which meant the
    shrink case the adjacent comment acknowledged was the one still landing in
    candidates.

    The only safe output is the direct width from the retained PGDATA child to the one
    final SQL aggregate, never an aggregate reclaim candidate.
    """
    source = _read(ACTION)
    assert "wal_dir_bytes_at_sql = du_total(wal_host_dir, scan_budget)" not in source
    assert '"pg_wal_pgdata_walk_to_window_close",' in source
    assert "if wal_unlisted > 0" not in source

    # Opening SQL saw 118,000, the closing PGDATA child saw 120,000, and final SQL saw
    # 116,000. Only abs(P-A) = 4,000 is carried.
    result = _run_inventory_action(tmp_path, wal_at_window_close=116000)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    summary = inventory["summary"]
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"

    assert inventory["wal"]["bytes"] == 118000
    assert inventory["wal"]["bytes_at_window_close"] == 116000
    unlisted = f"{pgdata}/pg_wal (subdirectories and files pg_ls_waldir does not list)"
    assert unlisted not in {
        row["path"] for row in summary["largest_unaccounted_directories"]
    }
    assert {
        "term": "pg_wal_pgdata_walk_to_window_close",
        "bytes": 4000,
        "path": f"{pgdata}/pg_wal",
    } in summary["measurement_uncertainty_terms"]
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True
    assert not any(
        failure.startswith("candidates_do_not_account_for_unaccounted")
        for failure in json.loads(result.stdout)["failures"]
    )


def test_v3_disk_inventory_gives_the_df_du_residual_an_error_bar(tmp_path):
    """`df` is one instant; `du` is a traversal. The residual needs its own width.

    A sibling consumer changing WHILE the root walk runs leaves its earlier or
    partly-observed size in `directory_scan_root_bytes`. The before/after volume
    bracket deliberately permits that drift -- refusing on any movement would fail
    every run on a live host -- but it was not removed from the residual, so ordinary
    directory growth could be reported as filesystem metadata or blocks held by
    deleted-but-open files. Those are the two things an operator chases when this
    figure is flagged, and neither would have been there.

    The substantive fix is the reported error bar. The extra significance condition is
    correct in general but INERT at production scale, and saying so is part of being
    honest about it: the bracket permits at most max(1 GiB, 0.5% of used) while
    significance needs 2% of used, so the drift can only exceed the threshold on a
    volume under about 50 GiB. Production is 1,815 GiB. The figure is what an operator
    reads; the condition only earns its place on a small volume where the 1 GiB floor
    dominates.
    """
    source = _read(ACTION)
    assert "intra_scan_drift = abs(volume_used_at_scan - opening_used)" in source
    assert "and abs(residual) > intra_scan_drift" in source
    assert "volume_used_opening_unavailable" in source

    # du totals 1,547,000 against df's 1,557,000 at the scan, so the residual is
    # 10,000 -- and the volume moved 12,000 during the walk, so the residual is
    # smaller than the window it was measured across and explains nothing on its own.
    result = _run_inventory_action(tmp_path, du_below_df=True, volume_used_drift=-12000)
    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(result.stdout)["inventory"]["summary"]
    assert summary["filesystem_minus_directory_scan_bytes"] == 10000
    assert summary["filesystem_minus_directory_scan_uncertainty_bytes"] == 12000
    assert summary["filesystem_minus_directory_scan_is_significant"] is False
    # The method says what the error bar means, so the figure is not left to be
    # interpreted as metadata or deleted-but-open blocks on its own.
    assert "filesystem_minus_directory_scan_uncertainty_bytes" in summary["method"]


def test_v3_disk_inventory_reads_database_sizes_at_the_closing_window(tmp_path):
    """accounted_bytes claims to describe one state, so every operand must be closing.

    The PGDATA and WAL figures were, but the database and temp totals came from the
    SQL phase -- so a database growing or shrinking in between, freely within the
    multi-GiB PGDATA tolerance, landed in `database_size_metric_difference_bytes`.
    That term is documented as a `du`-versus-`st_size` difference and nothing else, so
    temporal drift hid inside a metrological one, and the headline unaccounted figure
    was wrong by the database change while the closure still held.
    """
    source = _read(ACTION)
    assert "closing_database_rows = psql_json(" in source
    assert "operating_database_bytes = operating_database_bytes_at_close" in source
    assert "temp_bytes = temp_bytes_at_close" in source
    # Aggregates only, so re-reading costs no row lists.
    closing = source.split("closing_database_rows = psql_json(")[1].split(
        "if len(closing_database_rows)"
    )[0]
    assert "LIMIT" not in closing
    assert "datname=current_database()" in closing

    # The operating database grows 9,000 bytes between the SQL phase and the close.
    result = _run_inventory_action(tmp_path, database_grew=9000)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    summary = inventory["summary"]

    # The opening read is kept as a bracket, so the movement is visible...
    assert inventory["databases"][0]["size_bytes"] == 1320000
    assert inventory["databases_at_window_close"] == {
        "operating_database_bytes": 1329000,
        "database_total_bytes": 1337000,
        "temp_directory_bytes": 5,
        "operating_database_drift_bytes": 9000,
        "database_total_drift_bytes": 9000,
        "measured_at": "window_close",
    }
    # ...and the summary uses the CLOSING figure, so accounted_bytes rises by 9,000
    # and the headline unaccounted figure falls by it, rather than the difference
    # being absorbed into the metric-only term.
    assert summary["operating_database_bytes"] == 1329000
    assert summary["accounted_bytes"] == 1446005 + 9000
    assert summary["unaccounted_bytes"] == 1557000 - (1446005 + 9000)
    # The metric difference stays metrological: du's live total against the CLOSING
    # st_size sum, so it drops by exactly the 9,000 that is no longer misattributed.
    assert summary["database_size_metric_difference_bytes"] == 1295 - 9000
    # The database's own movement across the window is a width too, so the shortfall is
    # judged against a figure that includes it rather than against the metric term
    # alone.
    assert {
        "term": "database_total_across_window",
        "bytes": 9000,
    } in summary["measurement_uncertainty_terms"]
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is True


def test_v3_disk_inventory_resolves_pgdata_through_the_deepest_covering_mount(tmp_path):
    """A name heuristic can select an outer mount while a deeper one provides PGDATA.

    With `/var/lib/postgresql` mounted AND `/var/lib/postgresql/18` mounted beneath
    it, PGDATA `/var/lib/postgresql/18/docker` is actually provided by the inner
    mount. Selecting the outer one mapped PGDATA into that mount's hidden underlying
    tree; if a stale directory happened to exist there, the path and device checks
    would both pass while every scan measured the wrong filesystem. Choosing the
    deepest covering mount makes an intervening mount impossible rather than merely
    detectable, so there is nothing left to check for.
    """
    source = _read(ACTION)
    # The data directory is read FIRST, so the mount can be chosen by containment.
    assert "def container_data_directory(db_user: str, db_name: str) -> str:" in source
    create = source.index("container_pgdata_path = container_data_directory(")
    select = source.index("mount_source, mount_destination = postgres_mount(")
    assert create < select
    # Containment and depth, not a destination name.
    assert 'container_pgdata == target or container_pgdata.startswith(f"{target}/")' in (
        source
    )
    assert "if best is None or len(target) > best[0]:" in source
    assert '"/var/lib/postgresql/data"' not in source

    # The INNER mount is selected, so PGDATA maps through /mnt/pg18 rather than
    # through the outer volume's hidden underlying tree. The run then stops because
    # the fixture's df/du stubs only model the ordinary single-mount layout, which is
    # the honest scope of this test: threading a whole alternate filesystem through
    # the stubs would not test the selection any harder.
    result = _run_inventory_action(tmp_path, pgdata_inner_mount=True)
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["postgres_data_directory"] == {
        "container_path": "/var/lib/postgresql/18/docker",
        "host_path": "/mnt/pg18/docker",
        "mount_destination": "/var/lib/postgresql/18",
    }
    # And on the ordinary layout the outer mount is still selected, so the change is
    # a refinement of the selection rather than a different answer for the real host.
    (tmp_path / "ordinary").mkdir()
    ordinary = _run_inventory_action(tmp_path / "ordinary")
    assert json.loads(ordinary.stdout)["inventory"]["postgres_data_directory"] == {
        "container_path": "/var/lib/postgresql/18/docker",
        "host_path": "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker",
        "mount_destination": "/var/lib/postgresql",
    }


def test_v3_disk_inventory_measures_the_atime_policy_rather_than_assuming_it():
    """du's own reads can write, and whether they do is a property of the host.

    `du` reads every directory it traverses, and under the kernel's DEFAULT
    `relatime` that read updates the directory's access time whenever the stored
    atime predates mtime/ctime or is over 24 hours old; `strictatime` updates on
    every access. So "this action modifies nothing" is true only under `noatime` or
    `nodiratime`, which is a mount option on the production host and not something
    this code controls. It is therefore measured and reported, in both directions --
    an unconditional disclaimer would be as wrong as the unconditional denial was.
    """
    source = _read(ACTION)
    assert "def mount_atime_policy(path: str) -> dict[str, Any]:" in source
    # Read from /proc/mounts: reading a virtual file writes nothing, and it does not
    # depend on findmnt being installed on the host.
    assert 'PROC_MOUNTS = "/proc/mounts"' in source
    assert "open(PROC_MOUNTS" in source
    # Longest matching mount point wins, because a nested mount governs what is below
    # it -- the same reasoning as the nearest-ancestor attribution in exclusive_usage.
    assert "if best is None or len(stripped) > best[0]:" in source
    # /proc/mounts octal-escapes separators; a mount point containing a space must not
    # be mis-parsed into the options column.
    assert '.replace("\\\\040", " ")' in source
    # nodiratime alone is sufficient: du's writes would be to DIRECTORY atimes.
    assert '"noatime" in options or "nodiratime" in options' in source
    # relatime is the default when nothing is specified, so absence means relatime --
    # not "no atime updates".
    assert 'policy = "relatime"' in source


def test_v3_disk_inventory_requires_the_wal_directory_in_the_retained_children():
    """pg_wal must survive the child cap; pg_xlog legitimately may not exist.

    The subtraction of wal_bytes happens at exactly one place, so a pg_wal dropped by
    the size-based child cap would skip it while the omitted-children aggregate still
    reported those bytes as an unaccounted candidate -- live, already-accounted WAL
    presented as a reclaim candidate, with the closure flag false and the receipt still
    reporting success. A data directory always has a WAL directory, so its absence from
    the retained children means the cap took it.
    """
    source = _read(ACTION)
    assert 'if name == "pg_wal":' in source
    assert "wal_directory_not_observed_in_data_directory" in source


def test_v3_disk_inventory_tolerates_only_terminal_vanished_diagnostics():
    """A path containing the marker text must not make a real error look like churn.

    GNU du writes "du: cannot access 'PATH': REASON", the reason is the terminal text,
    and this scan covers the whole filesystem including operator-uncontrolled names. A
    file literally named "No such file or directory" would have made a Permission
    denied line on it match as harmless churn, after which the action accepts an
    incomplete scan and reports success.
    """
    source = _read(ACTION)
    assert "line.rstrip().endswith(marker)" in source
    assert "any(marker in line for marker in DU_VANISHED_MARKERS)" not in source


def test_v3_disk_inventory_bounds_replication_slots_by_wal_actually_retained(tmp_path):
    """pg_replication_slots is as unbounded as pg_database, and the obvious order is wrong.

    The view lists every slot that exists and max_replication_slots is operator
    configuration, so the counts come from an aggregate and the sample is bounded. The
    ORDER has to follow PostgreSQL's documented wal_status semantics, which invert the
    intuitive reading: `extended` means "max_wal_size is exceeded but the files are
    still retained" -- the state that actually puts unexpected WAL on the volume --
    while `unreserved` means the slot "no longer retains the required WAL files" and
    `lost` means it "is no longer usable". Ordering by lost/unreserved first filled the
    sample with slots that had already stopped holding WAL and could drop the ones
    responsible for it, while the receipt claimed the sample was ordered by WAL held.
    """
    source = _read(ACTION)
    assert "REPLICATION_SLOT_INVENTORY_LIMIT = 50" in source
    assert "LIMIT {REPLICATION_SLOT_INVENTORY_LIMIT}" in source
    # Counting what retains WAL, not what has stopped: the old counter filtered on
    # ('unreserved','lost') and reported it as the WAL-pinning count.
    assert "wal_status IN ('reserved','extended')" in source
    assert "AS wal_pinning_slots" not in source
    # QUALIFIED in ORDER BY. An unqualified name resolves to the OUTPUT column first,
    # and `restart_lsn::text AS restart_lsn` makes that output text -- so the sort was
    # lexicographic over hex LSNs, where '10/...' precedes the OLDER 'F/...'. The
    # bounded sample could therefore fill with newer slots and omit the one retaining
    # the most WAL: exactly the row this ordering exists to keep.
    assert "pg_replication_slots.restart_lsn ASC NULLS LAST" in source
    # extended first, then reserved, then furthest behind by restart_lsn.
    assert "ORDER BY (wal_status = 'extended') DESC NULLS LAST, " in source
    assert "(wal_status = 'reserved') DESC NULLS LAST, " in source
    assert "(wal_status = 'extended') DESC, " not in source
    assert "(wal_status = 'reserved') DESC, " not in source
    assert "restart_lsn ASC NULLS LAST, slot_name " in source

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    wal = json.loads(result.stdout)["inventory"]["wal"]
    assert wal["replication_slot_count"] == 0
    assert wal["inactive_replication_slot_count"] == 0
    assert wal["wal_retaining_replication_slot_count"] == 0
    assert wal["wal_beyond_max_wal_size_replication_slot_count"] == 0
    assert wal["lost_replication_slot_count"] == 0
    assert wal["replication_slot_sample_order"] == (
        "wal_retained_then_oldest_restart_lsn"
    )
    assert wal["replication_slots_truncated"] is False


def test_v3_disk_inventory_requires_the_temp_directory_through_the_base_cap(tmp_path):
    """base/pgsql_tmp must survive the cap for the same reason the live OIDs must.

    Its bytes are already inside accounted_bytes via pg_ls_tmpdir(), so a size-based
    cap that drops it presents the live temporary directory among the unaccounted
    candidates while it is still being subtracted as accounted -- and the negative
    metric-difference term that follows can leave the closure flag true. Only required
    when the directory exists: the wrapper returns NULL when base/pgsql_tmp is not a
    directory, and a cluster that has never spilled to disk legitimately has none.
    """
    source = _read(ACTION)
    # From an observation taken BESIDE the base scan, not the opening query: a
    # pgsql_tmp created in between left the opening reading None, so the guard
    # permitted a breakdown whose cap had dropped a directory accounted_bytes now
    # subtracts, and the negative metric difference could offset it and leave the
    # closure true. The existence test and the subtracted figure must come from
    # observations that bracket the scan rather than precede the whole phase.
    assert "temp_probe_rows = psql_json(" in source
    assert "temp_directory_exists = temp_directory_exists_at_close" in source
    probe = source.index("temp_probe_rows = psql_json(")
    base_scan = source.index("base_usage, base_omitted, base_omitted_bytes = du_stream(")
    assert probe < base_scan
    assert "temp_directory_observed = any(" in source
    # BRACKETED both sides of the scan. One probe before it was not enough: a
    # pgsql_tmp created while the up-to-300-second base walk ran, then dropped by the
    # row cap, left the pre-scan boolean false while the closing query counts its
    # bytes in accounted_bytes -- so the omitted aggregate presents live temp bytes as
    # a candidate and the negative metric-difference term can keep the closure true.
    assert "temp_after_rows = psql_json(" in source
    assert "elif temp_directory_exists != temp_exists_after_scan:" in source
    assert '"reason": "temporary_directory_changed_during_base_scan"' in source
    # Either observation seeing it is enough to require that the scan observed it.
    assert (
        "temp_directory_exists or temp_exists_after_scan\n"
        "                ) and not temp_directory_observed:" in source
    )
    assert '"reason": "temporary_directory_not_observed"' in source


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
    # base/ is no longer an "unavailable" reason: like pg_wal it is REQUIRED, because
    # the omitted-children aggregate would otherwise report all live database storage
    # as an unaccounted candidate while the null verdict let the run succeed.
    assert "base_directory_not_observed_in_data_directory" in source
    # The budget is no longer a reason of its own here: each closing scan is given its
    # own full allowance, so an exhausted budget surfaces as the scan's own failure
    # rather than as a pre-emptive skip against a deadline the scan never had.
    assert "scan_budget.begin_closing_scan()" in source
    # Unavailable means no claim, not a claim of zero: no metric difference is
    # computed, and the candidate list declares itself incomplete so the shortfall it
    # reports is not read as a verdict.
    assert "metric_difference = None" in source
    assert (
        "candidate_list_complete = bool(base_breakdown_used) and root_rows_omitted == 0"
        in source
    )
    assert "if candidate_list_complete" in source
    # And null is distinguished from false at the failure site, so "cannot be asserted"
    # does not stop the operation the way "disproved" does.
    assert "if accounted_within_uncertainty is False:" in source
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
    # ...but makes NO base claim, and declares the candidate list incomplete rather
    # than judging a shortfall that contains a gap this action left knowingly. The
    # shortfall is still reported -- it is still the best description of what was
    # measured -- but the verdict is null, not false, so the run is not failed by a
    # gap whose cause is already recorded.
    assert summary["database_size_metric_difference_bytes"] is None
    assert summary["candidate_list_complete"] is False
    assert summary["candidates_account_for_unaccounted_within_uncertainty"] is None
    assert summary["candidate_shortfall_bytes"] == 3995
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
    """The final WAL total is accounted without classifying a sequential difference."""
    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]

    assert inventory["wal"]["bytes_at_window_close"] == 118000
    pgdata = "/var/lib/docker/volumes/edfinder-pgdata/_data/18/docker"
    by_path = {
        row["path"]: row
        for row in inventory["summary"]["largest_unaccounted_directories"]
    }
    wal_unlisted = f"{pgdata}/pg_wal (subdirectories and files pg_ls_waldir does not list)"
    assert wal_unlisted not in by_path
    assert inventory["wal"]["unlisted_directory_classification"] == {
        "available": False,
        "reason": "live_wal_cannot_be_snapshotted_read_only",
    }
    assert {
        "term": "pg_wal_pgdata_walk_to_window_close",
        "bytes": 2000,
        "path": f"{pgdata}/pg_wal",
    } in inventory["summary"]["measurement_uncertainty_terms"]


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


def test_v3_disk_inventory_reports_relation_inventory_truncation(tmp_path):
    """The relations list was the only bounded list without a truncation flag.

    Unlike the index and dead-tuple inventories an operator could not tell an
    exhaustive result from a partial one, so a database whose space is spread across
    many medium-sized relations looked as though it had no further relation-level
    consumers -- a silent omission in the section that answers "what is big".
    """
    source = _read(ACTION)
    assert "RELATION_INVENTORY_LIMIT = 80" in source
    assert "LIMIT {RELATION_INVENTORY_LIMIT + 1}" in source

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    inventory = json.loads(result.stdout)["inventory"]
    assert inventory["relation_inventory_limit"] == 80
    assert inventory["relation_inventory_truncated"] is False


def test_v3_disk_inventory_checks_nested_mounts_before_the_first_du(tmp_path):
    source = _read(ACTION)
    assert 'PROC_MOUNTS = "/proc/mounts"' in source
    assert "def same_device_nested_mounts(root: str) -> dict[str, Any]:" in source
    assert "os.stat(base).st_dev" in source
    assert "os.stat(point).st_dev" in source
    assert "def same_device_aliases(" not in source
    assert "directory_scan_same_device_aliases" not in source
    assert "alias_excludes" not in source
    assert "--exclude=" not in source
    assert 'run(["stat", "-c", "%d %i", point])' not in source
    check = source.index("nested_mount_report = same_device_nested_mounts(usage_root)")
    first_du = source.index("pgdata_before = du_total(pgdata_host, scan_budget)")
    assert check < first_du

    result = _run_inventory_action(tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)["inventory"]["directory_scan_same_device_mounts"]
    assert report["available"] is True
    assert report["safe_to_scan"] is True
    assert report["mount_points_below_root"] == 0


def test_v3_disk_inventory_refuses_a_same_device_nested_mount(tmp_path):
    result = _run_inventory_action(tmp_path, nested_mount_mode="same_device")
    assert result.returncode == 1, result.stderr or result.stdout
    receipt = json.loads(result.stdout)
    report = receipt["inventory"]["directory_scan_same_device_mounts"]
    nested = str(tmp_path / "scan-root" / "nested")
    assert report["reason"] == "same_device_nested_mount_under_scan_root"
    assert report["safe_to_scan"] is False
    assert report["same_device_mount_count"] == 1
    assert report["same_device_mount_paths"] == [nested]
    assert report["same_device_mount_paths_truncated"] is False
    assert (
        receipt["inventory"]["volume_directory_usage"][
            "volume_directory_usage_failed"
        ]
        == "same_device_nested_mount_under_scan_root"
    )


def test_v3_disk_inventory_refuses_an_unreadable_mount_table(tmp_path):
    result = _run_inventory_action(tmp_path, nested_mount_mode="unreadable")
    assert result.returncode == 1, result.stderr or result.stdout
    receipt = json.loads(result.stdout)
    report = receipt["inventory"]["directory_scan_same_device_mounts"]
    assert report["available"] is False
    assert report["reason"] == "proc_mounts_unreadable"
    assert (
        receipt["inventory"]["volume_directory_usage"][
            "volume_directory_usage_failed"
        ]
        == "proc_mounts_unreadable"
    )


def test_v3_disk_inventory_allows_a_different_device_nested_mount(tmp_path):
    result = _run_inventory_action(tmp_path, nested_mount_mode="different_device")
    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)["inventory"]["directory_scan_same_device_mounts"]
    assert report["available"] is True
    assert report["safe_to_scan"] is True
    assert report["mount_points_below_root"] == 1
    assert report["same_device_mount_count"] == 0
    assert report["same_device_mount_paths"] == []


def test_v3_disk_inventory_refuses_a_failed_nested_mount_stat(tmp_path):
    result = _run_inventory_action(tmp_path, nested_mount_mode="stat_failure")
    assert result.returncode == 1, result.stderr or result.stdout
    receipt = json.loads(result.stdout)
    report = receipt["inventory"]["directory_scan_same_device_mounts"]
    missing = str(tmp_path / "scan-root" / "nested")
    assert report["reason"] == "nested_mount_stat_failed"
    assert report["failed_stat_paths"] == [missing]
    assert report["failed_stat_path_count"] == 1
    assert report["failed_stat_paths_truncated"] is False
