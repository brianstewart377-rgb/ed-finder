from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/operator/actions/v3-live-checkpoint-provision-v2.sh'
WORKFLOW = ROOT / '.github/workflows/v3-live-checkpoint-ops.yml'


def test_provisioner_is_non_production_and_read_only_for_app():
    text = SCRIPT.read_text(encoding='utf-8')
    assert 'vmi3542235' in text
    assert 'edfinder_checkpoint_ro' in text
    assert 'default_transaction_read_only = on' in text
    assert 'sql/seed_preview.sql' not in text  # seed is delegated to canonical seed_check.sh
    assert 'scripts/seed_check.sh' in text
    assert 'redis-server' not in text.lower()
    assert 'nats' not in text.lower()
    assert 'nb79a3d.mevnode.com' not in text
    assert 'ed-finder-prod' not in text


def test_ops_workflow_reuses_checkpoint_secret_boundary_only():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'environment: v3-live-checkpoint' in text
    assert 'v3-checkpoint-ops-requests' in text
    assert 'sudo -n bash scripts/operator/actions/v3-live-checkpoint-provision-v2.sh' in text
    secret_names = set(re.findall(r'secrets\.([A-Z0-9_]+)', text))
    assert secret_names == {
        'V3_LIVE_CHECKPOINT_SSH_KEY',
        'V3_LIVE_CHECKPOINT_HOST',
        'V3_LIVE_CHECKPOINT_PORT',
        'V3_LIVE_CHECKPOINT_USER',
        'V3_LIVE_CHECKPOINT_SSH_KNOWN_HOSTS',
    }
    assert 'ED_NEW_OPERATOR_' not in text
