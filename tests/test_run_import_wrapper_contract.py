from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_import_supports_repo_root_helper_scripts_and_unbuffered_output():
    source = (ROOT / "scripts" / "run_import.sh").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "./scripts/run_import.sh scripts/repair_body_contract.py --json" in source
    assert './scripts/run_import.sh scripts/reconcile_no_body_ratings.py --apply --batch-size 5000' in source
    assert 'elif [[ "$1" == scripts/*.py ]]; then' in source
    assert 'SCRIPT="/opt/ed-finder/$1"' in source
    assert 'PYTHONUNBUFFERED=1' in source
    assert 'docker compose --profile import run -d --name "$JOB_NAME" \\' in source
    assert 'docker logs -f "$JOB_NAME"' in source
    assert 'EXIT_CODE="$(docker wait "$JOB_NAME")"' in source
    assert 'cleanup_job' in source
    assert '-u "$SCRIPT" "${ARGS[@]}"' in source
    assert '- ./scripts:/opt/ed-finder/scripts:ro' in compose
    assert 'PYTHONUNBUFFERED: "1"' in compose
