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


def _archive_metadata(output: io.BytesIO) -> tuple[list[str], dict, dict]:
    with tarfile.open(fileobj=io.BytesIO(output.getvalue()), mode="r:gz") as bundle:
        names = bundle.getnames()
        manifest_source = bundle.extractfile("recovery-manifest.json")
        receipt_source = bundle.extractfile("recovery-receipt.json")
        assert manifest_source is not None
        assert receipt_source is not None
        manifest = json.load(manifest_source)
        receipt = json.load(receipt_source)
    return names, manifest, receipt


def _included_paths(included: list[recovery.ScannedFile]) -> list[str]:
    return [item.relative for item in included]


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
    assert [relative for _, relative, _ in files] == ["compose.yml"]


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


def test_archive_manifest_and_receipt_prove_no_db_no_mutation_and_exact_scan(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    files = recovery.collect_files(tmp_path, [compose])
    output = io.BytesIO()
    recovery.stream_archive(
        tmp_path.resolve(),
        "retained-project",
        files,
        output,
        required_configs=[compose],
    )

    archive_bytes = output.getvalue()
    assert hashlib.sha256(archive_bytes).hexdigest()
    names, manifest, receipt = _archive_metadata(output)
    assert names == [
        "source/Dockerfile",
        "source/compose.yml",
        "recovery-manifest.json",
        "recovery-receipt.json",
    ]
    assert [entry["path"] for entry in manifest["files"]] == ["Dockerfile", "compose.yml"]
    assert all(len(entry["sha256"]) == 64 for entry in manifest["files"])
    assert manifest["excluded_sensitive_file_count"] == 0
    assert manifest["excluded_sensitive_files"] == []
    assert receipt["db_access"] is False
    assert receipt["host_mutation"] is False
    assert receipt["docker_inspect_env"] is False
    assert receipt["compose_project"] == "retained-project"
    scan = receipt["source_content_scan"]
    assert scan["performed"] is True
    assert scan["mode"] == "fail-closed-before-stream"
    assert scan["candidate_file_count"] == 2
    assert scan["excluded_sensitive_file_count"] == 0
    assert scan["archive_uses_exact_scanned_bytes"] is True


def test_safe_placeholders_file_indirection_and_empty_defaults_remain_recoverable(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text(
        "\n".join(
            (
                "services:",
                "  app:",
                "    environment:",
                "      ADMIN_TOKEN: ${ADMIN_TOKEN:-}",
                "      FRONTIER_CLIENT_SECRET: ${FRONTIER_CLIENT_SECRET:-}",
                "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}",
                '      DATABASE_URL: "postgresql://app:${POSTGRES_PASSWORD}@db/app"',
                "      GLITCHTIP_GRAFANA_AUTH_TOKEN_SECRET_FILE: /run/secrets/glitchtip_grafana_auth_token",
                "",
            )
        ),
        encoding="utf-8",
    )
    script = tmp_path / "start.sh"
    script.write_text(
        "\n".join(
            (
                'OPENAI_API_KEY="${OPENAI_API_KEY}"',
                'DATABASE_URL="postgresql://app:${POSTGRES_PASSWORD}@db/app"',
                'REDIS_URL="redis://:${REDIS_PASSWORD}@cache/0"',
                'CACHE_URL="host=cache password=${CACHE_PASSWORD}"',
                'DATABASE_URL="postgresql://db/app?password=${POSTGRES_PASSWORD}"',
                'DB_DSN_DIRECT="host=db user=app password=${DB_PASSWORD}"',
                "",
            )
        ),
        encoding="utf-8",
    )
    files = recovery.collect_files(tmp_path, [compose])
    output = io.BytesIO()
    recovery.stream_archive(
        tmp_path.resolve(),
        "retained-project",
        files,
        output,
        required_configs=[compose],
    )
    names, manifest, _ = _archive_metadata(output)
    assert "source/compose.yml" in names
    assert "source/start.sh" in names
    assert manifest["excluded_sensitive_file_count"] == 0


def test_nonempty_shell_default_is_not_treated_as_placeholder(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text(
        "services:\n  app:\n    environment:\n      ADMIN_TOKEN: ${ADMIN_TOKEN:-literal-secret}\n",
        encoding="utf-8",
    )
    files = recovery.collect_files(tmp_path, [compose])
    with pytest.raises(recovery.RecoveryError, match="Required Compose config"):
        recovery.stream_archive(
            tmp_path.resolve(),
            "retained-project",
            files,
            io.BytesIO(),
            required_configs=[compose],
        )


def test_repository_compose_contract_has_no_content_scan_findings():
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    assert recovery._scan_text(compose, "docker-compose.yml") == ()


def test_optional_credentialed_uri_is_excluded_with_provenance_only(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    secret = "archive-" + "must-not-contain-this"
    unsafe = tmp_path / "legacy-script.py"
    unsafe.write_text(
        "dsn = " + repr("postgresql://" + f"app:{secret}@db/app") + "\n",
        encoding="utf-8",
    )
    files = recovery.collect_files(tmp_path, [compose])
    output = io.BytesIO()
    recovery.stream_archive(
        tmp_path.resolve(),
        "retained-project",
        files,
        output,
        required_configs=[compose],
    )

    names, manifest, receipt = _archive_metadata(output)
    assert "source/legacy-script.py" not in names
    assert manifest["excluded_sensitive_file_count"] == 1
    excluded = manifest["excluded_sensitive_files"][0]
    assert excluded["path"] == "legacy-script.py"
    assert "credentialed-uri" in excluded["findings"]
    assert len(excluded["sha256"]) == 64
    assert receipt["source_content_scan"]["excluded_sensitive_file_count"] == 1

    with tarfile.open(fileobj=io.BytesIO(output.getvalue()), mode="r:gz") as bundle:
        retained_payload = b""
        for member in bundle.getmembers():
            if not member.isfile():
                continue
            source = bundle.extractfile(member)
            if source is not None:
                retained_payload += source.read()
    assert secret.encode() not in retained_payload


@pytest.mark.parametrize(
    ("filename", "content", "finding"),
    (
        ("legacy-cache.py", 'cache = "redis://:redis-password@cache/0"\n', "credentialed-uri"),
        (
            "legacy-query.py",
            'dsn = "postgresql://db/app?sslmode=require&password=query-password"\n',
            "credentialed-uri",
        ),
        (
            "legacy-dsn.sh",
            'DB_DSN_DIRECT="host=db dbname=app user=app password=dsn-password"\n',
            "credentialed-dsn",
        ),
        ("settings.py", 'POSTGRES_PASSWORD = "python-password"\n', "sensitive-environment-assignment"),
        (
            "storage.sh",
            "RCLONE_CONFIG_STORAGEBOX_PASS=storagebox-password\n",
            "sensitive-environment-assignment",
        ),
        (
            "Dockerfile",
            "FROM scratch\nENV POSTGRES_PASSWORD docker-password\n",
            "sensitive-environment-assignment",
        ),
        (
            "cache.txt",
            'CACHE_URL="memcached://app:memcached-password@cache"\n',
            "credentialed-uri",
        ),
        (
            "roles.sql",
            "ALTER ROLE app LOGIN PASSWORD 'sql-password';\n",
            "sql-password-statement",
        ),
    ),
)
def test_additional_credential_forms_are_excluded(
    tmp_path: Path,
    filename: str,
    content: str,
    finding: str,
):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    (tmp_path / filename).write_text(content, encoding="utf-8")
    files = recovery.collect_files(tmp_path, [compose])
    included, excluded = recovery.scan_selected_files(files, [compose])
    assert _included_paths(included) == ["compose.yml"]
    assert len(excluded) == 1
    assert excluded[0]["path"] == filename
    assert finding in excluded[0]["findings"]


@pytest.mark.parametrize(
    "mapping",
    (
        'services: {db: {environment: {"POSTGRES_PASSWORD": quoted-password}}}\n',
        "services: {db: {environment: {POSTGRES_PASSWORD: flow-password}}}\n",
    ),
)
def test_quoted_and_flow_yaml_sensitive_keys_fail_required_compose(tmp_path: Path, mapping: str):
    compose = tmp_path / "compose.yml"
    compose.write_text(mapping, encoding="utf-8")
    files = recovery.collect_files(tmp_path, [compose])
    with pytest.raises(recovery.RecoveryError, match="Required Compose config"):
        recovery.scan_selected_files(files, [compose])


def test_historical_docker_env_json_is_excluded_without_secret_values(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    secret = "historical-" + "credential-value"
    inspect_file = tmp_path / "container-inspect-start.json"
    inspect_file.write_text(
        json.dumps(
            {
                "Config": {
                    "Env": [
                        "POSTGRES_" + f"PASSWORD={secret}",
                        "DATABASE_" + "URL=" + "postgresql://" + f"app:{secret}@db/app",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    files = recovery.collect_files(tmp_path, [compose])
    output = io.BytesIO()
    recovery.stream_archive(
        tmp_path.resolve(),
        "retained-project",
        files,
        output,
        required_configs=[compose],
    )
    names, manifest, _ = _archive_metadata(output)
    assert "source/container-inspect-start.json" not in names
    excluded = manifest["excluded_sensitive_files"][0]
    assert excluded["path"] == "container-inspect-start.json"
    assert "credentialed-uri" in excluded["findings"]
    assert "sensitive-environment-assignment" in excluded["findings"]
    assert secret not in json.dumps(manifest)


@pytest.mark.parametrize(
    ("filename", "payload", "finding"),
    (
        ("key-material.md", lambda: "-----BEGIN " + "PRIVATE KEY-----\nnot-a-real-key\n", "private-key-material"),
        (
            "encrypted-key.md",
            lambda: "-----BEGIN ENCRYPTED " + "PRIVATE KEY-----\nnot-a-real-key\n",
            "private-key-material",
        ),
        ("provider.txt", lambda: "sk-" + "a" * 30, "openai-api-token"),
        ("github.txt", lambda: "ghp_" + "b" * 30, "github-token"),
        ("cloud.txt", lambda: "AKIA" + "C" * 16, "aws-access-key"),
    ),
)
def test_recognized_secret_material_is_excluded(
    tmp_path: Path,
    filename: str,
    payload,
    finding: str,
):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    (tmp_path / filename).write_text(payload(), encoding="utf-8")
    files = recovery.collect_files(tmp_path, [compose])
    included, excluded = recovery.scan_selected_files(files, [compose])
    assert _included_paths(included) == ["compose.yml"]
    assert len(excluded) == 1
    assert excluded[0]["path"] == filename
    assert finding in excluded[0]["findings"]


def test_required_compose_secret_fails_before_archive_bytes_are_emitted(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    secret = "required-" + "secret-value"
    compose.write_text(
        "services:\n  db:\n    environment:\n      POSTGRES_PASSWORD: " + secret + "\n",
        encoding="utf-8",
    )
    files = recovery.collect_files(tmp_path, [compose])
    output = io.BytesIO()
    with pytest.raises(recovery.RecoveryError, match="Required Compose config"):
        recovery.stream_archive(
            tmp_path.resolve(),
            "retained-project",
            files,
            output,
            required_configs=[compose],
        )
    assert output.getvalue() == b""


def test_invalid_utf8_selected_file_fails_before_archive_bytes_are_emitted(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "broken.txt").write_bytes(b"\xff\xfe")
    files = recovery.collect_files(tmp_path, [compose])
    output = io.BytesIO()
    with pytest.raises(recovery.RecoveryError, match="not valid UTF-8"):
        recovery.stream_archive(
            tmp_path.resolve(),
            "retained-project",
            files,
            output,
            required_configs=[compose],
        )
    assert output.getvalue() == b""


def test_selected_file_identity_change_fails_closed(tmp_path: Path):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    script = tmp_path / "safe.py"
    script.write_text("print('safe')\n", encoding="utf-8")
    files = recovery.collect_files(tmp_path, [compose])

    original = tmp_path / "original.py"
    script.rename(original)
    script.write_text("print('replacement')\n", encoding="utf-8")

    with pytest.raises(recovery.RecoveryError, match="identity changed"):
        recovery.scan_selected_files(files, [compose])


def test_archive_uses_exact_payload_returned_by_content_scan(tmp_path: Path, monkeypatch):
    compose = tmp_path / "compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    script = tmp_path / "safe.py"
    script.write_text("POSTGRES_PASSWORD='path-now-contains-secret'\n", encoding="utf-8")
    files = recovery.collect_files(tmp_path, [compose])

    compose_payload = b"services: {}\n"
    script_payload = b"print('bytes-that-were-scanned')\n"
    scanned = [
        recovery.ScannedFile(
            relative="compose.yml",
            mode=0o644,
            payload=compose_payload,
            sha256=hashlib.sha256(compose_payload).hexdigest(),
        ),
        recovery.ScannedFile(
            relative="safe.py",
            mode=0o644,
            payload=script_payload,
            sha256=hashlib.sha256(script_payload).hexdigest(),
        ),
    ]
    monkeypatch.setattr(recovery, "scan_selected_files", lambda *_args, **_kwargs: (scanned, []))

    output = io.BytesIO()
    recovery.stream_archive(
        tmp_path.resolve(),
        "retained-project",
        files,
        output,
        required_configs=[compose],
    )
    with tarfile.open(fileobj=io.BytesIO(output.getvalue()), mode="r:gz") as bundle:
        source = bundle.extractfile("source/safe.py")
        assert source is not None
        assert source.read() == script_payload
        manifest_source = bundle.extractfile("recovery-manifest.json")
        assert manifest_source is not None
        manifest = json.load(manifest_source)
    safe_entry = next(entry for entry in manifest["files"] if entry["path"] == "safe.py")
    assert safe_entry["sha256"] == hashlib.sha256(script_payload).hexdigest()


def test_workflow_uses_exact_allowlist_pinned_trust_and_artifact_upload():
    workflow = (Path(__file__).parents[1] / ".github/workflows/chatgpt-ed-new-ops.yml").read_text()
    helper = (
        Path(__file__).parents[1] / "scripts/operator/recover_v3_runtime_contract.py"
    ).read_text()
    assert "recover-v3-runtime-contract" in workflow
    assert "ED_NEW_OPERATOR_KNOWN_HOSTS" in workflow
    assert "ssh-keyscan" not in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "ref: main" in workflow
    assert "trusted-main/scripts/operator/recover_v3_runtime_contract.py" in workflow
    assert 'git diff --name-only "$BEFORE_SHA" "$CURRENT_SHA"' in workflow
    assert "{{json .Config.Labels}}" in helper
    assert "Config.Env" not in helper
    assert "scan_selected_files" in helper
    assert "archive_uses_exact_scanned_bytes" in helper
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
