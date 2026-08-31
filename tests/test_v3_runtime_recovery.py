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


def test_docker_metadata_parsing_requires_compose_contract_and_confines_configs(
    tmp_path: Path,
):
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


def test_symlink_and_config_traversal_fail_closed(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("print('outside')\n", encoding="utf-8")
    (source / "linked.py").symlink_to(outside)
    with pytest.raises(recovery.RecoveryError, match="symlink"):
        recovery.collect_files(source, [source / "compose.yml"])


def test_file_count_per_file_and_total_size_bounds_are_inclusive(
    tmp_path: Path, monkeypatch
):
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
    recovery.stream_archive(tmp_path.resolve(), "retained-project", files, output)

    archive_bytes = output.getvalue()
    assert hashlib.sha256(archive_bytes).hexdigest()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as bundle:
        names = bundle.getnames()
        manifest = json.load(bundle.extractfile("recovery-manifest.json"))
        receipt = json.load(bundle.extractfile("recovery-receipt.json"))
    assert names == [
        "source/Dockerfile",
        "source/compose.yml",
        "recovery-manifest.json",
        "recovery-receipt.json",
    ]
    assert [entry["original"]["path"] for entry in manifest["files"]] == [
        "Dockerfile",
        "compose.yml",
    ]
    assert all(len(entry["original"]["sha256"]) == 64 for entry in manifest["files"])
    assert manifest["disposition_counts"] == {
        "excluded": 0,
        "redacted": 0,
        "verbatim": 2,
    }
    assert receipt["db_access"] is False
    assert receipt["host_mutation"] is False
    assert receipt["live_docker_environment_queried"] is False
    assert receipt["compose_project"] == "retained-project"


def test_workflow_uses_exact_allowlist_pinned_trust_and_artifact_upload():
    workflow = (
        Path(__file__).parents[1] / ".github/workflows/chatgpt-ed-new-ops.yml"
    ).read_text()
    assert "recover-v3-runtime-contract" in workflow
    assert "ED_NEW_OPERATOR_KNOWN_HOSTS" in workflow
    assert "ssh-keyscan" not in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "ref: main" in workflow
    assert "trusted-main/scripts/operator/recover_v3_runtime_contract.py" in workflow
    assert 'git diff --name-only "$BEFORE_SHA" "$CURRENT_SHA"' in workflow
    assert (
        "{{json .Config.Labels}}"
        in (
            Path(__file__).parents[1]
            / "scripts/operator/recover_v3_runtime_contract.py"
        ).read_text()
    )
    assert (
        "Config.Env"
        not in (
            Path(__file__).parents[1]
            / "scripts/operator/recover_v3_runtime_contract.py"
        ).read_text()
    )
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
    )


def _archive(
    tmp_path: Path, required: Path
) -> tuple[bytes, dict, dict, dict[str, bytes]]:
    files = recovery.collect_files(tmp_path, [required])
    output = io.BytesIO()
    recovery.stream_archive(tmp_path, "synthetic-project", files, output, [required])
    raw = output.getvalue()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as bundle:
        members = {
            member.name: bundle.extractfile(member).read()
            for member in bundle.getmembers()
            if member.isfile()
        }
    return (
        raw,
        json.loads(members["recovery-manifest.json"]),
        json.loads(members["recovery-receipt.json"]),
        members,
    )


