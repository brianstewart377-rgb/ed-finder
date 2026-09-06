"""Regression for Python startup injection through the shared operator home."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/operator/actions/v3-app-live-checkpoint-preflight.sh"


def test_both_launcher_interpreter_calls_disable_user_site_and_environment():
    source = LAUNCHER.read_text()
    assert '"$PYTHON_BIN" -I -S -c' in source
    assert 'exec "$PYTHON_BIN" -I -S "$SCRIPT_DIR/../v3_checkpoint_deploy.py"' in source


def test_poisoned_home_pythonpath_and_workdir_never_execute(tmp_path):
    home = tmp_path / "home"
    poison = tmp_path / "poison"
    poison.mkdir()
    site = home / ".local/lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    site.mkdir(parents=True)
    marker = tmp_path / "injected"
    payload = f"from pathlib import Path; Path({str(marker)!r}).write_text('injected')\n"
    (site / "injection.pth").write_text("import pathlib; " + payload.split("; ", 1)[1])
    (site / "sitecustomize.py").write_text(payload)
    (poison / "sitecustomize.py").write_text(payload)
    # Execute the real launcher against an inert deployer, not a host operation.
    stage = tmp_path / "sealed/scripts/operator"
    (stage / "actions").mkdir(parents=True)
    launcher = stage / "actions" / LAUNCHER.name
    launcher.write_text(LAUNCHER.read_text())
    (stage / "v3_checkpoint_deploy.py").write_text(
        "import json,sys; print(json.dumps({'isolated':sys.flags.isolated,'no_site':sys.flags.no_site}))\n"
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    # Only the version probe is stubbed, so this isolation test also runs in an
    # editor without the repository's exact interpreter. Runtime CI is separate.
    shim = binary / "python3.14"
    shim.write_text(
        '#!/bin/bash\n'
        'if [ "$1" = -I ] && [ "$2" = -S ] && [ "$3" = -c ]; then exit 0; fi\n'
        + 'exec ' + shlex.quote(sys.executable) + ' "$@"\n'
    )
    shim.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PYTHONPATH": str(poison),
           "PYTHONUSERBASE": str(home / ".local"),
           "PATH": str(binary) + os.pathsep + os.environ["PATH"]}
    result = subprocess.run(["/bin/bash", str(launcher)], cwd=poison, env=env,
                            text=True, capture_output=True, check=False, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"isolated": 1, "no_site": 1}
    assert not marker.exists()
