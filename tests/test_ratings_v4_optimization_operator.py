from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/ratings-v4-production-optimize.yml'
ACTION = ROOT / 'scripts/operator/actions/ratings-v4-optimize.sh'
RUNNER = ROOT / 'scripts/ratings_v4/run_generation.py'


def test_parallel_runner_is_bounded_and_parent_owned_db():
    runner = RUNNER.read_text(encoding='utf-8')
    assert 'ProcessPoolExecutor' in runner
    assert "multiprocessing.get_context('spawn')" in runner
    assert 'MAX_ENCODER_WORKERS = 16' in runner
    assert 'if len(pending) >= workers:' in runner
    assert 'executor.submit(' in runner
    assert 'encode_chunk, identifier, ordinal, canonical' in runner
    assert '_write_encoded_chunk(' in runner
    assert "parser.add_argument('--workers'" in runner
    assert 'psycopg.connect' in runner
    assert 'psycopg.connect' not in runner[runner.index('def _drain_oldest'):runner.index('def build_generation')]


def test_optimization_request_is_data_only_and_uses_trusted_main():
    workflow = WORKFLOW.read_text(encoding='utf-8')
    assert 'ratings-v4-generation-optimize' in workflow
    assert '.github/ratings-v4-optimize-requests/*.json' in workflow
    assert 'data != {"operation": "ratings-v4-generation-optimize"}' in workflow
    assert 'ref: main' in workflow
    assert 'trusted-main/scripts/operator/actions/ratings-v4-optimize.sh' in workflow
    assert 'psycopg[binary]==3.3.4' in workflow
    assert 'ijson==3.5.1' in workflow
    assert '--only-binary=:all:' in workflow


def test_optimized_worker_proves_progress_before_reversible_cutover():
    action = ACTION.read_text(encoding='utf-8')
    assert 'new_generation_key="ratings_v4_prod_p${sequence}_opt1"' in action
    assert 'new_worker="edfinder-ratings-v4-prod-p${sequence}-opt1"' in action
    assert 'TARGET_CPUS="16"' in action
    assert 'TARGET_MEMORY="64g"' in action
    assert 'TARGET_WORKERS="8"' in action
    assert 'TARGET_CHUNK_SIZE="1000"' in action
    assert '--chunk-size 1000' in action
    assert '--workers 8' in action
    assert '--memory-swap "$TARGET_MEMORY"' in action
    assert 'MIN_PROOF_CHUNKS="2"' in action
    assert action.index('proof_chunks=0') < action.index('docker stop --time 30 "$old_worker"')
    assert 'old_worker_retained=true' in action
    assert 'old_generation_deleted=false' in action
    assert 'publication_performed=false' in action
    assert 'migrations_performed=false' in action
    assert 'canonical_writes_performed=false' in action
    assert 'publish_derived_generation(' not in action
    assert 'docker rm "$old_worker"' not in action
    assert 'DROP ' not in action
    assert 'TRUNCATE ' not in action
