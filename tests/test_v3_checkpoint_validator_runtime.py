"""The selected Actions interpreter may live outside system PATH."""
import os
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("validator_result", [0, 78])
def test_toolcache_validator_survives_system_path_reset(tmp_path, validator_result):
    scope = runpy.run_path(str(ROOT / "tests/test_v3_checkpoint_local_transport.py"))
    run_local = scope["run_local"]
    # Replace only the Python stub with an executable outside the fixed PATH.
    run_local.__globals__["STUBS"] = scope["STUBS"].replace(
        'python3.14() { cat >/dev/null; return "${TEST_PYTHON_RC:-0}"; }', ""
    )
    toolcache = tmp_path / "toolcache" / "bin"
    toolcache.mkdir(parents=True)
    validator = toolcache / "python3.14"
    validator.write_text(
        '#!/bin/bash\ncat >/dev/null\nprintf "selected\n" > "$TEST_ROOT/validator-used"\n'
        + f"exit {validator_result}\n"
    )
    validator.chmod(0o700)
    result = run_local(tmp_path, ["provision"], PATH=str(toolcache) + os.pathsep + os.environ["PATH"])
    assert result.returncode == validator_result, result.stderr
    assert (tmp_path / "validator-used").read_text().strip() == "selected"
    calls = tmp_path / "sudo-calls"
    if validator_result:
        assert not calls.exists()
    else:
        assert "PATH=/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" in calls.read_text()
        assert str(toolcache) not in calls.read_text()
