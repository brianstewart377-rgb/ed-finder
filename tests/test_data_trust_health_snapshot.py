import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCRIPT = ROOT / "scripts" / "checks" / "data_trust_health_snapshot.py"


def test_data_trust_health_snapshot_requires_database_url():
    result = subprocess.run(
        [sys.executable, str(SNAPSHOT_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "missing --database-url or DATABASE_URL" in result.stderr
