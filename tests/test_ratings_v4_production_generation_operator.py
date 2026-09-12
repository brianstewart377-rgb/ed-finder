from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
ACTION = ROOT / "scripts/operator/actions/ratings-v4-generation.sh"
ACCELERATE_WORKFLOW = ROOT / ".github/workflows/ratings-v4-production-accelerate.yml"
ACCELERATE_ACTION = ROOT / "scripts/operator/actions/ratings-v4-accelerate.sh"


def test_generation_request_uses_trusted_main_and_is_allowlisted():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "ratings-v4-generation-start" in workflow
    assert "ratings-v4-generation-status" in workflow
    assert "ref: main" in workflow
    assert "trusted-main/scripts/operator/actions/ratings-v4-generation.sh" in workflow
    assert ".github/ed-new-ops-requests/*.json" in workflow
    assert 'extra=set(d)-{"operation"}' in workflow


def test_generation_worker_is_bounded_and_cannot_publish_or_migrate():
    action = ACTION.read_text(encoding="utf-8")
    assert "--cpus 2" in action
    assert "--memory 12g" in action
    assert "--pids-limit 512" in action
    assert "--restart no" in action
    assert "dst=/work,readonly" in action
    assert "dst=/source/galaxy.json.gz,readonly" in action
    assert "--chunk-size 500" in action
    assert "publication_performed=false" in action
    assert "canonical_writes_performed=false" in action
    assert "publish_derived_generation(" not in action
    assert "v3_production_migrate.py" not in action
    assert "DROP " not in action
    assert "TRUNCATE " not in action


def test_generation_dependencies_are_offline_and_pinned():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    action = ACTION.read_text(encoding="utf-8")
    for requirement in ("psycopg[binary]==3.3.4", "ijson==3.5.1"):
        assert requirement in workflow
        assert requirement in action
    assert "--only-binary=:all:" in workflow
    assert "--no-index" in action
    assert ".ratings-v4-wheelhouse" in workflow
    assert ".ratings-v4-wheelhouse" in action


def test_generation_reuses_live_database_secret_without_printing_it():
    action = ACTION.read_text(encoding="utf-8")
    assert "DATABASE_URL=" in action
    assert "RATINGS_V4_CANONICAL_DATABASE_URL=%s" in action
    assert "RATINGS_V4_DERIVED_DATABASE_URL=%s" in action
    assert 'printf \'%s\' "$value"' in action
    assert 'printf \'%s\\n\' "$dsn"' not in action


def test_acceleration_is_in_place_and_data_only():
    workflow = ACCELERATE_WORKFLOW.read_text(encoding="utf-8")
    action = ACCELERATE_ACTION.read_text(encoding="utf-8")
    assert "ratings-v4-generation-accelerate" in workflow
    assert "ref: main" in workflow
    assert ".github/ratings-v4-ops-requests/*.json" in workflow
    assert "trusted-main/scripts/operator/actions/ratings-v4-accelerate.sh" in workflow
    assert 'TARGET_CPUS="16"' in action
    assert 'TARGET_MEMORY="64g"' in action
    assert 'docker update \\' in action
    assert "--cpus \"$TARGET_CPUS\"" in action
    assert "--memory \"$TARGET_MEMORY\"" in action
    assert "worker_restarted=false" in action
    assert "publication_performed=false" in action
    assert "migrations_performed=false" in action
    assert "canonical_writes_performed=false" in action
    assert "docker restart" not in action
    assert "docker stop" not in action
    assert "docker rm" not in action
    assert "publish_derived_generation(" not in action
