"""The bootstrap must not execute an interpreter from the coding worker cache."""
from pathlib import Path
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
