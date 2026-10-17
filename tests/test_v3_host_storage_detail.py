"""Exercise the isolated collector with disposable command fixtures only."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/v3-host-storage-detail.sh"
PGDATA = "/var/lib/docker/volumes/edfinder-v3-phase4c-full-20260827_r5-pgdata"


def _code():
    words = shlex.split(ACTION.read_text().split("exec timeout", 1)[1])
    assert words[:2] == ["--signal=KILL", "600"]
    assert words[-4:-1] == ["-I", "-B", "-c"]
    return words[-1]


def _definitions():
    tree = ast.parse(_code())
    tree.body = [
        n
        for n in tree.body
        if isinstance(
            n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign)
        )
    ]
    namespace = {}
    exec(compile(tree, str(ACTION), "exec"), namespace)
    return namespace


STUB = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["CALLS"], "a") as log:
    log.write(json.dumps([name] + args) + "\\n")
mode = os.environ.get("FIXTURE_MODE", "")
pg = "edfinder-v3-phase4c-full-20260827_r5-pgdata"

def output(value):
    print(json.dumps(value))

def fields(*values):
    print("\\t".join(json.dumps(value) for value in values))

if name == "hostname":
    print("wrong-host" if mode == "wrong-host" else ("ed-finder-prod" if args == ["-s"] else "nb79a3d.mevnode.com"))
elif name == "pwd":
    print("/opt/ed-finder")
elif name == "df":
    print("1B-blocks Used Avail\\n2000000000000 1500000000000 500000000000")
elif name == "du":
    assert "--exclude=/var/lib/docker/volumes/" + pg in args
    assert not args[-1].startswith("/var/lib/docker/volumes/" + pg)
    if mode == "du-failure" or (mode == "volume-du-failure" and args[-1].endswith("unused/_data")):
        raise SystemExit(1)
    if args[-1] == "/var/lib":
        for size, path in ((64400000000, "/var/lib"), (40000000000, "/var/lib/docker"), (24000000000, "/var/lib/backup\\nname")):
            sys.stdout.write(str(size) + "\\t" + path + "\\0")
    else:
        sys.stdout.write("1234\\t" + args[-1] + "\\0")
elif name == "docker":
    assert args[:2] == ["--host", "unix:///var/run/docker.sock"]
    args = args[2:]
    if args[:2] == ["container", "ls"]:
        if mode == "containers-failure":
            raise SystemExit(1)
        print("running-id\\nstopped-id")
    elif args[:2] == ["container", "inspect"]:
        if args[-1] == "running-id":
            mounts = [{"Type": "volume", "Name": pg}]
            if mode == "extra-running-postgres":
                mounts.append({"Type": "volume", "Name": "extra-postgres-data"})
            fields("/production-postgres", "sha256:used", "postgres:18", "2026-08-27T00:00:00Z", "running", True, mounts)
        else:
            container = "/rehearsal-postgres" if mode == "extra-stopped-postgres" else "/rehearsal"
            fields(container, "sha256:old", "rehearsal:august", "2026-08-02T00:00:00Z", "exited", False, [{"Type": "volume", "Name": "old-rehearsal"}])
    elif args[:2] == ["volume", "ls"]:
        print(pg + "\\nold-rehearsal\\nunused")
        if mode == "extra-running-postgres":
            print("extra-postgres-data")
        if mode == "pgdata-alias":
            print("pgdata-alias")
    elif args[:2] == ["volume", "inspect"]:
        volume = args[-1]
        mountpoint = "/var/lib/docker/volumes/" + volume + "/_data"
        if mode == "relocated-pgdata" and volume == pg:
            mountpoint = "/var/lib/other-pgdata"
        if mode == "external-volume" and volume == "unused":
            mountpoint = "/srv/volume"
        if volume == "pgdata-alias":
            mountpoint = "/var/lib/docker/volumes/" + pg + "/_data"
        fields(volume, {"com.docker.compose.project": "rehearsal", "backup.token": "SECRET-LABEL-VALUE"}, mountpoint)
    elif args[:2] == ["image", "ls"]:
        for tag, image_id, size in (("postgres", "used", "1GB"), ("rehearsal", "old", "2GB"), ("unused", "unused", "5GB")):
            output({"Repository": tag, "Tag": "18", "ID": "sha256:" + image_id, "Size": size, "CreatedAt": "2026-08-02 00:00:00 +0000 UTC"})
    else:
        raise AssertionError(args)
else:
    raise AssertionError(name)
"""