def test_templates_and_ordinary_mentions_remain_verbatim(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    content = "services:\n  db:\n    environment:\n      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}\n      API_TOKEN: ${{ secrets.API_TOKEN }}\n"
    compose.write_text(content)
    (tmp_path / "notes.py").write_text(
        "# A password, token, or key is supplied by the operator.\npassword_field_name = 'identifier'\n"
    )
    _, manifest, _, members = _archive(tmp_path, compose)
    assert members["source/compose.yml"] == content.encode()
    assert manifest["disposition_counts"] == {
        "excluded": 0,
        "redacted": 0,
        "verbatim": 2,
    }


def test_required_compose_literal_is_redacted_without_corrupting_structure(
    tmp_path: Path,
):
    compose = tmp_path / "compose.yml"
    compose.write_text(
        "services:\n  db:\n    environment:\n      POSTGRES_PASSWORD: fixture_compose_value\n"
    )
    _, manifest, _, members = _archive(tmp_path, compose)
    assert members["source/compose.yml"] == (
        b"services:\n  db:\n    environment:\n      POSTGRES_PASSWORD: REDACTED\n"
    )
    assert manifest["files"][0]["disposition"] == "redacted"


def test_json_source_identifier_with_password_word_is_not_a_secret(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n")
    source = tmp_path / "schema.json"
    source.write_text('{"password_field_name": "ordinary_identifier"}\n')
    _, manifest, _, members = _archive(tmp_path, compose)
    assert members["source/schema.json"] == source.read_bytes()
    entry = next(
        item for item in manifest["files"] if item["original"]["path"] == "schema.json"
    )
    assert entry["disposition"] == "verbatim"


def test_text_uri_is_redacted_and_both_identities_are_recorded(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n")
    source = tmp_path / "recover.py"
    synthetic = "postgresql://fixture_user:fixture_only_password@db.invalid/example"
    source.write_text(f'url = "{synthetic}"\n')
    _, manifest, _, members = _archive(tmp_path, compose)
    payload = members["source/recover.py"]
    assert synthetic.encode() not in payload
    assert b"postgresql://REDACTED:REDACTED@" in payload
    entry = next(
        item for item in manifest["files"] if item["original"]["path"] == "recover.py"
    )
    assert entry["disposition"] == "redacted"
    assert (
        entry["original"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert entry["archive"]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_docker_inspect_json_environment_is_structurally_redacted(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n")
    capture = tmp_path / "inspect.json"
    first = "fixture_password_value"
    second = "redis://fixture_user:fixture_redis_value@cache.invalid/0"
    capture.write_text(
        json.dumps(
            {
                "Config": {
                    "Env": [
                        f"POSTGRES_PASSWORD={first}",
                        f"DATABASE_URL={second}",
                        "SAFE=yes",
                    ]
                }
            }
        )
    )
    _, manifest, receipt, members = _archive(tmp_path, compose)
    parsed = json.loads(members["source/inspect.json"])
    assert parsed["Config"]["Env"] == [
        "POSTGRES_PASSWORD=REDACTED",
        "DATABASE_URL=redis://REDACTED:REDACTED@cache.invalid/0",
        "SAFE=yes",
    ]
    assert (
        first.encode() not in members["source/inspect.json"]
        and second.encode() not in members["source/inspect.json"]
    )
    assert receipt["source_files_with_environment_material"] == 1
    assert receipt["source_environment_files_redacted"] == 1
    assert manifest["disposition_counts"]["redacted"] == 1


def test_private_key_and_recognized_token_are_excluded_without_value_leak(
    tmp_path: Path,
):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n")
    key = "-----BEGIN PRIVATE KEY-----\nfixture-material\n-----END PRIVATE KEY-----"
    token = "ghp_" + "SyntheticFixtureToken1234567890"
    (tmp_path / "historical.py").write_text(key)
    (tmp_path / "legacy.sh").write_text(token)
    raw, manifest, receipt, members = _archive(tmp_path, compose)
    assert key.encode() not in raw and token.encode() not in raw
    assert "source/historical.py" not in members and "source/legacy.sh" not in members
    assert manifest["disposition_counts"]["excluded"] == 2
    assert receipt["disposition_counts"]["excluded"] == 2


@pytest.mark.parametrize("content", [b"\xff\xfe", b'{"Env": ['])
def test_preflight_failure_emits_no_output_and_never_echoes_content(
    tmp_path: Path, content: bytes
):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n")
    bad = tmp_path / "bad.json"
    bad.write_bytes(content)
    output = io.BytesIO()
    with pytest.raises(recovery.RecoveryError) as caught:
        recovery.stream_archive(
            tmp_path,
            "project",
            recovery.collect_files(tmp_path, [compose]),
            output,
            [compose],
        )
    assert output.getvalue() == b""
    assert content not in str(caught.value).encode()


def test_archive_is_deterministic_and_final_scan_finds_no_secret(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n")
    synthetic = "postgres://fixture:fixture_password@db.invalid/db"
    (tmp_path / "script.sh").write_text(f"DATABASE_URL={synthetic}\n")
    first, manifest, receipt, members = _archive(tmp_path, compose)
    second, _, _, _ = _archive(tmp_path, compose)
    assert first == second
    assert manifest["selected_file_count"] == sum(
        manifest["disposition_counts"].values()
    )
    assert manifest["archive_file_count"] == len(members) - 2
    assert receipt["archive_total_bytes"] == sum(
        item["archive"]["size"] for item in manifest["files"] if "archive" in item
    )
    for payload in members.values():
        text = payload.decode()
        assert not recovery._unsafe(text)
        assert synthetic not in text


def test_workflow_publishes_only_a_fresh_complete_recovery_archive():
    workflow = (
        Path(__file__).parents[1] / ".github/workflows/chatgpt-ed-new-ops.yml"
    ).read_text()
    assert 'staging_dir="$(mktemp -d ' in workflow
    assert "trap cleanup EXIT" in workflow
    assert '> "$archive"' in workflow
    assert 'test -s "$archive"' in workflow
    assert 'sha256sum "$(basename "$archive")"' in workflow
    assert 'artifact_dir="$(mktemp -d ' in workflow
    assert 'mv "$staging_dir" "$artifact_dir"' in workflow
    assert (
        'printf \'artifact_dir=%s\\n\' "$artifact_dir" >> "$GITHUB_OUTPUT"' in workflow
    )
    assert (
        "if: success() && steps.request.outputs.operation == 'recover-v3-runtime-contract'"
        in workflow
    )
    assert "${{ steps.recovery.outputs.artifact_dir }}" in workflow
    assert "${{ runner.temp }}/edfinder-v3-runtime-recovery/" not in workflow
