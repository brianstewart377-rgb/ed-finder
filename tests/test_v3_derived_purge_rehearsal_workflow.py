"""The manual Contabo rehearsal has no credential or deployment boundary."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/v3-derived-purge-rehearsal.yml"


def workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def steps():
    return workflow()["jobs"]["rehearse"]["steps"]


def test_manual_scale_choices_and_self_hosted_concurrency():
    document = workflow()
    assert set(document["on"]) == {"workflow_dispatch"}
    inputs = document["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"scale"}
    assert inputs["scale"]["type"] == "choice"
    assert inputs["scale"]["default"] == "smoke"
    assert inputs["scale"]["options"] == ["smoke", "one_percent"]
    assert document["permissions"] == {"contents": "read"}
    assert document["concurrency"] == {
        "group": "v3-derived-purge-rehearsal", "cancel-in-progress": "false",
    }
    job = document["jobs"]["rehearse"]
    # Only the dedicated Docker-capable runner; never the Codex runners'
    # default self-hosted/Linux/X64 labels.
    assert job["runs-on"] == ["purge-rehearsal"]
    assert 0 < int(job["timeout-minutes"]) <= 720
    assert "services" not in job
    assert "environment" not in job


def test_job_env_uses_only_job_level_contexts():
    # GitHub rejects the whole dispatch when job-level env names a context
    # (runner, env, steps, job) that is only available inside steps.
    job_env = workflow()["jobs"]["rehearse"]["env"]
    assert "REHEARSAL_OUTPUT_DIR" not in job_env
    for value in job_env.values():
        for context in ("runner.", "env.", "steps.", "job."):
            assert "${{ " + context not in value


def test_first_step_preflights_before_checkout_and_checkout_pins_main_sha():
    job_steps = steps()
    first = job_steps[0]["run"]
    assert '>> "$GITHUB_ENV"' in first
    assert first.index('>> "$GITHUB_ENV"') < first.index('"$DISPATCH_REF" = refs/heads/main')
    assert '"$DISPATCH_REF" = refs/heads/main' in first
    assert "docker info" in first
    assert "docker context inspect" in first
    assert "docker ps -aq" in first
    assert "DockerRootDir" in first
    assert "df -PB1" in first
    checkout = job_steps[1]
    assert checkout["uses"] == "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] == "false"
    assert "git ls-remote --exit-code origin refs/heads/main" in job_steps[2]["run"]
    assert '"$current_main" = "$DISPATCH_SHA"' in job_steps[2]["run"]


def test_no_production_credentials_and_fixed_harness_arguments():
    text = WORKFLOW.read_text().lower()
    for forbidden in ("secrets.", "v3_production_", "ed_new_operator_", "ssh ", "sudo ", "nb79a3d", "ed-finder-prod"):
        assert forbidden not in text
    setup = next(step for step in steps() if "setup-python@" in step.get("uses", ""))
    assert setup["with"]["python-version"] == "3.14"
    execute = next(step for step in steps() if "--scale" in step.get("run", ""))
    assert 'scripts/rehearsal/v3_derived_purge_rehearsal.py' in execute["run"]
    assert '--run-id "$REHEARSAL_RUN_ID"' in execute["run"]
    assert '--output-dir "$REHEARSAL_OUTPUT_DIR"' in execute["run"]


def test_cleanup_always_scopes_run_and_verifies_absence_and_retains_artifacts():
    cleanup = next(step for step in steps() if step["name"].startswith("Remove own"))
    assert cleanup["if"] == "always()"
    assert cleanup["run"].count('--filter "$project_filter" --filter "$run_filter"') == 4
    assert "docker rm -f" in cleanup["run"]
    assert "docker volume rm" in cleanup["run"]
    assert cleanup["run"].count('[ -z "$(docker') == 2
    upload = steps()[-1]
    assert upload["if"] == "always() && env.REHEARSAL_OUTPUT_DIR != ''"
    assert upload["with"]["path"] == "${{ env.REHEARSAL_OUTPUT_DIR }}/"
    assert upload["uses"] == "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    assert upload["with"]["retention-days"] == "180"


def _shell_runner(tmp_path, *, free_bytes=50_000_000_000, existing="", endpoint="unix:///var/run/docker.sock", reachable=True):
    """Execute actual workflow shell against a disposable fake Docker daemon."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"containers": ["own"], "volumes": ["own-data"]}))
    docker = bin_dir / "docker"
    docker.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