def _run(
    tmp_path, mode="", options="rw,noatime", nested_options=None, mountinfo_extra=""
):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "fixture"
    stub.write_text(STUB)
    stub.chmod(0o755)
    for name in ("hostname", "pwd", "df", "docker", "du"):
        (bindir / name).symlink_to(stub)
    mounts = tmp_path / "mountinfo"
    mounts.write_text(
        "1 0 8:1 / / "
        + options
        + " - ext4 /dev/test rw\n"
        + (
            "2 1 8:2 / " + PGDATA + " " + nested_options + " - ext4 /dev/pg rw\n"
            if nested_options
            else ""
        )
        + mountinfo_extra
    )
    script = tmp_path / "action.sh"
    script.write_text(
        ACTION.read_text().replace('"/proc/self/mountinfo"', json.dumps(str(mounts)))
    )
    calls = tmp_path / "calls.jsonl"
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        timeout=15,
        env={
            **os.environ,
            "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
            "CALLS": str(calls),
            "FIXTURE_MODE": mode,
        },
    )
    assert result.stderr == "", result.stderr
    assert len(result.stdout.splitlines()) == 1
    return (
        result.returncode,
        json.loads(result.stdout),
        [json.loads(line) for line in calls.read_text().splitlines()],
    )


def test_collector_reports_storage_and_stopped_references_without_scanning_pgdata(
    tmp_path,
):
    status, receipt, calls = _run(tmp_path)
    assert status == 0
    assert receipt["status"] == "success"
    assert receipt["failures"] == []
    assert receipt["read_only"] is True
    assert receipt["db_writes_performed"] is False
    assert "filesystem_writes_performed" not in receipt
    assert receipt["content_writes_performed"] is False
    assert receipt["direct_db_access_performed"] is False
    assert receipt["root_filesystem_before"] == receipt["root_filesystem_after"]
    assert "docker_system_df" not in receipt
    assert receipt["directory_atime_metadata_writes_possible"] is False
    assert receipt["directory_atime_guard"]["atime_updating_mounts"] == []
    volumes = {v["name"]: v for v in receipt["volumes"]}
    postgres = volumes[PGDATA.rsplit("/", 1)[-1]]
    assert postgres["size_bytes"] is None
    assert postgres["measured"] is False
    assert postgres["reason"] == "postgres_data_volume_not_scanned"
    for name in ("old-rehearsal", "unused"):
        assert volumes[name]["size_bytes"] == 1234
        assert volumes[name]["measured"] is True
        assert volumes[name]["size_source"] == "du_allocated_bytes"
    assert volumes["old-rehearsal"]["in_use"] is True
    assert volumes["old-rehearsal"]["containers"] == [
        {"name": "rehearsal", "state": "exited"}
    ]
    assert volumes["unused"]["in_use"] is False
    assert volumes["unused"]["labels"] == {"com.docker.compose.project": "rehearsal"}
    assert volumes["unused"]["other_label_count"] == 1
    assert "SECRET-LABEL-VALUE" not in json.dumps(receipt)
    assert "backup.token" not in json.dumps(receipt)
    images = {i["id"]: i for i in receipt["images"]}
    assert images["sha256:old"]["in_use"] is True
    assert images["sha256:unused"]["in_use"] is False
    assert receipt["stopped_containers"][0]["name"] == "rehearsal"
    assert receipt["var_lib_top"][0]["size_bytes"] == 64_400_000_000
    assert receipt["var_lib_top"][2]["path"] == "/var/lib/backup\nname"
    for command in calls:
        if command[0] == "du":
            assert "--exclude=" + PGDATA in command
            assert command[-1] != PGDATA
        assert "exec" not in command
        assert not (command[0] == "docker" and command[3:5] == ["system", "df"])
    scans = [c for c in calls if c[0] == "du"]
    volume_scans = [c for c in scans if "/volumes/" in c[-1]]
    assert {c[-1] for c in volume_scans} == {
        "/var/lib/docker/volumes/" + name + "/_data"
        for name in ("old-rehearsal", "unused")
    }
    assert all("-sx" in c and "--block-size=1" in c for c in volume_scans)
    # No full inspect dumps: container environments and commands never reach Python.
    for command in calls:
        if "inspect" in command:
            assert "--format" in command
            assert ".Config.Env" not in command


