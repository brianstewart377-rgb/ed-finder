"""F2d release refusals use local, synthetic release and ledger evidence only."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "ranking_version", "ranking_sha256", "f2d_operator_code_sha256",
    "minimum_schema_compatible_image", "rollback_targets",
)
MINIMUM = "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:" + "a" * 64
LATER = "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:" + "b" * 64
EARLIER = "ghcr.io/brianstewart377-rgb/ed-finder/v3-backend@sha256:" + "c" * 64


@pytest.fixture
def deployer():
    spec = importlib.util.spec_from_file_location(
        "v3_production_deploy_f2d_tests", ROOT / "scripts/operator/v3_production_deploy.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy_attestation():
    return json.loads((ROOT / "deploy/v3-production/target-authority.json").read_text())[
        "accepted_release_schema_compatibility"
    ]


@pytest.fixture
def attestation(legacy_attestation):
    return {
        **legacy_attestation,
        "ranking_version": "fixture-ranking-v1",
        "ranking_sha256": "d" * 64,
        "f2d_operator_code_sha256": "e" * 64,
        "minimum_schema_compatible_image": MINIMUM,
        "rollback_targets": [MINIMUM, LATER],
    }


def registered_entries():
    rows = []
    for line in (ROOT / "sql/v3/migration-manifest.txt").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        checksum, ledger_name, path = line.split()
        rows.append({"path": "sql/" + path, "ledger_name": ledger_name,
                     "mode": "auto", "sha256": checksum})
    return rows


def complete_entries():
    # The future migration is deliberately synthetic: no production identity is invented.
    return [*registered_entries(), {
        "path": "sql/v3/migrations/016_fixture_governed_purge.sql",
        "ledger_name": "016_fixture_governed_purge.sql", "mode": "auto", "sha256": "f" * 64,
    }]


def generation():
    return {
        "generation_key": "ratings_v4_prod_p4_parallel_v1",
        "derived_generation_id": "cfc25d36-3bc7-4011-a465-d6460eaaf826",
        "publication_sequence": 1,
        "state": "PUBLISHED",
        "finder_products": [],
    }


def test_current_accepted_release_remains_valid_without_f2d_fields(deployer, legacy_attestation):
    assert not set(FIELDS) & set(legacy_attestation)
    deployer.validate_release_compatibility_shape(legacy_attestation)
    authority = json.loads((ROOT / "deploy/v3-production/target-authority.json").read_text())
    assert deployer.validate_authority(authority) == []


def test_complete_f2d_attestation_is_valid(deployer, attestation):
    deployer.validate_release_compatibility_shape(attestation)


@pytest.mark.parametrize("field", FIELDS)
def test_f2d_attestation_rejects_partial_group(deployer, attestation, field):
    attestation.pop(field)
    with pytest.raises(deployer.DeploymentError, match="f2d.*(incomplete|partial|required)"):
        deployer.validate_release_compatibility_shape(attestation)


@pytest.mark.parametrize("field", FIELDS)
def test_a_single_f2d_field_requires_whole_group(deployer, legacy_attestation, attestation, field):
    legacy_attestation[field] = attestation[field]
    with pytest.raises(deployer.DeploymentError, match="f2d.*(incomplete|partial|required)"):
        deployer.validate_release_compatibility_shape(legacy_attestation)


@pytest.mark.parametrize(("field", "invalid"), [
    ("ranking_version", ""), ("ranking_version", "   "), ("ranking_version", "x" * 257),
    ("ranking_version", 1), ("ranking_sha256", "A" * 64), ("ranking_sha256", "d" * 63),
    ("f2d_operator_code_sha256", "E" * 64), ("f2d_operator_code_sha256", None),
    ("minimum_schema_compatible_image", "registry.example/backend:latest"),
    ("minimum_schema_compatible_image", "registry.example/backend@sha256:" + "A" * 64),
    ("rollback_targets", []), ("rollback_targets", ["registry.example/backend:latest"]),
    ("rollback_targets", [MINIMUM, MINIMUM]), ("rollback_targets", [EARLIER, MINIMUM]),
])
def test_f2d_attestation_refusals_name_invalid_field(deployer, attestation, field, invalid):
    attestation[field] = invalid
    with pytest.raises(deployer.DeploymentError, match=field):
        deployer.validate_release_compatibility_shape(attestation)


def test_release_gate_has_one_exact_required_migration_set(deployer):
    assert deployer.F2D_REQUIRED_MIGRATIONS == ("014", "010", "011", "013", "015", "016")


def test_current_manifest_refuses_missing_016_by_name(deployer):
    entries = registered_entries()
    with pytest.raises(deployer.DeploymentError, match="^required_migration_not_registered:016$"):
        deployer.validate_f2d_migrations({"migration_set_entries": entries}, entries)


def test_fixture_manifest_and_exact_ledger_with_all_six_pass(deployer):
    entries = complete_entries()
    deployer.validate_f2d_migrations({"migration_set_entries": deepcopy(entries)}, entries)


@pytest.mark.parametrize("number", ["014", "010", "011", "013", "015", "016"])
def test_gate_refuses_each_missing_applied_migration(deployer, number):
    entries = complete_entries()
    applied = [entry for entry in entries if not entry["ledger_name"].startswith(number + "_")]
    with pytest.raises(deployer.DeploymentError, match=f"^required_migration_not_applied:{number}$"):
        deployer.validate_f2d_migrations({"migration_set_entries": applied}, entries)


@pytest.mark.parametrize("number", ["014", "010", "011", "013", "015", "016"])
def test_gate_refuses_each_ledger_hash_mismatch(deployer, number):
    entries = complete_entries()
    applied = deepcopy(entries)
    next(row for row in applied if row["ledger_name"].startswith(number + "_"))["sha256"] = "0" * 64
    with pytest.raises(deployer.DeploymentError, match=f"^required_migration_hash_mismatch:{number}$"):
        deployer.validate_f2d_migrations({"migration_set_entries": applied}, entries)


def test_f2d_detection_uses_applied_product_publication_migration(deployer):
    entries = registered_entries()
    candidate = {"git_sha": "a" * 40}
    assert deployer.is_f2d_release(candidate, {"migration_set_entries": entries}) is True
    before_015 = [entry for entry in entries if not entry["ledger_name"].startswith("015_")]
    assert deployer.is_f2d_release(candidate, {"migration_set_entries": before_015}) is False


def test_explicit_attestation_also_selects_f2d_gate(deployer, attestation):
    assert deployer.is_f2d_release({}, {"migration_set_entries": []}, attestation) is True


def test_exact_published_target_without_products_passes(deployer):
    # No READY, receipt, row count, publication timestamp or audit is supplied or required.
    deployer.validate_f2d_generation(generation())


@pytest.mark.parametrize(("field", "invalid"), [
    ("generation_key", "ratings_v4_prod_p4_opt1"),
    ("derived_generation_id", "00000000-0000-0000-0000-000000000000"),
    ("publication_sequence", 2), ("state", "READY"),
])
def test_gate_refuses_wrong_current_generation(deployer, field, invalid):
    observed = generation()
    observed[field] = invalid
    with pytest.raises(deployer.DeploymentError, match="generation"):
        deployer.validate_f2d_generation(observed)


@pytest.mark.parametrize("product", ["system_search", "system_archetype"])
def test_any_target_finder_product_refuses_even_before_ready(deployer, product):
    observed = generation()
    observed["finder_products"] = [product]
    with pytest.raises(deployer.DeploymentError, match="finder_product"):
        deployer.validate_f2d_generation(observed)


def test_trim_rollback_targets_starts_at_minimum(deployer):
    assert deployer.trim_rollback_targets([EARLIER, MINIMUM, LATER], MINIMUM) == [MINIMUM, LATER]


def test_absent_minimum_refuses_rollback_target_trimming(deployer):
    with pytest.raises(deployer.DeploymentError, match="minimum_schema_compatible_image"):
        deployer.trim_rollback_targets([EARLIER, LATER], MINIMUM)


@pytest.mark.parametrize("image", [MINIMUM, LATER])
def test_rollback_allows_images_at_or_after_boundary(deployer, attestation, image):
    deployer.require_f2d_rollback_image(image, attestation)


def test_rollback_refuses_image_below_boundary(deployer, attestation):
    with pytest.raises(deployer.DeploymentError, match="^f2d_rollback_image_incompatible$"):
        deployer.require_f2d_rollback_image(EARLIER, attestation)


def test_gate_requires_attestation(deployer):
    with pytest.raises(deployer.DeploymentError, match="^f2d_release_attestation_required$"):
        deployer.validate_f2d_attestation(None, {}, "a" * 64, "123", {})


def candidate_evidence(attestation):
    candidate = {"git_sha": attestation["source_sha"], "images": deepcopy(attestation["images"])}
    schema = {"migration_set_identity": attestation["compatible_migration_sets"][0]}
    return candidate, attestation["manifest_sha256"], attestation["release_run_id"], schema


def test_attestation_binds_exact_candidate_and_schema(deployer, attestation):
    deployer.validate_f2d_attestation(attestation, *candidate_evidence(attestation))


@pytest.mark.parametrize("mismatch", ["source_sha", "release_run_id", "manifest_sha256", "images", "schema"])
def test_attestation_rejects_other_candidate_or_schema(deployer, attestation, mismatch):
    candidate, checksum, run_id, schema = candidate_evidence(attestation)
    if mismatch == "source_sha":
        candidate["git_sha"] = "f" * 40
    elif mismatch == "release_run_id":
        run_id = "99999"
    elif mismatch == "manifest_sha256":
        checksum = "f" * 64
    elif mismatch == "images":
        candidate["images"]["backend"] = EARLIER
    else:
        schema["migration_set_identity"] = "sha256:" + "0" * 64
    with pytest.raises(deployer.DeploymentError, match="attestation"):
        deployer.validate_f2d_attestation(attestation, candidate, checksum, run_id, schema)


PROBES = [
    ("GET", "/api/archetypes/rankings?archetype=paradise&offset=9999&limit=1", None, 503),
    ("GET", "/api/archetypes/rankings?archetype=paradise&offset=9999&limit=2", None, 422),
    ("POST", "/api/local/search", {"galaxy_wide": True, "sort_by": "development", "from": 9999, "size": 1}, 503),
    ("POST", "/api/local/search", {"galaxy_wide": True, "sort_by": "development", "from": 9999, "size": 2}, 422),
]


@pytest.mark.parametrize("mismatch", [None, 0, 1, 2, 3])
def test_behavioural_probe_pairs_record_every_status_even_after_mismatch(deployer, monkeypatch, mismatch):
    calls = []
    statuses = [spec[3] if index != mismatch else 200 for index, spec in enumerate(PROBES)]

    def response(method, origin, path, body):
        assert origin == "http://127.0.0.1:58080"
        calls.append((method, path, body))
        return statuses[len(calls) - 1], finder_unavailable_payload(), "application/json"

    monkeypatch.setattr(deployer, "get", lambda origin, path: response("GET", origin, path, None))
    monkeypatch.setattr(deployer, "post", lambda origin, path, body: response("POST", origin, path, body))
    outcomes = []
    if mismatch is None:
        deployer.f2d_behavioural_probes("http://127.0.0.1:58080", outcomes)
    else:
        with pytest.raises(deployer.DeploymentError, match="^behavioural_probe_pairs_failed$"):
            deployer.f2d_behavioural_probes("http://127.0.0.1:58080", outcomes)
    assert calls == [(method, path, body) for method, path, body, _expected in PROBES]
    assert len(outcomes) == 4
    assert [item["status"] for item in outcomes] == statuses
    assert [item["expected_status"] for item in outcomes] == [503, 422, 503, 422]
    for recorded, (method, path, body, _expected) in zip(outcomes, PROBES, strict=True):
        assert recorded["method"] == method
        assert recorded["path"] == path
        assert recorded["body"] == body


def test_compatible_rollback_artifact_must_be_recorded(deployer, tmp_path, attestation):
    with pytest.raises(deployer.DeploymentError, match="^compatible_rollback_artifact_not_recorded$"):
        deployer.select_f2d_rollback(tmp_path, attestation, {"migration_set_identity": "sha256:" + "0" * 64})


@pytest.mark.parametrize("image", [MINIMUM, EARLIER])
def test_recorded_rollback_artifact_respects_boundary(deployer, monkeypatch, tmp_path, attestation, image):
    manifest = {"git_sha": "a" * 40, "images": {"backend": image, "web": "registry.example/web@sha256:" + "1" * 64}}
    body = json.dumps(manifest).encode()
    checksum = hashlib.sha256(body).hexdigest()
    path = tmp_path / f"{manifest['git_sha']}-123-{checksum}.release.json"
    path.write_bytes(body)
    path.with_name(path.name + ".sha256").write_text(f"{checksum}  {path.name}\n")
    validated = []

    def validate_manifest(candidate, *, purpose, current_migration_set):
        assert purpose == "rollback"
        assert current_migration_set == "sha256:" + "0" * 64
        validated.append(candidate)

    monkeypatch.setattr(deployer, "manifest_tool", lambda: SimpleNamespace(
        validate_manifest=validate_manifest, ManifestError=ValueError,
    ))
    schema = {"migration_set_identity": "sha256:" + "0" * 64}
    if image == EARLIER:
        with pytest.raises(deployer.DeploymentError, match="^compatible_rollback_artifact_not_recorded$"):
            deployer.select_f2d_rollback(tmp_path, attestation, schema)
    else:
        selected = deployer.select_f2d_rollback(tmp_path, attestation, schema)
        assert selected == manifest
        assert validated == [manifest]


def test_prior_runtime_cannot_bypass_f2d_boundary_with_manifest_compatibility(deployer, monkeypatch, attestation):
    schema_identity = "sha256:" + "0" * 64
    receipt = {"active_slot": "blue", "migration_set_identity": schema_identity}
    manifest = {"git_sha": "a" * 40, "images": {"backend": EARLIER, "web": "registry.example/web@sha256:" + "1" * 64}}
    monkeypatch.setattr(deployer, "manifest_tool", lambda: SimpleNamespace(
        validate_manifest=lambda *_args, **_kwargs: None, ManifestError=ValueError,
    ))
    # Boundary rejection must happen before inspecting/restarting any earlier image.
    monkeypatch.setattr(deployer, "verify_image", lambda *_args: pytest.fail("earlier image inspected"))
    with pytest.raises(deployer.DeploymentError, match="^f2d_rollback_image_incompatible$"):
        deployer.validate_prior_runtime(
            receipt, manifest, {"migration_set_identity": schema_identity}, {},
            lambda *_args, **_kwargs: pytest.fail("runtime accessed before boundary rejection"), attestation,
        )


def test_generation_read_is_bounded_parameterized_and_product_scope_is_target_only(deployer):
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(stdout=json.dumps(generation()))

    assert deployer.verify_f2d_generation({}, runner) == generation()
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert "--no-password" in argv
    assert "ON_ERROR_STOP=1" in argv
    assert "generation_id=cfc25d36-3bc7-4011-a465-d6460eaaf826" in argv
    sql = " ".join(kwargs["input_text"].split())
    assert "BEGIN READ ONLY;" in sql
    assert "SET LOCAL statement_timeout" in sql
    # This keeps opt1's retained READY product manifest outside the refusal.
    assert "WHERE derived_generation_id = :'generation_id'::uuid" in sql
    assert "product_code IN ('system_search', 'system_archetype')" in sql
    assert "JOIN v3_meta.derived_generation" in sql
    assert not any(word in sql.upper() for word in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE "))


@pytest.mark.parametrize("payload", ["", "[]", "null", "{}", '{"finder_products": []}'])
def test_unavailable_or_malformed_generation_refuses(deployer, payload):
    with pytest.raises(deployer.DeploymentError, match="(generation|finder_product)"):
        deployer.verify_f2d_generation({}, lambda *_args, **_kwargs: SimpleNamespace(stdout=payload))


def test_registered_migration_reader_matches_repository_manifest(deployer):
    assert deployer.registered_f2d_migrations() == registered_entries()


def promotion_fixture(deployer, monkeypatch, tmp_path, attestation, *, registered=True):
    spec = importlib.util.spec_from_file_location(
        "deployment_test_support", ROOT / "tests/test_v3_production_application_deployment.py"
    )
    assert spec and spec.loader
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    args, authority, receipt_dir, _snapshot = support._cancellation_promote_setup(monkeypatch, tmp_path, deployer)
    args.mode = "upgrade"
    schema = deployer.validate_schema_file(None, None)
    schema["migration_set_entries"] = complete_entries() if registered else registered_entries()
    candidate, checksum, candidate_bytes = deployer.validate_candidate(None, None, None)
    candidate["images"]["backend"] = MINIMUM
    attestation.update(
        source_sha=candidate["git_sha"], release_run_id=args.candidate_run_id,
        manifest_sha256=checksum, images=deepcopy(candidate["images"]),
        compatible_migration_sets=[schema["migration_set_identity"]],
    )
    args.candidate_attestation = tmp_path / "attestation.json"
    args.candidate_attestation.write_text(json.dumps(attestation))
    authority["accepted_release_schema_compatibility"] = deepcopy(attestation)
    prior_manifest = {
        "git_sha": "b" * 40,
        "images": {"backend": EARLIER, "web": "registry.example/web@sha256:" + "2" * 64},
    }
    prior_receipt = {
        "active_slot": "blue", "source_sha": prior_manifest["git_sha"],
        "release_run_id": "123", "migration_set_identity": schema["migration_set_identity"],
    }
    monkeypatch.setattr(deployer, "load_current", lambda _directory: (prior_receipt, prior_manifest, tmp_path / "prior.release.json"))
    monkeypatch.setattr(deployer, "manifest_tool", lambda: SimpleNamespace(
        validate_manifest=lambda *_args, **_kwargs: None, ManifestError=ValueError,
    ))
    if registered:
        monkeypatch.setattr(deployer, "registered_f2d_migrations", complete_entries)
    recovery = {
        "git_sha": "d" * 40,
        "images": {"backend": LATER, "web": "registry.example/web@sha256:" + "3" * 64},
    }
    body = json.dumps(recovery).encode()
    recovery_checksum = hashlib.sha256(body).hexdigest()
    path = receipt_dir / f"{recovery['git_sha']}-234-{recovery_checksum}.release.json"
    path.write_bytes(body)
    Path(str(path) + ".sha256").write_text(f"{recovery_checksum}  {path.name}\n")
    commands = []
    observed = generation()

    def runner(argv, **kwargs):
        commands.append((argv, kwargs.get("env", {}).copy()))
        output = ""
        if "psql" in argv and "--command" in argv:
            output = json.dumps({
                "database_name": deployer.DATABASE_NAME, "server_address": "local", "server_port": 5432,
                "transaction_read_only": "on", "migrations": [
                    {"filename": row["ledger_name"], "checksum_sha256": row["sha256"]}
                    for row in schema["migration_set_entries"]
                ],
            })
        elif "psql" in argv:
            output = json.dumps(observed)
        elif argv[:2] == ["docker", "inspect"]:
            if argv[3] == "{{.Config.Image}}":
                output = candidate["images"]["backend"]
            else:
                role = "backend" if argv[-1] == deployer.CONTAINERS["api-blue"] else "web"
                output = f"true\t{prior_manifest['images'][role]}\t{prior_manifest['git_sha']}"
        elif "/app/.venv/bin/python" in argv:
            output = json.dumps({"ranking_version": attestation["ranking_version"],
                                 "ranking_sha256": attestation["ranking_sha256"], "publication_gate": True})
        return SimpleNamespace(stdout=output, returncode=0)

    statuses = iter([503, 422, 503, 422])
    monkeypatch.setattr(deployer, "get", lambda _origin, path: (200, json.dumps(openapi_document()).encode(), "application/json")
                        if path == "/openapi.json" else (422, b"{}", "application/json")
                        if "galaxy_region=1" in path else (next(statuses), finder_unavailable_payload(), "application/json"))
    monkeypatch.setattr(deployer, "post", lambda _origin, _path, body: (422, b"{}", "application/json")
                        if "body_filters" in body else (next(statuses), finder_unavailable_payload(), "application/json"))
    return args, authority, receipt_dir, runner, commands, observed, recovery


def test_promote_refuses_unregistered_016_before_any_service_mutation(deployer, monkeypatch, tmp_path, attestation):
    args, authority, _directory, runner, commands, _observed, _recovery = promotion_fixture(
        deployer, monkeypatch, tmp_path, attestation, registered=False,
    )
    with pytest.raises(deployer.OperationFailed) as failed:
        deployer.promote(args, authority, runner)
    receipt = failed.value.receipt
    assert receipt["failures"] == ["required_migration_not_registered:016"]
    assert receipt["service_changes_performed"] is False
    assert not any("up" in argv or "pull" in argv or "stop" in argv for argv, _env in commands)


def test_promote_accepts_complete_fixture_and_persists_all_behavioural_statuses(deployer, monkeypatch, tmp_path, attestation):
    args, authority, directory, runner, _commands, observed, recovery = promotion_fixture(
        deployer, monkeypatch, tmp_path, attestation,
    )
    receipt = deployer.promote(args, authority, runner)
    assert receipt["status"] == "accepted"
    assert receipt["f2d_generation"] == observed
    assert [row["status"] for row in receipt["f2d_behavioural_probes"]] == [503, 422, 503, 422]
    assert receipt["accepted_release_schema_compatibility"] == attestation
    assert receipt["rollback_targets"] == [MINIMUM, LATER]
    assert receipt["incompatible_rollback_images"] == [EARLIER]
    assert receipt["rollback"]["images"] == recovery["images"]
    pointer = json.loads((directory / "current.json").read_text())
    persisted = json.loads((directory / pointer["receipt_file"]).read_text())
    assert persisted["f2d_behavioural_probes"] == receipt["f2d_behavioural_probes"]
    assert persisted["accepted_release_schema_compatibility"] == attestation


@pytest.mark.parametrize("product", ["system_search", "system_archetype"])
def test_promote_refuses_existing_target_product_before_mutation(deployer, monkeypatch, tmp_path, attestation, product):
    args, authority, _directory, runner, commands, observed, _recovery = promotion_fixture(
        deployer, monkeypatch, tmp_path, attestation,
    )
    observed["finder_products"] = [product]
    with pytest.raises(deployer.OperationFailed) as failed:
        deployer.promote(args, authority, runner)
    assert failed.value.receipt["failures"] == ["finder_products_already_registered_on_parallel_v1"]
    assert not any("up" in argv or "pull" in argv or "stop" in argv for argv, _env in commands)


def test_probe_mismatch_uses_compatible_recovery_instead_of_incompatible_prior(deployer, monkeypatch, tmp_path, attestation):
    args, authority, directory, runner, commands, _observed, recovery = promotion_fixture(
        deployer, monkeypatch, tmp_path, attestation,
    )
    statuses = iter([200, 422, 503, 422])
    monkeypatch.setattr(deployer, "get", lambda _origin, path: (200, json.dumps(openapi_document()).encode(), "application/json")
                        if path == "/openapi.json" else (422, b"{}", "application/json")
                        if "galaxy_region=1" in path else (next(statuses), finder_unavailable_payload(), "application/json"))
    monkeypatch.setattr(deployer, "post", lambda _origin, _path, body: (422, b"{}", "application/json")
                        if "body_filters" in body else (next(statuses), finder_unavailable_payload(), "application/json"))
    with pytest.raises(deployer.OperationFailed) as failed:
        deployer.promote(args, authority, runner)
    receipt = failed.value.receipt
    assert receipt["failures"] == ["behavioural_probe_pairs_failed"]
    assert [row["status"] for row in receipt["f2d_behavioural_probes"]] == [200, 422, 503, 422]
    assert receipt["rollback"] == {
        "attempted": True, "status": "verified", "kind": "recorded-schema-compatible-release",
        "source_sha": recovery["git_sha"], "schema_compatible": True,
    }
    restores = [(argv, env) for argv, env in commands if "up" in argv and "api-blue" in argv]
    assert len(restores) == 1
    assert restores[0][1]["V3_PRODUCTION_API_IMAGE"] == LATER
    assert all(env.get("V3_PRODUCTION_API_IMAGE") != EARLIER for _argv, env in commands)
    assert not (directory / "current.json").exists()
    assert receipt["accepted_release_pointer_reconciliation_required"] is True
    durable = json.loads((directory / receipt["durable_failure_receipt"]).read_text())
    assert durable["f2d_behavioural_probes"] == receipt["f2d_behavioural_probes"]


@pytest.mark.parametrize("mismatch", [None, "image", "ranking_version", "ranking_sha256", "malformed"])
def test_staged_image_contract_binds_digest_and_concrete_in_image_ranking(deployer, attestation, mismatch):
    calls = []

    def runner(argv, **_kwargs):
        calls.append(argv)
        if "inspect" in argv:
            return SimpleNamespace(stdout=EARLIER if mismatch == "image" else attestation["images"]["backend"])
        assert argv[0:2] == ["docker", "exec"]
        assert "PYTHONDONTWRITEBYTECODE=1" in argv
        assert "/app/.venv/bin/python" in argv
        assert argv[-1] == "-"
        assert "from edfinder_api.ranking.profile import RANKING_VERSION, ranking_sha256" in _kwargs["input_text"]
        if mismatch == "malformed":
            return SimpleNamespace(stdout="not-json")
        ranking = {"ranking_version": attestation["ranking_version"],
                   "ranking_sha256": attestation["ranking_sha256"], "publication_gate": True}
        if mismatch == "ranking_version":
            ranking["ranking_version"] = "another-profile"
        elif mismatch == "ranking_sha256":
            ranking["ranking_sha256"] = "0" * 64
        return SimpleNamespace(stdout=json.dumps(ranking))

    if mismatch is None:
        deployer.verify_f2d_image_contract("green", attestation, {}, runner)
    else:
        reason = "f2d_deployed_image_identity_mismatch" if mismatch == "image" else "f2d_deployed_ranking_identity"
        with pytest.raises(deployer.DeploymentError, match=reason):
            deployer.verify_f2d_image_contract("green", attestation, {}, runner)
    assert len(calls) == (1 if mismatch == "image" else 2)


def openapi_document():
    return {
        "paths": {
            "/api/archetypes/rankings": {"get": {"parameters": [
                {"name": "min_score", "in": "query", "schema": {"type": "integer", "enum": [60, 76, 88]}},
                {"name": "offset", "in": "query", "schema": {"type": "integer", "minimum": 0, "maximum": 9999}},
                {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 500}},
            ]}},
            "/api/local/search": {"post": {"requestBody": {"content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/LocalSearchRequest"}},
            }}}},
        },
        "components": {"schemas": {"LocalSearchRequest": {"type": "object", "properties": {
            "size": {"type": "integer", "minimum": 1, "maximum": 500},
            "from": {"type": "integer", "minimum": 0, "maximum": 2_147_483_647},
        }}}},
    }


def test_concrete_openapi_contract_accepts_local_request_schema_reference(deployer, monkeypatch):
    calls = []

    def get(origin, path):
        calls.append((origin, path))
        return 200, json.dumps(openapi_document()).encode(), "application/json"

    monkeypatch.setattr(deployer, "get", get)
    recorded = deployer.verify_f2d_openapi_contract("http://127.0.0.1:58081")
    assert calls == [("http://127.0.0.1:58081", "/openapi.json")]
    assert recorded == {"status": 200, "contracts": {
        "min_score": [60, 76, 88], "ranking.limit": {"minimum": 1, "maximum": 500},
        "ranking.offset": {"minimum": 0, "maximum": 9999},
        "search.size": {"minimum": 1, "maximum": 500},
        "search.from": {"minimum": 0, "maximum": 2_147_483_647},
    }}


@pytest.mark.parametrize(("field", "bound"), [
    ("ranking.limit", "minimum"), ("ranking.limit", "maximum"),
    ("ranking.offset", "minimum"), ("ranking.offset", "maximum"),
    ("search.size", "minimum"), ("search.size", "maximum"),
    ("search.from", "minimum"), ("search.from", "maximum"),
])
def test_openapi_refuses_each_missing_individual_bound(deployer, monkeypatch, field, bound):
    document = openapi_document()
    group, name = field.split(".")
    if group == "ranking":
        schema = next(item["schema"] for item in document["paths"]["/api/archetypes/rankings"]["get"]["parameters"] if item["name"] == name)
    else:
        schema = document["components"]["schemas"]["LocalSearchRequest"]["properties"][name]
    schema.pop(bound)
    monkeypatch.setattr(deployer, "get", lambda *_args: (200, json.dumps(document).encode(), "application/json"))
    with pytest.raises(deployer.DeploymentError, match="f2d_openapi_contract_invalid:" + field):
        deployer.verify_f2d_openapi_contract("http://127.0.0.1:58081")


@pytest.mark.parametrize("replacement", [{"type": "integer"}, {"type": "integer", "enum": [60, 61, 76, 88]}])
def test_openapi_refuses_unbounded_or_widened_floor(deployer, monkeypatch, replacement):
    document = openapi_document()
    document["paths"]["/api/archetypes/rankings"]["get"]["parameters"][0]["schema"] = replacement
    monkeypatch.setattr(deployer, "get", lambda *_args: (200, json.dumps(document).encode(), "application/json"))
    with pytest.raises(deployer.DeploymentError, match="f2d_openapi_contract_invalid:min_score"):
        deployer.verify_f2d_openapi_contract("http://127.0.0.1:58081")


@pytest.mark.parametrize("reference", ["https://example.invalid/schema", "#/components/schemas/Missing", "#/components/schemas/LocalSearchRequest"])
def test_openapi_refuses_external_missing_or_cyclic_reference(deployer, monkeypatch, reference):
    document = openapi_document()
    document["components"]["schemas"]["LocalSearchRequest"] = {"$ref": reference}
    monkeypatch.setattr(deployer, "get", lambda *_args: (200, json.dumps(document).encode(), "application/json"))
    with pytest.raises(deployer.DeploymentError, match="f2d_openapi_contract_invalid:reference"):
        deployer.verify_f2d_openapi_contract("http://127.0.0.1:58081")


@pytest.mark.parametrize(("status", "payload"), [(503, b"{}"), (200, b"not-json"), (200, b"[]"), (200, b"{}")])
def test_openapi_refuses_unavailable_or_invalid_document(deployer, monkeypatch, status, payload):
    monkeypatch.setattr(deployer, "get", lambda *_args: (status, payload, "application/json"))
    with pytest.raises(deployer.DeploymentError, match="f2d_openapi_contract_invalid:"):
        deployer.verify_f2d_openapi_contract("http://127.0.0.1:58081")


def finder_unavailable_payload():
    return json.dumps({"detail": "Finder ranking products are not available for the published generation "
                       "(system_archetype=MISSING, system_search=MISSING)."}).encode()


@pytest.mark.parametrize("bad_reason", [b"{}", b'{"detail":"database unavailable"}', b'not-json'])
def test_503_with_unverified_reason_fails_and_still_records_all_pairs(deployer, monkeypatch, bad_reason):
    calls = []

    def response(*_args):
        index = len(calls)
        calls.append(index)
        return PROBES[index][3], bad_reason, "application/json"

    monkeypatch.setattr(deployer, "get", response)
    monkeypatch.setattr(deployer, "post", response)
    outcomes = []
    with pytest.raises(deployer.DeploymentError, match="^behavioural_probe_pairs_failed$"):
        deployer.f2d_behavioural_probes("http://127.0.0.1:58080", outcomes)
    assert [row["status"] for row in outcomes] == [503, 422, 503, 422]
    assert [row["not_ready_reason_verified"] for row in outcomes] == [False, None, False, None]


def test_first_f2d_boundary_is_the_candidate_backend(deployer, attestation, legacy_attestation):
    attestation["images"]["backend"] = MINIMUM
    deployer.validate_f2d_boundary(attestation, legacy_attestation)
    attestation["minimum_schema_compatible_image"] = EARLIER
    with pytest.raises(deployer.DeploymentError, match="^f2d_minimum_schema_compatible_image_mismatch$"):
        deployer.validate_f2d_boundary(attestation, legacy_attestation)


@pytest.mark.parametrize("minimum", [MINIMUM, EARLIER, LATER])
def test_later_f2d_releases_preserve_original_boundary(deployer, attestation, minimum):
    previous = deepcopy(attestation)
    attestation["images"]["backend"] = LATER
    attestation["minimum_schema_compatible_image"] = minimum
    if minimum == MINIMUM:
        deployer.validate_f2d_boundary(attestation, previous)
    else:
        with pytest.raises(deployer.DeploymentError, match="^f2d_minimum_schema_compatible_image_mismatch$"):
            deployer.validate_f2d_boundary(attestation, previous)


@pytest.mark.parametrize("resolver", ["current", "old_ready_only"])
def test_in_image_program_exercises_real_publication_resolver_without_database(deployer, tmp_path, resolver):
    if resolver == "current":
        source_path = ROOT / "apps/api/src/local_search.py"
    else:
        source_path = tmp_path / "old_local_search.py"
        source_path.write_text(
            "async def _current_derived_generation(connection):\n"
            "    return await connection.fetchrow('SELECT fixture')\n"
        )
    program = deployer.F2D_IMAGE_CONTRACT_PROGRAM.replace("/app/local_search.py", str(source_path))
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=tmp_path,
        env={"PYTHONPATH": str(ROOT / "apps/api/src"), "PYTHONDONTWRITEBYTECODE": "1",
             "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", "")},
        capture_output=True, text=True, timeout=10, check=False,
    )
    if resolver == "current":
        assert result.returncode == 0, result.stderr
        identity = json.loads(result.stdout)
        assert identity["publication_gate"] is True
        assert identity["ranking_version"]
        assert len(identity["ranking_sha256"]) == 64
    else:
        assert result.returncode != 0
        assert "publication resolver accepted unavailable products" in result.stderr


@pytest.mark.parametrize("bad_index", [None, 0, 1])
def test_staging_rejects_picked_and_galaxywide_hard_filters(deployer, monkeypatch, bad_index):
    calls = []

    def response(method, path, body):
        index = len(calls)
        calls.append((method, path, body))
        return 503 if index == bad_index else 422, b"{}", "application/json"

    monkeypatch.setattr(deployer, "get", lambda _origin, path: response("GET", path, None))
    monkeypatch.setattr(deployer, "post", lambda _origin, path, body: response("POST", path, body))
    if bad_index is None:
        recorded = deployer.verify_f2d_rejections("http://127.0.0.1:58081")
        assert [row["status"] for row in recorded] == [422, 422]
        assert calls == [
            ("GET", "/api/archetypes/rankings?archetype=paradise&galaxy_region=1", None),
            ("POST", "/api/local/search", {"galaxy_wide": True, "sort_by": "development",
                                           "body_filters": {"elw_count": {"min": 1}}, "size": 1}),
        ]
    else:
        with pytest.raises(deployer.DeploymentError, match="^f2d_hard_filter_rejection_failed$"):
            deployer.verify_f2d_rejections("http://127.0.0.1:58081")