state_path = Path(os.environ["STATE_PATH"])
state = json.loads(state_path.read_text())
if args == ["info"]:
    sys.exit(0 if os.environ["REACHABLE"] == "1" else 1)
elif args[:2] == ["context", "inspect"]:
    print(os.environ["ENDPOINT"])
elif args[:1] == ["info"]:
    print(os.environ["DOCKER_ROOT"])
elif args[:2] == ["ps", "-aq"]:
    if any("run-id=" in arg for arg in args):
        print("\\n".join(state["containers"]))
    else:
        print(os.environ["EXISTING"])
elif args[:3] == ["volume", "ls", "-q"]:
    print("\\n".join(state["volumes"]))
elif args[:2] == ["rm", "-f"]:
    state["containers"].remove(args[2])
elif args[:2] == ["volume", "rm"]:
    state["volumes"].remove(args[2])
else:
    raise SystemExit("Unexpected Docker command: " + repr(args))
state_path.write_text(json.dumps(state))
''')
    docker.chmod(0o755)
    df = bin_dir / "df"
    df.write_text('#!/bin/sh\nprintf "Filesystem 1B-blocks Used Available Use%% Mounted on\\nmock 100000000000 0 %s 0%% /\\n" "$FREE_BYTES"\n')
    df.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        "STATE_PATH": str(state), "DOCKER_ROOT": str(tmp_path),
        "FREE_BYTES": str(free_bytes), "EXISTING": existing, "ENDPOINT": endpoint,
        "REACHABLE": "1" if reachable else "0", "DISPATCH_REF": "refs/heads/main",
        "REHEARSAL_SCALE": "smoke", "REHEARSAL_RUN_ID": "123-1", "DOCKER_HOST": "",
        "RUNNER_TEMP": str(tmp_path), "GITHUB_ENV": str(tmp_path / "github_env"),
    }
    return env, state


@pytest.mark.parametrize(("scale", "free_bytes", "accepted"), [
    ("smoke", 4_999_999_999, False), ("smoke", 5_000_000_000, True),
    ("one_percent", 39_999_999_999, False), ("one_percent", 40_000_000_000, True),
    ("arbitrary", 100_000_000_000, False),
])
def test_disk_refusal_executes_real_preflight(tmp_path, scale, free_bytes, accepted):
    env, _ = _shell_runner(tmp_path, free_bytes=free_bytes)
    env["REHEARSAL_SCALE"] = scale
    result = subprocess.run(["bash", "-c", steps()[0]["run"]], env=env, capture_output=True, text=True)
    assert (result.returncode == 0) is accepted, result.stderr
    exported = (tmp_path / "github_env").read_text()
    assert exported == f"REHEARSAL_OUTPUT_DIR={tmp_path}/v3-purge-rehearsal-123-1\n"


@pytest.mark.parametrize("overrides", [
    {"REHEARSAL_RUN_ID": "../escape"}, {"REHEARSAL_RUN_ID": ""}, {"RUNNER_TEMP": ""},
])
def test_preflight_refuses_bad_run_id_or_missing_runner_temp(tmp_path, overrides):
    env, _ = _shell_runner(tmp_path)
    env.update(overrides)
    result = subprocess.run(["bash", "-c", steps()[0]["run"]], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert not (tmp_path / "github_env").exists()


@pytest.mark.parametrize("overrides", [
    {"existing": "other-rehearsal"}, {"reachable": False}, {"endpoint": "tcp://remote:2375"},
])
def test_runner_refuses_existing_container_unreachable_or_remote_docker(tmp_path, overrides):
    env, _ = _shell_runner(tmp_path, **overrides)
    result = subprocess.run(["bash", "-c", steps()[0]["run"]], env=env, capture_output=True, text=True)
    assert result.returncode != 0


def test_cleanup_deletes_owned_resources_then_checks_again(tmp_path):
    env, state = _shell_runner(tmp_path)
    cleanup = next(step for step in steps() if step["name"].startswith("Remove own"))
    result = subprocess.run(["bash", "-c", cleanup["run"]], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(state.read_text()) == {"containers": [], "volumes": []}