@pytest.mark.parametrize(
    "mode, failure",
    [
        ("du-failure", "var_lib_top:command_failed:du:1"),
        ("containers-failure", "containers:command_failed:docker:1"),
        ("volume-du-failure", "volume_size:unused:command_failed:du:1"),
    ],
)
def test_collector_marks_partial_inventory_stopped(tmp_path, mode, failure):
    status, receipt, calls = _run(tmp_path, mode)
    assert status == 1
    assert receipt["status"] == "stopped"
    assert failure in receipt["failures"]
    assert "root_filesystem_after" in receipt
    if mode == "containers-failure":
        assert all(
            v["in_use"] is None and v["containers"] is None for v in receipt["volumes"]
        )
        assert all(i["in_use"] is None for i in receipt["images"])
        assert all(not v["measured"] for v in receipt["volumes"])
        # Unclassified volumes may belong to another PostgreSQL container:
        # every /var/lib du must exclude them as well as PGDATA.
        var_lib_du = [c for c in calls if c[0] == "du" and c[-1].startswith("/var/lib")]
        assert var_lib_du
        for volume in receipt["volumes"]:
            assert all("--exclude=" + volume["mountpoint"] in c for c in var_lib_du)
    if mode == "volume-du-failure":
        volume = next(v for v in receipt["volumes"] if v["name"] == "unused")
        assert volume["size_bytes"] is None
        assert volume["measured"] is False
        assert volume["reason"] == "command_failed:du:1"
        assert "var_lib_top" in receipt


def test_wrong_host_stops_before_storage_commands(tmp_path):
    status, receipt, calls = _run(tmp_path, "wrong-host")
    assert status == 1
    assert "unexpected_host_identity" in receipt["failures"]
    assert {c[0] for c in calls} == {"hostname"}


@pytest.mark.parametrize("options", ["rw,relatime", "rw,strictatime", "rw"])
def test_discloses_directory_atime_updates_instead_of_refusing(tmp_path, options):
    # Production's root is relatime; refusing would make the action unusable.
    status, receipt, calls = _run(tmp_path, options=options)
    assert "directory_atime_writes_not_suppressed" not in receipt["failures"]
    assert status == 0
    assert any(c[0] == "du" for c in calls)
    assert receipt["directory_atime_metadata_writes_possible"] is True
    assert receipt["directory_atime_writes_suppressed"] is False
    assert receipt["directory_atime_guard"]["atime_updating_mounts"]
    assert "filesystem_writes_performed" not in receipt
    assert receipt["content_writes_performed"] is False
    assert "root_filesystem_after" in receipt


def test_targets_match_current_production_authority_and_no_shell_spool():
    ns = _definitions()
    authority = json.loads(
        (ROOT / "deploy/v3-production/target-authority.json").read_text()
    )
    assert ns["EXPECTED_HOST"] == authority["target"]["hostname"]
    assert ns["EXPECTED_FQDN"] == authority["target"]["fqdn"]
    assert ns["ACTION_BUDGET_SECONDS"] < 600
    assert "<<" not in ACTION.read_text()
    assert "\x27" not in _code()
    subprocess.run(["bash", "-n", str(ACTION)], check=True)


def test_optional_directory_presence_and_total_exclusion(tmp_path):
    ns = _definitions()
    assert ns["optional_directory"](str(tmp_path / "missing"))["present"] is False
    calls = []

    def fake_run(command):
        calls.append(command)
        return "1234\t" + str(tmp_path) + "\0"

    ns["run"] = fake_run
    assert ns["optional_directory"](str(tmp_path))["size_bytes"] == 1234
    assert "-sx" in calls[0]
    assert "--exclude=" + PGDATA in calls[0]
    link = tmp_path / "link"
    link.symlink_to(tmp_path)
    with pytest.raises(RuntimeError, match="optional_path_not_directory"):
        ns["optional_directory"](str(link))


def test_shared_deadline_refuses_new_work_and_reserves_closing_df():
    ns = _definitions()
    ns["DEADLINE"] = ns["time"].monotonic() + 10
    with pytest.raises(RuntimeError, match="action_budget_exhausted"):
        ns["run"](["must-not-execute"])


def test_command_output_cap_fails_closed_and_kills_child():
    ns = _definitions()
    ns["MAX_OUTPUT_BYTES"] = 10
    with pytest.raises(RuntimeError, match="command_output_limit"):
        ns["run"]([sys.executable, "-I", "-B", "-c", "print('x' * 100)"])


def test_top_entries_are_sorted_capped_and_disclose_omissions():
    ns = _definitions()
    ns["du"] = lambda path: [
        {"path": f"/var/lib/{n}", "size_bytes": n} for n in range(50, 0, -1)
    ]
    rows = ns["var_lib"]()
    assert len(rows) == 40
    assert rows[0]["size_bytes"] == 50
    assert ns["receipt"]["var_lib_entries_omitted"] == 10


