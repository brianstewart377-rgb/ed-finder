"""Read-only host storage routing and executable annotation contracts; no SSH calls."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

import pytest
import yaml


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
ACTION = ROOT / "scripts/operator/actions/v3-host-storage-detail.sh"
OPERATION = "v3-host-storage-detail"
PREFIX = "::notice title=Host storage detail::"
PGDATA = "/var/lib/docker/volumes/edfinder-v3-phase4c-full-20260827_r5-pgdata"


def _workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def _step(name: str) -> dict:
    return next(
        step
        for step in _workflow()["jobs"]["execute"]["steps"]
        if step.get("name") == name
    )


def test_operation_is_in_closed_choices_and_independent_request_allowlist(
    tmp_path: Path,
) -> None:
    inputs = _workflow()["on"]["workflow_dispatch"]["inputs"]["operation"]
    assert inputs["type"] == "choice"
    assert inputs["options"].count(OPERATION) == 1
    run = _step("Resolve request")["run"]
    assert f"{OPERATION}) ;;" in run
    output = tmp_path / "github-output"
    for operation, expected in ((OPERATION, 0), (OPERATION + "-cleanup", 64)):
        result = subprocess.run(
            ["bash", "-c", run],
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                "EVENT_NAME": "workflow_dispatch",
                "INPUT_OPERATION": operation,
                "GITHUB_OUTPUT": str(output),
            },
        )
        assert result.returncode == expected, result.stderr
    assert output.read_text() == f"operation={OPERATION}\n"


def test_host_storage_detail_preserves_pinned_ssh_elevation_and_receipt() -> None:
    assert _workflow()["concurrency"]["group"] == "chatgpt-ed-new-ops"
    step = _step("Inspect V3 host storage detail")
    assert step["if"] == f"steps.request.outputs.operation == '{OPERATION}'"
    assert int(step["timeout-minutes"]) <= 12
    assert (
        step["env"]["RECEIPT"]
        == "${{ runner.temp }}/v3-host-storage-detail-receipt.json"
    )
    run = step["run"]
    for expected in (
        "IdentitiesOnly=yes",
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=~/.ssh/known_hosts",
        '"\\$(id -u)\\" -eq 0',
        "exec sudo -n bash -s",
        "cd /opt/ed-finder",
        '< trusted-main/scripts/operator/actions/v3-host-storage-detail.sh > "$RECEIPT"',
        "|| status=$?",
        'exit "$status"',
    ):
        assert expected in run
    assert "ssh-keyscan" not in WORKFLOW.read_text()
    assert "| tee" not in run
    upload = _step("Upload V3 host storage detail receipt")
    assert (
        upload["if"] == f"always() && steps.request.outputs.operation == '{OPERATION}'"
    )
    assert upload["with"] == {
        "name": "v3-host-storage-detail-receipt",
        "path": "${{ runner.temp }}/v3-host-storage-detail-receipt.json",
        "if-no-files-found": "error",
        "retention-days": "30",
    }


def test_host_storage_detail_is_read_only_and_excludes_production_pgdata() -> None:
    source = ACTION.read_text()
    for forbidden in (r"\brm\b", r"\bprune\b", r"\brmi\b"):
        assert re.search(forbidden, source) is None
    assert '"$PYTHON_BIN" -I -S -B -c' in source
    assert f'PGDATA_PATH = "{PGDATA}"' in source
    assert (
        'command.extend("--exclude=" + x for x in sorted(excluded_paths()))' in source
    )
    assert 'command.extend(["--", path])' in source


def _annotations(tmp_path: Path, receipt: dict | None) -> list[str]:
    path = tmp_path / "receipt.json"
    if receipt is not None:
        path.write_text(json.dumps(receipt))
    step = _step("Annotate V3 host storage detail")
    assert step["if"] == f"always() && steps.request.outputs.operation == '{OPERATION}'"
    assert "python3 -I - <<'PYTHON'" in step["run"]
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "RECEIPT": str(path)},
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert 1 <= len(lines) <= 8
    assert all(line.startswith(PREFIX) and len(line) < 4000 for line in lines)
    return lines


def test_annotation_summary_executes_with_escaping_and_sorted_inventory(
    tmp_path: Path,
) -> None:
    lines = _annotations(
        tmp_path,
        {
            "status": "stopped",
            "read_only": True,
            "content_writes_performed": False,
            "directory_atime_metadata_writes_possible": True,
            "var_lib_scan_refused": "nested_mount",
            "failures": ["scan_failed"],
            "volumes": [
                {
                    "name": "small",
                    "size_bytes": 1024,
                    "measured": True,
                    "in_use": False,
                    "containers": [],
                },
                {
                    "name": "large%\r\n::error::injected",
                    "size_bytes": 1024**3,
                    "measured": True,
                    "in_use": True,
                    "containers": [{"name": "postgres", "state": "running"}],
                },
                {
                    "name": "production-pgdata",
                    "size_bytes": None,
                    "measured": False,
                    "reason": "postgres_data_volume_not_scanned",
                    "in_use": True,
                    "containers": [{"name": "app-postgres", "state": "running"}],
                },
            ],
            "images": [
                {
                    "repository_tag": "example:tag",
                    "id": "sha256:abcd",
                    "size_bytes": 2 * 1024**3,
                    "in_use": False,
                }
            ],
            "var_lib_top": [
                {"path": "/var/lib/small", "size_bytes": 1},
                {"path": "/var/lib/large", "size_bytes": 3 * 1024**3},
            ],
        },
    )
    assert len(lines) == 4
    joined = "\n".join(lines)
    for expected in (
        "status=stopped",
        "scan_failed",
        "content_writes_performed=False",
        "directory_atime_metadata_writes_possible=True",
        "var_lib_scan_refused=nested_mount",
        "large%25%0D%0A::error::injected",
        "measured=True",
        "production-pgdata: unknown; measured=False; reason=postgres_data_volume_not_scanned",
        "in_use=True; containers=postgres (running)",
        "example:tag [sha256:abcd]: 2.00 GiB",
        "in_use=False",
    ):
        assert expected in joined
    assert joined.index("large%25") < joined.index("small:")
    assert joined.index("/var/lib/large:") < joined.index("/var/lib/small:")
    assert "Docker system df" not in joined
    assert "\r" not in joined


def test_annotation_summary_is_bounded_and_discloses_omissions(tmp_path: Path) -> None:
    receipt = {
        "status": "ok",
        "failures": [],
        "read_only": True,
        "volumes": [
            {
                "name": f"volume-{index}-" + "%\r\n" * 200,
                "size_bytes": index,
                "in_use": False,
                "containers": [],
            }
            for index in range(100)
        ],
        "images": [
            {
                "repository_tag": f"image-{index}-" + "%\r\n" * 200,
                "size_bytes": index,
                "in_use": False,
            }
            for index in range(100)
        ],
        "var_lib_top": [
            {"path": "/var/lib/" + "%\r\n" * 200, "size_bytes": index}
            for index in range(40)
        ],
    }
    lines = _annotations(tmp_path, receipt)
    assert len(lines) == 7
    assert sum("[truncated:" in line for line in lines) == 3
    assert any("[field truncated]" in line for line in lines)


def test_annotation_summary_handles_unknown_container_references(
    tmp_path: Path,
) -> None:
    lines = _annotations(
        tmp_path,
        {
            "status": "stopped",
            "failures": ["containers:command_failed:docker:1"],
            "volumes": [
                {
                    "name": "unknown-volume",
                    "size_bytes": None,
                    "in_use": None,
                    "containers": None,
                }
            ],
        },
    )
    assert "containers:command_failed:docker:1" in lines[0]
    assert any(
        "unknown-volume: unknown; measured=unknown; reason=; in_use=None; containers="
        in line
        for line in lines
    )


def test_host_storage_detail_docs_disclose_scan_safety_and_atime_metadata() -> None:
    source = (
        ROOT / "docs/operations/v3-finder-production-rollout-state.md"
    ).read_text()
    section = source.split("## Host storage detail", 1)[1].split("\n## ", 1)[0]
    for expected in (
        "`content_writes_performed=false`",
        "`directory_atime_metadata_writes_possible`",
        "`directory_atime_guard.atime_updating_mounts`",
        "Scans run under the",
        "`rw,relatime`",
        "`size_bytes: null`",
        "`measured: false`",
        "`reason: postgres_data_volume_not_scanned`",
        "`docker image ls --format '{{json .}}'`",
        "`du -sx --block-size=1`",
        "`/proc/self/mountinfo`",
        "octal-unescapes",
        "bind source",
        "other read-only sections continue",
    ):
        assert expected in section
    assert "filesystem_writes_performed=false" not in section
    assert "directory_atime_writes_not_suppressed" not in section


@pytest.mark.parametrize(
    "receipt", (None, {"status": "stopped", "failures": ["host_identity_mismatch"]})
)
def test_annotation_summary_handles_absent_receipt_sections(
    tmp_path: Path, receipt: dict | None
) -> None:
    lines = _annotations(tmp_path, receipt)
    if receipt is None:
        assert len(lines) == 1
        assert "Receipt unavailable" in lines[0]
    else:
        assert "host_identity_mismatch" in lines[0]
        assert any("none or unavailable" in line for line in lines)
