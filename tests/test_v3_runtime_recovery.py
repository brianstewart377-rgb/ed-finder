from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

from scripts.operator import recover_v3_runtime_contract as recovery


def _labels(root: Path, configs: str = "compose.yml") -> str:
    return json.dumps(
        {
            recovery.COMPOSE_PROJECT_LABEL: "edfinder-v3-phase4c-full-20260827_r5",
            recovery.COMPOSE_WORKING_DIR_LABEL: str(root),
            recovery.COMPOSE_CONFIG_FILES_LABEL: configs,
        }
    )


def test_docker_metadata_parsing_requires_compose_contract_and_confines_configs(tmp_path: Path):
    (tmp_path / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    root, configs, project = recovery.parse_compose_labels(_labels(tmp_path))
    assert root == tmp_path.resolve()
    assert configs == ((tmp_path / "compose.yml").resolve(),)
    assert project == "edfinder-v3-phase4c-full-20260827_r5"

    outside = tmp_path.parent / "outside.yml"
    outside.write_text("services: {}\n", encoding="utf-8")
    with pytest.raises(recovery.RecoveryError, match="escapes"):
        recovery.parse_compose_labels(_labels(tmp_path, str(outside)))

    parsed = json.loads(_labels(tmp_path))
    del parsed[recovery.COMPOSE_PROJECT_LABEL]
    with pytest.raises(recovery.RecoveryError, match="project label"):
        recovery.parse_compose_labels(json.dumps(parsed))


@pytest.mark.parametrize(
    "name",
    (
        ".env",
        ".env.production",
        "credentials.json",
        "client-secret.yaml",
        "API_TOKEN.txt",
        "private_key.py",
        "server.pem",
        "server.crt",
        "id_rsa.txt",
    ),
)
def test_secret_names_are_rejected_case_insensitively(tmp_path: Path, name: str):
    (tmp_path / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / name).write_text("must not be archived\n", encoding="utf-8")
    files = recovery.collect_files(tmp_path, [tmp_path / "compose.yml"])
    assert [item.relative for item in files] == ["compose.yml"]


@pytest.mark.parametrize("name", ("backup.sql", "dump.sql", "data.sql", "logs.txt", "pgbackrest.json", "LOGS.TXT"))
def test_forbidden_content_category_stems_are_rejected(tmp_path: Path, name: str):
    (tmp_path / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / name).write_text("forbidden\n", encoding="utf-8")
    assert [item.relative for item in recovery.collect_files(tmp_path, [tmp_path / "compose.yml"])] == ["compose.yml"]


def test_symlink_and_config_traversal_fail_closed(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("print('outside')\n", encoding="utf-8")
    (source / "linked.py").symlink_to(outside)
    with pytest.raises(recovery.RecoveryError, match="symlink"):
        recovery.collect_files(source, [source / "compose.yml"])


def test_file_count_per_file_and_total_size_bounds_are_inclusive(tmp_path: Path, monkeypatch):
    compose = tmp_path / "compose.yml"
    compose.write_bytes(b"1234")
    (tmp_path / "safe.py").write_bytes(b"5678")
    monkeypatch.setattr(recovery, "MAX_FILES", 2)
    monkeypatch.setattr(recovery, "MAX_FILE_BYTES", 4)
    monkeypatch.setattr(recovery, "MAX_TOTAL_BYTES", 8)
    assert len(recovery.collect_files(tmp_path, [compose])) == 2

    (tmp_path / "extra.md").write_bytes(b"x")
    with pytest.raises(recovery.RecoveryError, match="total-size|file-count"):
        recovery.collect_files(tmp_path, [compose])

    (tmp_path / "extra.md").unlink()
    (tmp_path / "safe.py").write_bytes(b"12345")
    with pytest.raises(recovery.RecoveryError, match="per-file"):
        recovery.collect_files(tmp_path, [compose])


def test_archive_manifest_and_receipt_prove_no_db_and_no_mutation(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    script = tmp_path / "Dockerfile"
    script.write_text("FROM scratch\n", encoding="utf-8")
    files = recovery.collect_files(tmp_path, [compose])
    output = io.BytesIO()
    recovery.stream_archive(
        tmp_path.resolve(), recovery.EXPECTED_COMPOSE_PROJECT, files, output,
        target_host_identity="ed-new.example", trusted_commit="a" * 40, trusted_ref="refs/heads/main",
    )

    archive_bytes = output.getvalue()
    assert hashlib.sha256(archive_bytes).hexdigest()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as bundle:
        names = bundle.getnames()
        manifest = json.load(bundle.extractfile("recovery-manifest.json"))
        receipt = json.load(bundle.extractfile("recovery-receipt.json"))
    assert names == ["source/Dockerfile", "source/compose.yml", "recovery-manifest.json", "recovery-receipt.json"]
    assert [entry["path"] for entry in manifest["files"]] == ["Dockerfile", "compose.yml"]
    assert all(len(entry["sha256"]) == 64 for entry in manifest["files"])
    assert receipt["db_access"] is False
    assert receipt["host_mutation"] is False
    assert receipt["docker_inspect_env"] is False
    assert receipt["compose_project"] == recovery.EXPECTED_COMPOSE_PROJECT
    assert receipt["target_host_identity"] == "ed-new.example"
    assert receipt["trusted_implementation_commit"] == "a" * 40
    assert receipt["trusted_implementation_ref"] == "refs/heads/main"
    assert receipt["exit_status"] == 0 and receipt["outcome"] == "success"
    assert receipt["start_utc"].endswith("Z") and receipt["end_utc"].endswith("Z")


def test_archive_uses_exact_validated_bytes_after_path_replacement(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_bytes(b"validated bytes")
    files = recovery.collect_files(tmp_path, [compose])
    compose.unlink()
    compose.write_bytes(b"replacement secret bytes")
    output = io.BytesIO()
    recovery.stream_archive(tmp_path.resolve(), recovery.EXPECTED_COMPOSE_PROJECT, files, output)
    with tarfile.open(fileobj=io.BytesIO(output.getvalue()), mode="r:gz") as bundle:
        payload = bundle.extractfile("source/compose.yml").read()
        manifest = json.load(bundle.extractfile("recovery-manifest.json"))
    assert payload == b"validated bytes"
    assert manifest["files"][0]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_walk_errors_fail_closed(tmp_path: Path, monkeypatch):
    (tmp_path / "compose.yml").write_text("services: {}\n", encoding="utf-8")

    def broken_walk(*args, **kwargs):
        kwargs["onerror"](PermissionError(13, "denied", str(tmp_path / "unreadable")))
        return iter(())

    monkeypatch.setattr(recovery.os, "walk", broken_walk)
    with pytest.raises(recovery.RecoveryError, match="traverse"):
        recovery.collect_files(tmp_path, [tmp_path / "compose.yml"])


def test_compose_project_identity_must_match_exactly(tmp_path: Path):
    (tmp_path / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    labels = json.loads(_labels(tmp_path))
    labels[recovery.COMPOSE_PROJECT_LABEL] = "plausible-but-wrong"
    with pytest.raises(recovery.RecoveryError, match="retained project"):
        recovery.parse_compose_labels(json.dumps(labels))


def test_workflow_uses_exact_allowlist_pinned_trust_and_artifact_upload():
    root = Path(__file__).parents[1]
    workflow = (root / ".github/workflows/chatgpt-ed-new-ops.yml").read_text()
    request = (root / ".github/workflows/chatgpt-ed-new-ops-request.yml").read_text()
    assert "recover-v3-runtime-contract" in workflow
    assert "ED_NEW_OPERATOR_KNOWN_HOSTS" in workflow
    assert "ssh-keyscan" not in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "push:" not in workflow
    assert "environment: ed-new-operator" in workflow
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "ref: ${{ github.sha }}" in workflow
    assert "secrets.ED_NEW_OPERATOR_" not in request
    assert "environment:" not in request
    assert '"ref":"main"' in request
    assert "fetch-depth: 0" in request
    assert "git log --format= --name-status" in request
    assert "origin/main" in request
    assert "ssh-keyscan" not in request
    assert "docker ps --format" in workflow and 'out=$(docker ps' in workflow
    assert "--trusted-commit '$TRUSTED_COMMIT'" in workflow
    assert "--target-host-identity '$SSH_HOST'" in workflow
    recovery_source = (root / "scripts/operator/recover_v3_runtime_contract.py").read_text()
    assert "{{json .Config.Labels}}" in recovery_source
    assert "Config.Env" not in recovery_source
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    assert "retention-days: 14" in workflow
