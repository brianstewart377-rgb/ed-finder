"""Contracts for the backup heartbeat (dead-man's switch) and its installer."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HEARTBEAT = ROOT / "deploy/v3-production/backup/backup-heartbeat.sh"
SERVICE = ROOT / "deploy/v3-production/backup/edfinder-v3-backup-heartbeat.service"
TIMER = ROOT / "deploy/v3-production/backup/edfinder-v3-backup-heartbeat.timer"
INSTALLER = ROOT / "scripts/operator/actions/v3-backup-heartbeat-install.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
URL = "https://hc-ping.com/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
NOW = 1_800_000_000


def namespace(path: Path) -> dict:
    source = path.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    source = source.rsplit("\nraise SystemExit(main())", 1)[0]
    ns: dict = {}
    exec(compile(source, str(path), "exec"), ns)
    return ns


def info(*backups, code=0, message="ok"):
    return [{"name": "edfinder_v3", "status": {"code": code, "message": message}, "backup": list(backups)}]


def backup(kind, hours_ago, **extra):
    stop = int(NOW - hours_ago * 3600)
    return {"type": kind, "timestamp": {"start": stop - 600, "stop": stop}, **extra}


@pytest.fixture
def hb():
    ns = namespace(HEARTBEAT)
    # Production requires root; CI runs the suite as an ordinary user.
    ns["URL_FILE_OWNER"] = os.geteuid()
    return ns


# --- verdict -----------------------------------------------------------------

def test_recent_successful_backup_is_healthy_and_newest_wins(hb):
    healthy, summary = hb["judge"](info(backup("full", 50), backup("diff", 3)), NOW)
    assert healthy
    assert summary.startswith("ok type=diff ")
    assert "age_hours=3.0 max_hours=36" in summary


@pytest.mark.parametrize(("value", "reason"), [
    (info(backup("full", 37)), "newest_backup_too_old"),
    (info(), "no_successful_backup_recorded"),
    (info(backup("diff", 1, error=True)), "no_successful_backup_recorded"),
    (info(backup("diff", 1), code=2, message="no valid backups"), "stanza_status_not_ok code=2"),
    (info(backup("diff", 1), code=0, message="other"), "stanza_status_not_ok code=0"),
    (info(backup("diff", -2)), "newest_backup_in_future"),
    ([], "pgbackrest_info_unexpected_shape"),
    (info(backup("diff", 1)) * 2, "pgbackrest_info_unexpected_shape"),
    ({"status": "ok"}, "pgbackrest_info_unexpected_shape"),
    (info({"type": "diff", "timestamp": {"stop": "yesterday"}}), "no_successful_backup_recorded"),
    (info({"type": "archive", "timestamp": {"stop": NOW}}), "no_successful_backup_recorded"),
])
def test_anything_unproven_is_unhealthy(hb, value, reason):
    healthy, summary = hb["judge"](value, NOW)
    assert healthy is False
    assert summary.startswith(reason)


def test_an_errored_newer_backup_does_not_mask_an_old_good_one(hb):
    healthy, summary = hb["judge"](info(backup("full", 40), backup("diff", 1, error=True)), NOW)
    assert healthy is False and summary.startswith("newest_backup_too_old type=full")


def test_threshold_boundary(hb):
    assert hb["judge"](info(backup("diff", 36)), NOW)[0] is True
    assert hb["judge"](info(backup("diff", 36.01)), NOW)[0] is False


# --- configuration ------------------------------------------------------------

def private_url_file(tmp_path, content=URL + "\n", mode=0o600):
    path = tmp_path / "backup-heartbeat.url"
    path.write_text(content)
    path.chmod(mode)
    return path


def test_url_file_must_be_private_root_and_well_formed(hb, tmp_path):
    assert hb["read_url"](private_url_file(tmp_path)) == URL
    with pytest.raises(hb["ConfigError"], match="heartbeat_url_file_missing"):
        hb["read_url"](tmp_path / "absent")
    with pytest.raises(hb["ConfigError"], match="not_private_root_file"):
        hb["read_url"](private_url_file(tmp_path, mode=0o644))
    for bad in ("http://hc-ping.com/abc", "https://user:pw@hc-ping.com/abc", URL + "?x=1", URL + "\n" + URL, ""):
        with pytest.raises(hb["ConfigError"], match="heartbeat_url_invalid"):
            hb["read_url"](private_url_file(tmp_path, content=bad))


@pytest.mark.skipif(os.geteuid() != 0, reason="needs root to give the file another owner")
def test_url_file_owned_by_another_user_is_refused(hb, tmp_path):
    path = private_url_file(tmp_path)
    os.chown(path, 65534, 65534)
    with pytest.raises(hb["ConfigError"], match="not_private_root_file"):
        hb["read_url"](path)


def test_url_file_symlink_is_refused(hb, tmp_path):
    target = private_url_file(tmp_path)
    link = tmp_path / "link.url"
    link.symlink_to(target)
    with pytest.raises(hb["ConfigError"], match="not_private_root_file"):
        hb["read_url"](link)


# --- the run ------------------------------------------------------------------

def run_main(hb, capsys, *, url=URL, value=None, info_error=None, ping_error=None):
    pings = []

    def read_url():
        if url is None:
            raise hb["ConfigError"]("heartbeat_url_file_missing")
        return url

    def read_info():
        if info_error is not None:
            raise info_error
        return value

    def ping(target, body):
        pings.append((target, body))
        if ping_error:
            raise RuntimeError("URLError")

    hb["read_url"] = read_url
    hb["read_info"] = read_info
    hb["ping"] = ping
    hb["time"] = SimpleNamespace(time=lambda: NOW, gmtime=__import__("time").gmtime,
                                 strftime=__import__("time").strftime, sleep=lambda _s: None)
    code = hb["main"]()
    out = capsys.readouterr().out
    assert url is None or url not in out  # the URL is a credential and never printed
    return code, pings, out


def test_healthy_run_sends_the_success_ping(hb, capsys):
    code, pings, out = run_main(hb, capsys, value=info(backup("diff", 2)))
    assert code == 0
    assert [target for target, _ in pings] == [URL]
    assert pings[0][1].startswith("ED-Finder V3 backup heartbeat: ok type=diff")
    assert "healthy" in out and "success ping sent" in out


@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"value": info(backup("full", 48))}, "newest_backup_too_old"),
    ({"info_error": ValueError("pgbackrest_info_failed")}, "pgbackrest_info_failed"),
    ({"info_error": json.JSONDecodeError("bad", "x", 0)}, "pgbackrest_info_unreadable"),
    ({"info_error": subprocess.TimeoutExpired("docker", 180)}, "pgbackrest_info_unreadable"),
    ({"info_error": OSError("docker missing")}, "pgbackrest_info_unreadable"),
])
def test_unhealthy_or_unreadable_sends_the_fail_ping(hb, capsys, kwargs, reason):
    code, pings, _out = run_main(hb, capsys, **kwargs)
    assert code == 1
    assert [target for target, _ in pings] == [URL + "/fail"]
    assert reason in pings[0][1]


def test_missing_configuration_sends_nothing_so_silence_alerts(hb, capsys):
    code, pings, out = run_main(hb, capsys, url=None, value=info(backup("diff", 1)))
    assert code == 78 and pings == []
    assert "heartbeat_url_file_missing" in out


def test_ping_failure_is_reported_not_hidden(hb, capsys):
    code, pings, out = run_main(hb, capsys, value=info(backup("diff", 1)), ping_error=True)
    assert code == 75 and len(pings) == 1
    assert "ping failed" in out


def test_info_reads_the_pinned_container_and_stanza(hb, monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(info(backup("diff", 1))))

    monkeypatch.setenv("DOCKER_HOST", "tcp://elsewhere:2375")
    hb["subprocess"] = SimpleNamespace(run=fake_run, TimeoutExpired=subprocess.TimeoutExpired)
    assert hb["read_info"]()[0]["status"]["code"] == 0
    argv, kwargs = calls[0]
    assert argv == ["docker", "--host", "unix:///var/run/docker.sock", "exec", "-u", "postgres",
                    "edfinder-v3-phase4c-full-20260827_r5-postgres", "pgbackrest", "--stanza=edfinder_v3",
                    "--log-level-console=off", "--output=json", "info"]
    assert "DOCKER_HOST" not in kwargs["env"]

    hb["subprocess"] = SimpleNamespace(run=lambda *_a, **_k: SimpleNamespace(returncode=1, stdout=""),
                                       TimeoutExpired=subprocess.TimeoutExpired)
    with pytest.raises(ValueError, match="pgbackrest_info_failed"):
        hb["read_info"]()


def test_ping_retries_then_reports(hb, monkeypatch):
    attempts = []

    def urlopen(request, timeout):
        attempts.append((request.full_url, request.get_method(), timeout))
        raise OSError("connection refused")

    monkeypatch.setattr(hb["urllib"].request, "urlopen", urlopen)
    hb["time"] = SimpleNamespace(sleep=lambda _s: None)
    with pytest.raises(RuntimeError, match="OSError"):
        hb["ping"](URL, "body")
    assert attempts == [(URL, "POST", 10)] * 3


def test_heartbeat_script_runs_under_isolated_python314_and_parses():
    text = HEARTBEAT.read_text()
    assert "exec python3.14 -I -S - \"$@\" <<'PY'" in text
    subprocess.run(["bash", "-n", str(HEARTBEAT)], check=True)
    subprocess.run(["bash", "-n", str(INSTALLER)], check=True)


def test_heartbeat_without_configuration_exits_78_before_touching_docker(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    marker = tmp_path / "docker-called"
    docker = binary / "docker"
    docker.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    docker.chmod(0o755)
    script = tmp_path / "heartbeat.sh"
    script.write_text(HEARTBEAT.read_text().replace(
        "/etc/ed-finder/v3-production/backup-heartbeat.url", str(tmp_path / "absent.url")))
    python = subprocess.run(["bash", "-c", "command -v python3.14"], capture_output=True, text=True)
    if python.returncode:
        pytest.skip("python3.14 not on PATH")
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=False,
                            env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}"})
    assert result.returncode == 78
    assert "heartbeat_url_file_missing" in result.stdout
    assert not marker.exists()


def test_units_run_the_installed_script_hourly():
    service = SERVICE.read_text()
    timer = TIMER.read_text()
    assert "Type=oneshot" in service
    assert "ExecStart=/opt/ed-finder-v3-runtime/backup-heartbeat.sh\n" in service
    assert "OnCalendar=hourly" in timer and "Persistent=true" in timer
    assert "Unit=edfinder-v3-backup-heartbeat.service" in timer
    assert "WantedBy=timers.target" in timer


def test_installer_and_heartbeat_share_one_url_contract():
    assert namespace(HEARTBEAT)["URL_PATTERN"].pattern == namespace(INSTALLER)["URL_PATTERN"].pattern


# --- installer ----------------------------------------------------------------

def installer(tmp_path, monkeypatch, *, url_file=True, first_run="0", enabled="enabled", tamper=None,
              start_code=0, fresh=True, busy=0):
    ns = namespace(INSTALLER)
    ns["URL_FILE_OWNER"] = os.geteuid()
    runtime = tmp_path / "runtime"
    units = tmp_path / "systemd"
    runtime.mkdir()
    units.mkdir()
    ns["FILES"] = (
        (ns["FILES"][0][0], runtime / "backup-heartbeat.sh", 0o700),
        (ns["FILES"][1][0], units / "edfinder-v3-backup-heartbeat.service", 0o644),
        (ns["FILES"][2][0], units / "edfinder-v3-backup-heartbeat.timer", 0o644),
    )
    if url_file:
        ns["URL_FILE"] = private_url_file(tmp_path)
    else:
        ns["URL_FILE"] = tmp_path / "absent.url"
    commands = []
    started = []

    def run(argv, *, timeout=30, check=True):
        commands.append(argv)
        out = {"hostname -s": "ed-finder-prod", "hostname -f": "nb79a3d.mevnode.com"}.get(" ".join(argv), "")
        code = 0
        if argv[:2] == ["systemctl", "is-enabled"]:
            out = enabled
        if argv[:2] == ["systemctl", "is-active"]:
            out = "activating" if len([c for c in commands if c[:2] == ["systemctl", "is-active"]]) <= busy else "inactive"
        if argv[:2] == ["systemctl", "start"]:
            started.append(True)
            code = start_code
        if argv[:2] == ["systemctl", "show"]:
            # An earlier run (exit 0) until this one starts, if it does.
            timestamp = 200 if started and fresh else 100
            status = first_run if started and fresh else "0"
            out = f"ExecMainStartTimestampMonotonic={timestamp}\nExecMainStatus={status}"
        return SimpleNamespace(returncode=code, stdout=out + "\n")

    ns["run"] = run
    ns["time"] = SimpleNamespace(sleep=lambda _seconds: None)
    monkeypatch.setattr(os, "geteuid", lambda: 0)  # after the owner above: the root check
    args = ["a" * 40]
    for source in (HEARTBEAT, SERVICE, TIMER):
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if tamper == source.name:
            digest = "0" * 64
        args += [digest, base64.b64encode(payload).decode()]
    monkeypatch.setattr("sys.argv", ["installer", *args])
    return ns, commands, runtime, units


SHOW = ["systemctl", "show", "--property=ExecMainStartTimestampMonotonic", "--property=ExecMainStatus",
        "edfinder-v3-backup-heartbeat.service"]


def receipt_of(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_installer_installs_pinned_files_enables_timer_and_runs_once(tmp_path, monkeypatch, capsys):
    ns, commands, runtime, units = installer(tmp_path, monkeypatch)
    assert ns["main"]() == 0
    receipt = receipt_of(capsys)
    assert receipt["status"] == "passed" and receipt["failures"] == []
    assert receipt["heartbeat_url_file_valid"] and receipt["installed_hashes_verified"]
    assert receipt["timer_enabled"] and receipt["first_run_started"] and receipt["first_run_exit_status"] == 0
    assert receipt["db_writes_performed"] is False and receipt["direct_db_access_performed"] is False
    for item in receipt["files"]:
        assert item["source_sha256"] == item["installed_sha256"]
    assert (runtime / "backup-heartbeat.sh").read_bytes() == HEARTBEAT.read_bytes()
    assert (runtime / "backup-heartbeat.sh").stat().st_mode & 0o777 == 0o700
    assert (units / "edfinder-v3-backup-heartbeat.timer").stat().st_mode & 0o777 == 0o644
    # The fresh run comes before the timer can trigger one of its own.
    assert [c for c in commands if c[0] == "systemctl"] == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "stop", "edfinder-v3-backup-heartbeat.timer"],
        ["systemctl", "is-active", "edfinder-v3-backup-heartbeat.service"],
        SHOW,
        ["systemctl", "start", "edfinder-v3-backup-heartbeat.service"],
        SHOW,
        ["systemctl", "enable", "--now", "edfinder-v3-backup-heartbeat.timer"],
        ["systemctl", "is-enabled", "edfinder-v3-backup-heartbeat.timer"],
    ]
    assert URL not in json.dumps(receipt)


@pytest.mark.parametrize(("options", "failure"), [
    ({"url_file": False}, "heartbeat_url_file_missing"),
    ({"tamper": "backup-heartbeat.sh"}, "committed_source_hash_mismatch"),
    ({"tamper": "edfinder-v3-backup-heartbeat.timer"}, "committed_source_hash_mismatch"),
])
def test_installer_refuses_before_any_write(tmp_path, monkeypatch, capsys, options, failure):
    ns, commands, runtime, units = installer(tmp_path, monkeypatch, **options)
    assert ns["main"]() == 1
    receipt = receipt_of(capsys)
    assert receipt["status"] == "stopped" and receipt["failures"] == [failure]
    assert receipt["filesystem_writes_performed"] is False and receipt["files_installed"] is False
    assert list(runtime.iterdir()) == [] and list(units.iterdir()) == []
    assert not [c for c in commands if c[0] == "systemctl"]


@pytest.mark.parametrize(("options", "failure"), [
    ({"first_run": "1", "start_code": 3}, "first_heartbeat_run_not_healthy"),
    ({"first_run": ""}, "first_heartbeat_run_not_healthy"),
    # Codex: a failed start job can leave ExecMainStatus=0 from an earlier run.
    ({"start_code": 1, "fresh": False}, "first_heartbeat_run_not_healthy"),
    ({"start_code": 1}, "first_heartbeat_run_not_healthy"),
    # A start that reports success but did not run the process again.
    ({"fresh": False}, "first_heartbeat_run_not_healthy"),
    ({"enabled": "disabled"}, "timer_not_enabled"),
])
def test_installer_reports_an_unhealthy_first_run(tmp_path, monkeypatch, capsys, options, failure):
    ns, commands, _runtime, _units = installer(tmp_path, monkeypatch, **options)
    assert ns["main"]() == 1
    receipt = receipt_of(capsys)
    assert receipt["status"] == "stopped" and receipt["failures"] == [failure]
    assert receipt["files_installed"] is True
    # The hourly timer is armed even so: an unhealthy state keeps alerting.
    assert ["systemctl", "enable", "--now", "edfinder-v3-backup-heartbeat.timer"] in commands


def test_installer_waits_for_a_run_already_in_progress(tmp_path, monkeypatch, capsys):
    ns, commands, _runtime, _units = installer(tmp_path, monkeypatch, busy=2)
    assert ns["main"]() == 0
    assert receipt_of(capsys)["first_run_started"] is True
    checks = [c for c in commands if c[:2] == ["systemctl", "is-active"]]
    assert len(checks) == 3
    assert commands.index(checks[-1]) < commands.index(["systemctl", "start", "edfinder-v3-backup-heartbeat.service"])


def test_installer_refuses_when_a_run_never_finishes(tmp_path, monkeypatch, capsys):
    ns, commands, _runtime, _units = installer(tmp_path, monkeypatch, busy=10_000)
    assert ns["main"]() == 1
    assert receipt_of(capsys)["failures"] == ["heartbeat_service_busy"]
    assert ["systemctl", "start", "edfinder-v3-backup-heartbeat.service"] not in commands


def test_installer_refuses_wrong_host(tmp_path, monkeypatch, capsys):
    ns, _commands, runtime, _units = installer(tmp_path, monkeypatch)
    real = ns["run"]
    ns["run"] = lambda argv, **k: (SimpleNamespace(returncode=0, stdout="elsewhere\n")
                                   if argv[0] == "hostname" else real(argv, **k))
    assert ns["main"]() == 1
    assert receipt_of(capsys)["failures"] == ["target_host_mismatch"]
    assert list(runtime.iterdir()) == []


# --- workflow -----------------------------------------------------------------

def test_workflow_allows_only_a_manual_main_dispatch_and_streams_trusted_sources():
    text = WORKFLOW.read_text()
    options = yaml.safe_load(text)[True]["workflow_dispatch"]["inputs"]["operation"]["options"]
    assert "v3-backup-heartbeat-install" in options
    case = text.split("v3-backup-heartbeat-install)\n", 1)[1].split(";;", 1)[0]
    assert '"$EVENT_NAME" = workflow_dispatch' in case and '"$CURRENT_REF" = refs/heads/main' in case
    step = text.split("- name: Install trusted V3 backup heartbeat", 1)[1].split("\n      - name:", 1)[0]
    for path in ("deploy/v3-production/backup/backup-heartbeat.sh",
                 "deploy/v3-production/backup/edfinder-v3-backup-heartbeat.service",
                 "deploy/v3-production/backup/edfinder-v3-backup-heartbeat.timer"):
        assert path in step
    assert 'git -C trusted-main show "$source_sha:$path"' in step
    assert "< trusted-main/scripts/operator/actions/v3-backup-heartbeat-install.sh" in step
    assert "StrictHostKeyChecking=yes" in step and "ssh-keyscan" not in step
    assert "name: v3-backup-heartbeat-install-receipt" in text
