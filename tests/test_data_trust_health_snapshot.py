import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCRIPT = ROOT / "scripts" / "checks" / "data_trust_health_snapshot.py"
TELEMETRY_SCRIPT = ROOT / "scripts" / "checks" / "telemetry_hot_log_snapshot.py"


def test_data_trust_snapshot_uses_psycopg3_read_only_connection():
    source = SNAPSHOT_SCRIPT.read_text(encoding="utf-8")

    assert "import psycopg\n" in source
    assert "psycopg.connect(" in source
    assert "psycopg2" not in source
    assert "-c default_transaction_read_only=on" in source


def test_telemetry_snapshot_uses_psycopg3_read_only_connection():
    source = TELEMETRY_SCRIPT.read_text(encoding="utf-8")

    assert "import psycopg\n" in source
    assert "psycopg.connect(" in source
    assert "psycopg2" not in source
    assert "-c default_transaction_read_only=on" in source


def test_data_trust_health_snapshot_requires_database_url():
    result = subprocess.run(
        [sys.executable, str(SNAPSHOT_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={key: value for key, value in os.environ.items() if key != "DATABASE_URL"},
    )

    assert result.returncode == 2
    assert "missing --database-url or DATABASE_URL" in result.stderr