def test_command_timeout_kills_scan_without_spending_closing_reserve():
    ns = _definitions()
    ns["DEADLINE"] = ns["time"].monotonic() + 12.2
    with pytest.raises(RuntimeError, match="command_timeout"):
        ns["run"]([sys.executable, "-I", "-B", "-c", "import time; time.sleep(10)"])
    # The same deadline still permits the closing observation.
    assert (
        ns["run"]([sys.executable, "-I", "-B", "-c", "print(1)"], closing=True) == "1\n"
    )


def test_unexpected_pgdata_mountpoint_stops_before_any_du(tmp_path):
    status, receipt, calls = _run(tmp_path, "relocated-pgdata")
    assert status == 1
    assert "pgdata_exclusion_mountpoint_unverified" in receipt["failures"]
    assert "images" in receipt
    assert not any(command[0] == "du" for command in calls)


@pytest.mark.parametrize("options", ["rw,noatime", "rw,nodiratime", "ro,relatime"])
def test_suppressed_directory_atime_and_excluded_pgdata_mount(tmp_path, options):
    status, receipt, calls = _run(
        tmp_path, options=options, nested_options="rw,relatime"
    )
    assert status == 0
    assert any(c[0] == "du" for c in calls)
    assert receipt["content_writes_performed"] is False
    assert receipt["directory_atime_metadata_writes_possible"] is False
    assert receipt["directory_atime_guard"] == {
        "checked_mounts": ["/"],
        "atime_updating_mounts": [],
    }


@pytest.mark.parametrize(
    "device,root,point,decoded_point",
    [
        ("8:1", "/", "/var/lib/alias", "/var/lib/alias"),
        ("8:1", "/var/lib/docker", "/mnt/bind", "/mnt/bind"),
        ("8:1", "/var/lib", "/mnt/bind", "/mnt/bind"),
        ("8:1", r"/var/lib/with\040space", r"/mnt/bind\011tab", "/mnt/bind\ttab"),
        (
            "8:1",
            "/",
            r"/var/lib/with\134slash\012newline",
            "/var/lib/with\\slash\nnewline",
        ),
    ],
)
def test_nested_or_bind_mount_refuses_all_var_lib_du_but_keeps_inventory(
    tmp_path, device, root, point, decoded_point
):
    status, receipt, calls = _run(
        tmp_path,
        mountinfo_extra=f"3 1 {device} {root} {point} rw,noatime - ext4 /dev/test rw\n",
    )
    assert status == 1
    assert receipt["var_lib_scan_refused"] == "nested_mount"
    assert receipt["var_lib_scan_offending_mount_points"] == [decoded_point]
    assert "var_lib_top:nested_mount" in receipt["failures"]
    assert not any(c[0] == "du" for c in calls)
    assert "images" in receipt and "volumes" in receipt
    assert receipt["root_filesystem_after"] == receipt["root_filesystem_before"]
    assert receipt["directory_atime_metadata_writes_possible"] is False


@pytest.mark.parametrize(
    "entry",
    [
        "3 1 8:2 /var/lib/docker /mnt/other rw,relatime - ext4 /dev/other rw\n",
        "3 1 8:1 /var/library /mnt/other rw,relatime - ext4 /dev/test rw\n",
        "3 1 8:1 / /var/library rw,relatime - ext4 /dev/test rw\n",
        # Other-device mounts that du -x skips: a running container overlay,
        # its shm tmpfs, and a separate disk mounted under /var/lib.
        "3 1 0:51 / /var/lib/docker/overlay2/abc/merged rw,relatime"
        " - overlay overlay rw\n",
        "3 1 0:52 / /var/lib/docker/containers/abc/mounts/shm rw,relatime"
        " - tmpfs shm rw\n",
        "3 1 8:2 / /var/lib/external rw,relatime - ext4 /dev/other rw\n",
    ],
)
def test_unrelated_mounts_do_not_refuse_or_taint_atime_claims(tmp_path, entry):
    status, receipt, calls = _run(tmp_path, mountinfo_extra=entry)
    assert status == 0
    assert "var_lib_scan_refused" not in receipt
    assert receipt["directory_atime_metadata_writes_possible"] is False
    assert any(c[0] == "du" for c in calls)


def test_stacked_root_uses_visible_mount_atime_policy(tmp_path):
    status, receipt, _ = _run(
        tmp_path,
        mountinfo_extra="3 1 8:1 / / rw,relatime - ext4 /dev/test rw\n",
    )
    assert status == 0
    assert receipt["directory_atime_metadata_writes_possible"] is True
    assert receipt["directory_atime_guard"]["atime_updating_mounts"] == ["/"]


