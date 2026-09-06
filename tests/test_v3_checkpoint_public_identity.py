"""Stale public frontend HTML must never be accepted by a current API."""
import importlib.util
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def load(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts/operator"))
    path = ROOT / "scripts/operator/v3_checkpoint_public_smoke.py"
    spec = importlib.util.spec_from_file_location("checkpoint_public_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def html(identity=SHA):
    return f'<html><head><meta name="edfinder-build-sha" content="{identity}"></head><body>V3</body></html>'.encode()


@pytest.mark.parametrize("body", [html("b" * 40), b"<html><head></head></html>",
    b"<html><head><!-- " + html() + b" --></head></html>",
    html().replace(b"</head>", b'<meta name="edfinder-build-sha" content="' + SHA.encode() + b'"></head>'),
    html().replace(b"</head>", b'<meta name="edfinder-build-sha" content="old"></head>'),
    html().replace(b'<meta name=', b'<meta content="old" name='), b"\xff"])
def test_rejects_stale_missing_commented_duplicate_or_malformed_identity(monkeypatch, body):
    module = load(monkeypatch)
    with pytest.raises(module.DeploymentError):
        module.verify_web_identity(body, "text/html", SHA)


@pytest.mark.parametrize("stale_path", [None, "/", "/200.html"])
def test_current_api_cannot_mask_stale_root_or_fallback(monkeypatch, stale_path):
    module = load(monkeypatch)
    monkeypatch.setattr(module, "wait_for_origin_ready", lambda *a: None)
    monkeypatch.setattr(module, "smoke_origin", lambda *a: {"/api/health": {"status": 200}})
    observed = []
    def get(origin, path):
        observed.append((origin, path))
        return 200, html("b" * 40 if path == stale_path else SHA), "text/html"
    monkeypatch.setattr(module, "get_origin", get)
    if stale_path:
        with pytest.raises(module.DeploymentError, match="web build identity mismatch"):
            module.verify_public_checkpoint(SHA)
    else:
        result = module.verify_public_checkpoint(SHA)
        assert result["status"] == "accepted"
        assert result["checks"]["/"]["web_build_sha"] == SHA
        assert result["checks"]["/200.html"]["web_build_sha"] == SHA
        assert observed == [("http://vmi3542235.contaboserver.net", "/"),
                            ("http://vmi3542235.contaboserver.net", "/200.html")]


def test_stopped_public_identity_writes_failure_receipt(monkeypatch, tmp_path):
    module = load(monkeypatch)
    def fail(sha):
        raise module.DeploymentError("public web build identity mismatch")
    monkeypatch.setattr(module, "verify_public_checkpoint", fail)
    monkeypatch.setattr(sys, "argv", ["smoke", "--receipt", str(tmp_path / "receipt")])
    assert module.main() == 78
    assert '"status": "stopped"' in (tmp_path / "receipt").read_text()


def test_real_dockerfile_stamp_binds_both_html_files(monkeypatch, tmp_path):
    # Execute the actual build-time command with Node, without building containers.
    module = load(monkeypatch)
    dockerfile = (ROOT / "apps/web/Dockerfile").read_text()
    lines = [line for line in dockerfile.splitlines() if line.startswith('RUN BUILD_SHA=')]
    assert len(lines) == 1
    words = shlex.split(lines[0])
    script = words[words.index("-e") + 1]
    build = tmp_path / "build"; build.mkdir()
    for page in ("index.html", "200.html"):
        (build / page).write_text("<html><head></head><body>fixture</body></html>")
    import os
    result = subprocess.run(["node", "-e", script], cwd=tmp_path,
                            env={**os.environ, "BUILD_SHA": SHA}, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    for page in ("index.html", "200.html"):
        module.verify_web_identity((build / page).read_bytes(), "text/html", SHA)
