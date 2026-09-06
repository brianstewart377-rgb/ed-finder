"""Exact contracts for the OS-only bootstrap and its direct process launch."""
import base64
from pathlib import Path
import re
import shlex
import zlib

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/operator/v3_checkpoint_bootstrap.py"
GUARD = "github.ref == 'refs/heads/main' && github.repository == 'brianstewart377-rgb/ed-finder'"
PREINSTALL_BOOTSTRAPS = {
    ("v3-live-checkpoint-control.yml", "provision"): (
        "prepare-provision", "provision", GUARD, "v3-live-checkpoint-authority-candidate"
    ),
    ("v3-application-live-checkpoint-preflight.yml", "apply-local"): (
        "deploy", "deploy", "inputs.transport != 'ssh' && " + GUARD,
        "v3-live-checkpoint-deployment-receipt"
    ),
}


def shell_words(shell):
    """Substitute trusted expression fixtures before modelling runner argv."""
    values = {
        "github.sha": "a" * 40, "runner.temp": "/tmp/runner-temp",
        "github.run_id": "42", "github.run_attempt": "1",
    }
    for parent in ("prepare-provision", "deploy"):
        values[f"needs.{parent}.outputs.artifact_id"] = "123"
        values[f"needs.{parent}.outputs.bundle_sha256"] = "b" * 64
    for expression, value in values.items():
        shell = shell.replace("${{ " + expression + " }}", value)
    assert "${{" not in shell
    return shlex.split(shell)


def decoded_program(command):
    match = re.fullmatch(
        r"import base64,zlib;exec\(zlib\.decompress\(base64\.b64decode\('([A-Za-z0-9+/=]+)'\)\)\)",
        command,
    )
    assert match, "Unexpected bootstrap decoder command"
    return zlib.decompress(base64.b64decode(match[1], validate=True))


def is_verified_checkpoint_preinstall_job(path: Path, job_name: str, job: dict) -> bool:
    """The exception applies only after the whole job and command are verified."""
    specification = PREINSTALL_BOOTSTRAPS.get((path.name, job_name))
    if specification is None:
        return False
    parent, operation, guard, receipt = specification
    assert job["if"] == guard
    assert job["needs"] == parent
    assert job["runs-on"] == ["self-hosted", "Linux", "X64", "codex"]
    assert job["environment"] == "v3-live-checkpoint"
    steps = job["steps"]
    assert len(steps) == 2
    assert all("checkout@" not in step.get("uses", "") and
               "setup-python@" not in step.get("uses", "") for step in steps)
    commands = [step for step in steps if "run" in step]
    assert len(commands) == 1
    step = commands[0]
    assert step["run"] == "ignored-by-immutable-bootstrap"
    assert step["working-directory"] == "/"
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "if" not in step and "continue-on-error" not in step
    assert "shell" not in step
    assert set(job["defaults"]) == {"run"}
    assert set(job["defaults"]["run"]) == {"shell"}
    shell = job["defaults"]["run"]["shell"]
    assert "runner." not in shell
    expected_path = ("/tmp/" + receipt
                     + "-${{ github.run_id }}-${{ github.run_attempt }}.json")
    expected_suffix = (
        "${{ needs." + parent + ".outputs.artifact_id }} "
        + "${{ needs." + parent + ".outputs.bundle_sha256 }} "
        + '${{ github.sha }} ' + operation + ' "' + expected_path + '" {0}'
    )
    assert shell.endswith(expected_suffix)
    words = shell_words(shell)
    assert words[:7] == [
        "/usr/bin/sudo", "-n", "--preserve-env=GH_TOKEN", "/usr/bin/python3", "-I", "-S", "-c",
    ]
    assert decoded_program(words[7]) == SOURCE.read_bytes()
    assert words[8:] == ["123", "b" * 64, "a" * 40, operation,
                         f"/tmp/{receipt}-42-1.json", "{0}"]
    upload = steps[1]
    assert upload["uses"] == "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    assert upload["with"]["name"] == receipt
    assert upload["with"]["path"] == expected_path
    return True


def test_privileged_bootstrap_uses_only_root_os_interpreter_in_isolated_mode():
    for file, name in PREINSTALL_BOOTSTRAPS:
        path = ROOT / ".github/workflows" / file
        job = yaml.safe_load(path.read_text())["jobs"][name]
        assert is_verified_checkpoint_preinstall_job(path, name, job)
    local = (ROOT / "scripts/operator/actions/v3-live-checkpoint-local.sh").read_text()
    assert "python3.14 -I -S -c" in local
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
    for name, _ in PREINSTALL_BOOTSTRAPS:
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


@pytest.mark.parametrize("file,name", list(PREINSTALL_BOOTSTRAPS))
@pytest.mark.parametrize("change", [
    "program", "extra-command", "inline-command", "setup", "shell", "ref",
    "or-true", "or-false", "negated", "repository-bypass", "needs", "artifact", "env", "cwd",
])
def test_preinstall_exception_rejects_broader_runtime_bypasses(file, name, change):
    path = ROOT / ".github/workflows" / file
    job = yaml.safe_load(path.read_text())["jobs"][name]
    step = job["steps"][0]
    if change == "program":
        job["defaults"]["run"]["shell"] = job["defaults"]["run"]["shell"].replace("import base64,zlib;", "import os;")
    elif change == "extra-command":
        job["steps"].append({"run": "python arbitrary.py"})
    elif change == "inline-command":
        step["run"] += "\npython arbitrary.py\n"
    elif change == "setup":
        job["steps"].append({"uses": "actions/setup-python@untrusted"})
    elif change == "shell":
        step["shell"] = "bash"
    elif change == "ref":
        job["if"] = "true"
    elif change.startswith("or-"):
        job["if"] += " || " + change.removeprefix("or-")
    elif change == "negated":
        job["if"] = "!(" + job["if"] + ")"
    elif change == "repository-bypass":
        job["if"] = job["if"].replace(" && github.repository", " || github.repository")
    elif change == "needs":
        job["needs"] = "untrusted"
    elif change == "artifact":
        job["defaults"]["run"]["shell"] = job["defaults"]["run"]["shell"].replace("outputs.artifact_id", "outputs.untrusted_id")
    elif change == "env":
        step["env"]["PYTHONPATH"] = "/home/codex/poison"
    else:
        step["working-directory"] = "${{ github.workspace }}"
    with pytest.raises(AssertionError):
        is_verified_checkpoint_preinstall_job(path, name, job)


def test_preinstall_exception_does_not_apply_to_other_jobs_or_workflows():
    assert not is_verified_checkpoint_preinstall_job(Path("ci.yml"), "provision", {})
    assert not is_verified_checkpoint_preinstall_job(Path("v3-live-checkpoint-control.yml"), "release", {})