def test_mountinfo_guard_rechecks_before_each_du_including_optional_totals(tmp_path):
    ns = _definitions()
    mountinfo = tmp_path / "mountinfo"
    initial = "1 0 8:1 / / rw,noatime - ext4 /dev/test rw\n"
    mountinfo.write_text(initial)
    ns["MOUNTINFO_PATH"] = str(mountinfo)
    calls = []

    def fake_run(command):
        calls.append(command)
        mountinfo.write_text(
            initial + "3 1 8:1 /var/lib/source /mnt/bind rw - ext4 /dev/test rw\n"
        )
        return "1234\t" + command[-1] + "\0"

    ns["run"] = fake_run
    ns["du"]("/var/lib/docker/volumes/safe/_data", total=True)
    # The new mount is visible before both another volume and an optional total.
    with pytest.raises(RuntimeError, match="nested_mount"):
        ns["du"]("/var/lib/ed-finder", total=True)
    assert len(calls) == 1
    assert ns["receipt"]["var_lib_scan_refused"] == "nested_mount"


@pytest.mark.parametrize(
    "mountinfo", ["invalid\n", "2 1 8:2 / /mnt rw - ext4 /dev/test rw\n"]
)
def test_invalid_mountinfo_fails_closed_before_du(tmp_path, mountinfo):
    ns = _definitions()
    path = tmp_path / "mountinfo"
    path.write_text(mountinfo)
    ns["MOUNTINFO_PATH"] = str(path)
    ns["run"] = lambda argv: pytest.fail("No du on unresolved mount table")
    with pytest.raises(RuntimeError, match="mountinfo_invalid|root_mount_unresolved"):
        ns["du"]("/var/lib")


@pytest.mark.parametrize(
    "mode,protected",
    [
        ("extra-running-postgres", "extra-postgres-data"),
        ("extra-stopped-postgres", "old-rehearsal"),
        ("pgdata-alias", "pgdata-alias"),
    ],
)
def test_all_postgres_volume_references_and_pgdata_aliases_are_unmeasured(
    tmp_path, mode, protected
):
    status, receipt, calls = _run(tmp_path, mode)
    assert status == 0
    volume = next(v for v in receipt["volumes"] if v["name"] == protected)
    assert volume["size_bytes"] is None
    assert volume["measured"] is False
    assert volume["reason"] == "postgres_data_volume_not_scanned"
    for command in calls:
        assert not (command[0] == "docker" and command[3:5] == ["system", "df"])
        if command[0] == "du":
            assert command[-1] != volume["mountpoint"]
            assert "--exclude=" + volume["mountpoint"] in command


def test_nested_mount_refusal_preserves_volume_scans_outside_var_lib(tmp_path):
    status, receipt, calls = _run(
        tmp_path,
        "external-volume",
        mountinfo_extra=(
            "3 1 8:1 / /var/lib/nested rw,noatime - ext4 /dev/test rw\n"
            "4 1 8:2 / /srv rw,relatime - ext4 /dev/other rw\n"
        ),
    )
    assert status == 1
    assert receipt["var_lib_scan_refused"] == "nested_mount"
    assert [c[-1] for c in calls if c[0] == "du"] == ["/srv/volume"]
    assert receipt["directory_atime_metadata_writes_possible"] is True
    assert receipt["directory_atime_guard"]["atime_updating_mounts"] == ["/srv"]
    volume = next(v for v in receipt["volumes"] if v["name"] == "unused")
    assert volume["measured"] is True
    assert "root_filesystem_after" in receipt


@pytest.mark.parametrize(
    "extra,offending,refused",
    [
        # /var/lib is its own filesystem: mount roots are relative to it.
        ("4 1 8:3 /docker /mnt/bind rw,noatime - ext4 /dev/vl rw\n", "/mnt/bind", True),
        (
            "4 1 8:3 / /var/lib/alias rw,noatime - ext4 /dev/vl rw\n",
            "/var/lib/alias",
            True,
        ),
        # Same relative root on the ROOT device is a different directory.
        ("4 1 8:1 /docker /mnt/bind rw,noatime - ext4 /dev/test rw\n", None, False),
    ],
)
def test_separate_var_lib_filesystem_resolves_bind_sources_relative_to_it(
    tmp_path, extra, offending, refused
):
    status, receipt, calls = _run(
        tmp_path,
        mountinfo_extra="3 1 8:3 / /var/lib rw,noatime - ext4 /dev/vl rw\n" + extra,
    )
    if refused:
        assert receipt["var_lib_scan_refused"] == "nested_mount"
        assert receipt["var_lib_scan_offending_mount_points"] == [offending]
        assert not any(c[0] == "du" and c[-1].startswith("/var/lib") for c in calls)
    else:
        assert status == 0
        assert "var_lib_scan_refused" not in receipt
