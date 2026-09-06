"""The bootstrap must not execute an interpreter from the coding worker cache."""
from pathlib import Path
import shlex

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_privileged_bootstrap_uses_only_root_os_interpreter_in_isolated_mode():
    for file, name in (("v3-live-checkpoint-control.yml", "provision"),
                       ("v3-application-live-checkpoint-preflight.yml", "apply-local")):
        job = yaml.safe_load((ROOT / ".github/workflows" / file).read_text())["jobs"][name]
        step = next(step for step in job["steps"] if "run" in step)
        assert "/usr/bin/python3 -I -c" in step["run"]
        assert "pythonLocation" not in step["run"]
        assert "command -v python" not in step["run"]
        assert "/usr/bin/env -i" in step["run"]
    local = (ROOT / "scripts/operator/actions/v3-live-checkpoint-local.sh").read_text()
    assert "python3.14 -c" in local
    assert "sys.version_info[:2]==(3,14)" in local
    assert "runuser -u codex -- env -i" in local
    assert "systemctl restart" not in local
    assert "trap cleanup EXIT" in local
    assert local.index("logged_in=true") < local.index("docker login")
    assert "docker logout ghcr.io" in local


def test_checkpoint_workflow_yaml_has_no_duplicate_keys():
    class UniqueKeys(yaml.SafeLoader):
        pass
    def construct_mapping(loader, node, deep=False):
        keys = [loader.construct_object(key, deep=deep) for key, _ in node.value]
        assert len(keys) == len(set(keys)), f"Duplicate YAML key: {keys}"
        return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)
    UniqueKeys.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    for name in ("v3-live-checkpoint-control.yml", "v3-application-live-checkpoint-preflight.yml"):
        yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=UniqueKeys)


def test_bootstrap_preserves_script_execution_without_setuid_or_group_write(tmp_path):
    import runpy
    import tarfile
    helpers = runpy.run_path(str(ROOT / "tests/test_v3_checkpoint_local_transport.py"))
    module = helpers["load_module"]()
    member = tarfile.TarInfo("scripts/apply_migrations.sh")
    member.mode = 0o4777
    payload, digest = helpers["envelope"](member)
    module.unpack_bundle(payload, digest, tmp_path)
    assert (tmp_path / member.name).stat().st_mode & 0o7777 == 0o755


PREINSTALL_BOOTSTRAPS = {
    ("v3-live-checkpoint-control.yml", "provision"),
    ("v3-application-live-checkpoint-preflight.yml", "apply-local"),
}


def is_verified_checkpoint_preinstall_job(path: Path, job_name: str, job: dict) -> bool:
    """Only the two exact immutable OS bootstraps have a pre-install exception."""
    if (path.name, job_name) not in PREINSTALL_BOOTSTRAPS:
        return False
    assert job["runs-on"] == ["self-hosted", "Linux", "X64", "codex"]
    assert job["environment"] == "v3-live-checkpoint"
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert "github.repository == 'brianstewart377-rgb/ed-finder'" in job["if"]
    steps = job["steps"]
    assert all("checkout@" not in step.get("uses", "") and
               "setup-python@" not in step.get("uses", "") for step in steps)
    commands = [step for step in steps if "run" in step]
    assert len(commands) == 1
    step = commands[0]
    assert step["shell"] == "/bin/bash --noprofile --norc -p -e -o pipefail {0}"
    words = [word for word in shlex.split(step["run"], comments=True) if word.strip()]
    program = (ROOT / "scripts/operator/v3_checkpoint_bootstrap.py").read_text()
    assert words == [
        "set", "-euo", "pipefail", "printf", "%s", "$GH_TOKEN", "|",
        "/usr/bin/sudo", "-n", "/usr/bin/env", "-i",
        "PATH=/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "/usr/bin/python3", "-I",
        "-c", program, "$ARTIFACT_ID", "$BUNDLE_SHA", "$SOURCE_SHA", "$OPERATION",
        ">", "$RECEIPT",
    ]
    assert "needs." in step["env"]["BUNDLE_SHA"]
    assert "needs." in step["env"]["ARTIFACT_ID"]
    return True


@pytest.mark.parametrize("change", ["program", "extra-command", "inline-command", "setup", "shell", "ref"])
def test_preinstall_exception_rejects_broader_runtime_bypasses(change):
    path = ROOT / ".github/workflows/v3-live-checkpoint-control.yml"
    job = yaml.safe_load(path.read_text())["jobs"]["provision"]
    step = next(step for step in job["steps"] if "run" in step)
    if change == "program":
        step["run"] = step["run"].replace("import hashlib", "import os")
    elif change == "extra-command":
        job["steps"].append({"run": "python arbitrary.py"})
    elif change == "inline-command":
        step["run"] += "\npython arbitrary.py\n"
    elif change == "setup":
        job["steps"].append({"uses": "actions/setup-python@untrusted"})
    elif change == "shell":
        step["shell"] = "bash"
    else:
        job["if"] = "true"
    with pytest.raises(AssertionError):
        is_verified_checkpoint_preinstall_job(path, "provision", job)


def test_preinstall_exception_does_not_apply_to_other_jobs_or_workflows():
    assert not is_verified_checkpoint_preinstall_job(Path("ci.yml"), "provision", {})
    assert not is_verified_checkpoint_preinstall_job(
        Path("v3-live-checkpoint-control.yml"), "release", {}
    )
