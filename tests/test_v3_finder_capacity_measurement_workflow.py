"""Contract tests for the disposable F2d capacity-measurement workflow."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "v3-finder-capacity-measurement.yml"
RATINGS_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ratings-v4-freeze.yml"
UPLOAD_ARTIFACT = (
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
)
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
COMPLETE_RECEIPT = "docs/operations/evidence/f2d/complete-read-receipt.json"


def _load(path: Path) -> dict:
    # BaseLoader preserves GitHub Actions' bare ``on`` key instead of applying
    # PyYAML's YAML-1.1 boolean coercion. Scalar value comparisons below are
    # intentionally strings for the same reason.
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _workflow() -> tuple[dict, str]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    return _load(WORKFLOW_PATH), text


def test_dispatch_only_inputs_and_disposable_postgres_18_service() -> None:
    workflow, _ = _workflow()
    assert set(workflow["on"]) == {"workflow_dispatch"}
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"attested_f2d_operator_code_sha256", "rows"}
    assert inputs["attested_f2d_operator_code_sha256"]["required"] == "true"
    assert inputs["attested_f2d_operator_code_sha256"]["type"] == "string"
    assert inputs["rows"]["default"] == "200000"
    assert inputs["rows"]["type"] == "string"

    job = workflow["jobs"]["measure"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == "60"
    assert workflow["concurrency"]["group"] == "v3-finder-capacity-measurement"
    assert workflow["permissions"] == {"contents": "read"}
    assert job["services"]["postgres"] == _load(RATINGS_WORKFLOW_PATH)["jobs"]["verify"][
        "services"
    ]["postgres"]


def test_identity_precedes_complete_receipt_and_all_measurements() -> None:
    workflow, text = _workflow()
    steps = workflow["jobs"]["measure"]["steps"]
    runs = [step.get("run", "") for step in steps]
    joined_runs = "\n".join(runs)

    identity_index = next(
        index
        for index, run in enumerate(runs)
        if "f2d_operator_identity.sh verify" in run
    )
    assert "f2d_operator_identity.py verify" in runs[identity_index]
    complete_index = next(
        index for index, run in enumerate(runs) if "Require the committed" in run
        or (COMPLETE_RECEIPT in run and "[[ ! -f" in run)
    )
    script_indices = [
        next(index for index, run in enumerate(runs) if script in run)
        for script in (
            "scripts/dev/convert_calibration_histogram.py",
            "scripts/dev/measure_wide_archetype_footprint.py",
            "scripts/dev/measure_search_footprint.py",
        )
    ]
    assert identity_index < complete_index < script_indices[0]
    assert script_indices == sorted(script_indices)
    assert "f2d_operator_identity.sh verify . \"$ATTESTED\"" in joined_runs
    assert "f2d_operator_identity.py verify . \"$ATTESTED\"" in joined_runs
    assert "^[0-9a-f]{64}$" in joined_runs
    assert COMPLETE_RECEIPT in text


def test_actions_and_dependency_install_match_the_postgresql_18_reference_lane() -> None:
    workflow, _ = _workflow()
    steps = workflow["jobs"]["measure"]["steps"]
    assert steps[0]["uses"] == CHECKOUT
    assert steps[1]["uses"] == SETUP_PYTHON
    assert steps[1]["with"]["python-version"] == "3.14"
    install = next(step for step in steps if step.get("name") == "Install measurement dependencies")
    assert install["run"] == "python -m pip install -r apps/api/requirements.txt"


def test_evidence_verification_and_artifact_contract() -> None:
    workflow, text = _workflow()
    steps = workflow["jobs"]["measure"]["steps"]
    verification = next(step for step in steps if step.get("name") == "Verify and summarize the capacity evidence")
    verification_run = verification["run"]
    assert "load_sealed(COMPLETE_RECEIPT)" in verification_run
    assert "load_sealed(archetype_path)" in verification_run
    assert "load_sealed(search_path)" in verification_run
    assert "validate_archetype_footprint_receipt(archetype)" in verification_run
    assert "validate_search_footprint_receipt(search)" in verification_run
    assert 'receipt.get("f2d_operator_code_sha256") != attested' in verification_run
    assert 'archetype.get("fractions_sha256") != fractions.get("fractions_sha256")' in verification_run
    assert 'archetype.get("migration_011_sha256") != migration_011_sha256' in verification_run
    assert "GITHUB_STEP_SUMMARY" in verification_run
    assert verification_run.count("content_sha256=") >= 4

    upload = next(step for step in steps if step.get("uses") == UPLOAD_ARTIFACT)
    assert upload["with"]["name"] == "v3-finder-capacity-measurement"
    assert upload["with"]["retention-days"] == "90"
    assert upload["with"]["if-no-files-found"] == "error"
    paths = upload["with"]["path"].splitlines()
    assert paths == [
        COMPLETE_RECEIPT,
        "${{ runner.temp }}/calibration-fractions.json",
        "${{ runner.temp }}/archetype-footprint-receipt.json",
        "${{ runner.temp }}/search-footprint-receipt.json",
    ]
    assert "docs/operations/evidence/f2d/" in text


def test_workflow_has_no_production_or_operator_credentials() -> None:
    _, text = _workflow()
    lowered = text.lower()
    assert "${{ secrets." not in lowered
    assert "ed_new_operator_" not in lowered
    assert "nb79a3d.mevnode.com" not in lowered
    assert "ed-finder-prod" not in lowered


def test_measurement_steps_receive_the_attested_service_container_address() -> None:
    """A non-loopback disposable server is accepted only at the address the workflow attests."""
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/v3-finder-capacity-measurement.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["measure"]["steps"]
    attest = next(step for step in steps if step.get("id") == "disposable")
    assert attest["env"]["SERVICE_ID"] == "${{ job.services.postgres.id }}"
    assert "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'" in attest["run"]
    for name in ("Measure the eligible Archetype footprint", "Measure the Search footprint"):
        step = next(step for step in steps if step.get("name") == name)
        assert step["env"]["EDFINDER_DISPOSABLE_SERVER_ADDRESS"] == "${{ steps.disposable.outputs.address }}"
        assert steps.index(attest) < steps.index(step)
