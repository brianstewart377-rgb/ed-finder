"""Guards for the versioned V3 production backup schedule.

These files previously existed only on the production host, so a broken guard in
the wrapper failed nightly for twelve days with nothing visible in CI. The
assertions below pin the properties that failure depended on.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "deploy/v3-production/backup"
WRAPPER = BACKUP / "pgbackrest-operation.sh"
SERVICE = BACKUP / "edfinder-v3-pgbackrest@.service"
TIMERS = {
    "full": BACKUP / "edfinder-v3-backup-full.timer",
    "diff": BACKUP / "edfinder-v3-backup-diff.timer",
    "verify": BACKUP / "edfinder-v3-backup-verify.timer",
}


def test_wrapper_reads_the_container_process_table_with_a_pid_column():
    source = WRAPPER.read_text(encoding="utf-8")

    # Docker rejects ps output without a PID column, and the suppressed stderr
    # plus `set -euo pipefail` turned that into a silent no-op backup.
    assert 'docker top "$c" -eo pid,args' in source
    assert "-eo args 2>/dev/null" not in source


def test_wrapper_never_falls_back_to_the_local_mount_directory():
    source = WRAPPER.read_text(encoding="utf-8")

    assert "mount='/mnt/ed-storagebox'" in source
    assert 'mountpoint -q "$mount"' in source
    assert "fuse.rclone" in source
    # Every refusal is a SKIP with status 0, so a missing mount cannot look like
    # a successful backup.
    assert source.count("exit 0") >= 4
    assert "SKIP:" in source


def test_wrapper_supports_exactly_the_scheduled_operations():
    source = WRAPPER.read_text(encoding="utf-8")

    assert 'case "$op" in full|diff|verify)' in source
    assert 'pgbackrest --stanza=edfinder_v3 --log-level-console=info verify' in source
    assert '--type="$op" --log-level-console=info backup' in source
    # The stanza must be healthy before anything is written.
    assert '--output=json info' in source
    assert '=="ok"' in source


def test_service_is_oneshot_and_requires_the_storage_box_mount():
    source = SERVICE.read_text(encoding="utf-8")

    assert "Type=oneshot" in source
    assert "ConditionPathIsMountPoint=/mnt/ed-storagebox" in source
    assert "ExecStart=/opt/ed-finder-v3-runtime/pgbackrest-operation.sh %i" in source
    assert "TimeoutStartSec=infinity" in source


def test_each_timer_targets_its_matching_operation():
    expected = {
        "full": ("Sun *-*-* 02:30:00 UTC", "edfinder-v3-pgbackrest@full.service"),
        "diff": ("Mon..Sat *-*-* 02:30:00 UTC", "edfinder-v3-pgbackrest@diff.service"),
        "verify": ("Sun *-*-* 12:00:00 UTC", "edfinder-v3-pgbackrest@verify.service"),
    }

    for name, path in TIMERS.items():
        source = path.read_text(encoding="utf-8")
        on_calendar, unit = expected[name]
        assert f"OnCalendar={on_calendar}" in source
        assert f"Unit={unit}" in source
        assert "WantedBy=timers.target" in source
