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
    if mode == "du-failure":
        raise SystemExit(1)
    if args[-1] == "/var/lib":
        for size, path in ((64400000000, "/var/lib"), (40000000000, "/var/lib/docker"), (24000000000, "/var/lib/backup\\nname")):
            sys.stdout.write(str(size) + "\\t" + path + "\\0")
    else:
        sys.stdout.write("1234\\t" + args[-1] + "\\0")
elif name == "docker":
    assert args[:2] == ["--host", "unix:///var/run/docker.sock"]
    args = args[2:]
    if args[:2] == ["system", "df"]:
        if "-v" in args:
            output({"Volumes": [{"Name": pg, "Size": "1.346TB"}, {"Name": "old-rehearsal", "Size": "7GB"}, {"Name": "unused", "Size": "N/A" if mode == "unknown-size" else "3GB"}]})
        else:
            for kind in ("Images", "Containers", "Local Volumes", "Build Cache"):
                output({"Type": kind, "TotalCount": "3", "Active": "1", "Size": "20GB", "Reclaimable": "10GB (50%)"})
    elif args[:2] == ["container", "ls"]:
        if mode == "containers-failure":
            raise SystemExit(1)
        print("running-id\\nstopped-id")
    elif args[:2] == ["container", "inspect"]:
        if args[-1] == "running-id":
            fields("/production", "sha256:used", "postgres:18", "2026-08-27T00:00:00Z", "running", True, [{"Type": "volume", "Name": pg}])
        else:
            fields("/rehearsal", "sha256:old", "rehearsal:august", "2026-08-02T00:00:00Z", "exited", False, [{"Type": "volume", "Name": "old-rehearsal"}])
    elif args[:2] == ["volume", "ls"]:
        print(pg + "\\nold-rehearsal\\nunused")
    elif args[:2] == ["volume", "inspect"]:
        volume = args[-1]
        mountpoint = "/var/lib/docker/volumes/" + volume + "/_data"
        if mode == "relocated-pgdata" and volume == pg:
            mountpoint = "/var/lib/other-pgdata"
        fields(volume, {"com.docker.compose.project": "rehearsal"}, mountpoint)
    elif args[:2] == ["image", "ls"]:
        for tag, image_id, size in (("postgres", "used", "1GB"), ("rehearsal", "old", "2GB"), ("unused", "unused", "5GB")):
            output({"Repository": tag, "Tag": "18", "ID": "sha256:" + image_id, "Size": size, "CreatedAt": "2026-08-02 00:00:00 +0000 UTC"})
    else:
        raise AssertionError(args)
else:
    raise AssertionError(name)
"""


def _run(tmp_path, mode="", options="rw,noatime", nested_options=None):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "fixture"
    stub.write_text(STUB)
    stub.chmod(0o755)
    for name in ("hostname", "pwd", "df", "docker", "du"):
        (bindir / name).symlink_to(stub)
    mounts = tmp_path / "mounts"
    mounts.write_text(
        "/dev/test / ext4 "
        + options
        + " 0 0\n"
        + (
            "/dev/pg " + PGDATA + " ext4 " + nested_options + " 0 0\n"
            if nested_options
            else ""
        )
    )
    script = tmp_path / "action.sh"
    script.write_text(
        ACTION.read_text().replace('"/proc/self/mounts"', json.dumps(str(mounts)))
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
    assert receipt["filesystem_writes_performed"] is False
    assert receipt["direct_db_access_performed"] is False
    assert receipt["root_filesystem_before"] == receipt["root_filesystem_after"]
    assert len(receipt["docker_system_df"]) == 4
    assert receipt["docker_system_df"][0]["reclaimable_bytes"] == 10_000_000_000
    volumes = {v["name"]: v for v in receipt["volumes"]}
    assert volumes[PGDATA.rsplit("/", 1)[-1]]["size_bytes"] == 1_346_000_000_000
    assert volumes["old-rehearsal"]["in_use"] is True
    assert volumes["old-rehearsal"]["containers"] == [
        {"name": "rehearsal", "state": "exited"}
    ]
    assert volumes["unused"]["in_use"] is False
    assert volumes["unused"]["labels"] == {"com.docker.compose.project": "rehearsal"}
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
        ("unknown-size", "volume_size_unavailable:unused"),
    ],
)
def test_collector_marks_partial_inventory_stopped(tmp_path, mode, failure):
    status, receipt, _ = _run(tmp_path, mode)
    assert status == 1
    assert receipt["status"] == "stopped"
    assert failure in receipt["failures"]
    assert "root_filesystem_after" in receipt
    if mode == "containers-failure":
        assert all(
            v["in_use"] is None and v["containers"] is None for v in receipt["volumes"]
        )
        assert all(i["in_use"] is None for i in receipt["images"])
    if mode == "unknown-size":
        assert receipt["volumes"][-1]["size_bytes"] is None


def test_wrong_host_stops_before_storage_commands(tmp_path):
    status, receipt, calls = _run(tmp_path, "wrong-host")
    assert status == 1
    assert "unexpected_host_identity" in receipt["failures"]
    assert {c[0] for c in calls} == {"hostname"}


@pytest.mark.parametrize(
    "options,nested", [("rw,relatime", None), ("rw,noatime", "rw,relatime")]
)
def test_discloses_directory_atime_updates_instead_of_refusing(
    tmp_path, options, nested
):
    # Production's root is relatime; refusing would make the action unusable.
    status, receipt, calls = _run(tmp_path, options=options, nested_options=nested)
    assert "directory_atime_writes_not_suppressed" not in receipt["failures"]
    assert receipt["directory_atime_writes_suppressed"] is False
    assert receipt["directory_atime_guard"]["atime_updating_mounts"]
    assert receipt["filesystem_writes_performed"] is False
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
