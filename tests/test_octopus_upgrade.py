"""Hermetic Octopus upgrade safety tests: no Docker daemon or network is used."""

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "scripts/operator/actions/octopus-upgrade.sh"
PAYLOAD = ROOT / "scripts/operator/octopus-upgrade"
PINS = {
    "package.json": "fe6e369eac296a68d283576f484093f6a0213fc77cf97998d79463d07f1f0d5e",
    "package-lock.json": "871e50428cfae28914c7d871b8a70f9b0cd27704ac47d3ff9216c9ec92694ba0",
    "openai-models.sql": "bbf4daa73643b00f1b979b43f0950ffda5357e24ff84dff766053646fcdd70d3",
}
FROM_DIGEST = "sha256:7a65a6009136376a74ff0a4dd58fae26c10f610879bed7f9c97adb0530c7eb78"
TO_DIGEST = "sha256:dd36e9e7b9a8c092cf4382c1129500aa776e0848d72f28e45fdb5ac3e53fd043"
FROM_COMMIT = "55583ac832472ad8b535f1f678f9c11837f7cfdb"
TO_COMMIT = "634c32d71f06576e5e71ee2895d694668fd15a7a"
DATABASE_URL = "postgresql://octopus:disposable-non-default-password@postgres:5432/octopus"


def test_reviewed_payloads_and_upgrade_constants_are_pinned():
    source = ACTION.read_text()
    for name, digest in PINS.items():
        assert hashlib.sha256((PAYLOAD / name).read_bytes()).hexdigest() == digest
        assert digest in source
    for value in (
        FROM_COMMIT, TO_COMMIT, FROM_DIGEST, TO_DIGEST,
        "ghcr.io/octopusreview/octopus-selfhost:1.3.3",
        "ghcr.io/brianstewart377-rgb/ed-finder/mirror/node@sha256:"
        "e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf",
        "https://github.com/octopusreview/octopus",
        "ed-finder/operator-operation-result/v1",
    ):
        assert value in source


def test_action_never_prints_env_or_uses_tracing_or_manages_qdrant():
    source = ACTION.read_text()
    assert "set -euo pipefail" in source
    assert re.search(r"\bset\s+-[^\n]*x", source) is None
    assert re.search(r"\b(?:cat|echo)\b[^\n]*\.env", source) is None
    assert "--network host" not in source
    assert "--privileged" not in source
    assert re.search(r"(?:up|stop|restart|rm|down)[^\n]*qdrant", source) is None
    assert "docker volume" not in source
    assert "postgresql://octopus:octopus@postgres:5432/octopus" not in source


def _receipt(result):
    reports = []
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("schema_version") == "ed-finder/operator-operation-result/v1":
            reports.append(item)
    assert reports, (result.stdout, result.stderr)
    return reports[-1]


def _events(log):
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


STUB = r'''
import io
import json
import os
import signal
import sys
import tarfile
import time
from pathlib import Path

root = Path(os.environ["OCTOPUS_TEST_ROOT"])
state_file = root / "state.json"
state = json.loads(state_file.read_text())
args = sys.argv[1:]
tool = Path(sys.argv[0]).name
entry = {"tool": tool, "args": args, "version": state["version"], "running": state["running"],
         "env_bytes": (root / "octopus/.env").read_bytes().hex()}
if tool == "docker" and args and args[0] == "run":
    entry["database_url"] = os.environ.get("DATABASE_URL")
    mount = args[args.index("--mount") + 1]
    directory = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
    migration_dir = directory / "packages/db/prisma/migrations"
    entry["directory"] = directory.name
    entry["migrations"] = sorted(path.name for path in migration_dir.iterdir() if path.is_dir())
    entry["package_hashes"] = {name: __import__("hashlib").sha256((directory / name).read_bytes()).hexdigest()
                               for name in ("package.json", "package-lock.json")}
with (root / "commands.jsonl").open("a") as log:
    log.write(json.dumps(entry) + "\n")


def save():
    state_file.write_text(json.dumps(state))


if tool == "fence":
    print(json.dumps({"failures": ["purge_active"] if state["fenced"] else [], "allowed": not state["fenced"]}))
    sys.exit(1 if state["fenced"] else 0)
if tool == "git":
    args = args[2:]  # -C fixed-checkout
    if args[:2] == ["rev-parse", "HEAD"]:
        print("55583ac832472ad8b535f1f678f9c11837f7cfdb")
    elif args[:2] == ["remote", "get-url"]:
        print(state["origin"])
    elif args[0] == "status":
        sys.stdout.write(" M docker-compose.selfhost.yml\0?? docker-compose.selfhost.yml.before-qdrant-healthcheck-repair.20261031T120000Z\0")
        if "--untracked-files=all" in args:
            for path in sorted((root / "octopus/backups").glob("*")):
                sys.stdout.write("?? backups/" + path.name + "\0")
    elif args[0] == "rev-parse":
        print("634c32d71f06576e5e71ee2895d694668fd15a7a")
    elif args[0] == "archive":
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as archive:
            for name in [f"202609010000{i:02}_test" for i in range(60)] + ["20260929150000_sonnet55"]:
                content = b"-- disposable migration fixture\n"
                info = tarfile.TarInfo("packages/db/prisma/migrations/" + name + "/migration.sql")
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
            content = b"// disposable config fixture\n"
            info = tarfile.TarInfo("packages/db/prisma.config.ts")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    elif args[0] != "fetch":
        raise RuntimeError("unexpected git call")
    sys.exit(0)
assert tool == "docker"
if args[:2] == ["compose", "version"]:
    print("Docker Compose version test")
elif args[0] == "compose":
    if "config" in args:
        print(json.dumps({"services": {
            "web": {"image": "ghcr.io/octopusreview/octopus-selfhost:" + state["version"],
                    "environment": state["compose_environment"]},
            "postgres": {"image": "postgres:17-alpine"},
            "qdrant": {"image": "qdrant/qdrant:v1.17.0"},
        }}))
    elif "up" in args:
        assert args[-3:] == ["-d", "--no-deps", "web"]
        env = (root / "octopus/.env").read_bytes()
        state["version"] = "1.3.3" if b"OCTOPUS_VERSION=1.3.3" in env else "1.0.122"
        state["running"] = True
        save()
    elif "stop" in args:
        assert args[-2:] == ["stop", "web"]
        if state.get("fail_stop"):
            sys.exit(1)
        state["running"] = bool(state.get("stop_stays_running"))
        save()
    else:
        raise RuntimeError("unexpected compose call")
elif args[0] == "inspect":
    if args[-1] == "octopus-postgres-1":
        print(json.dumps([{"Config": {"Image": "postgres:17-alpine"}, "NetworkSettings": {"Networks": {"octopus_default": {}}}}]))
    elif args[-1] == "octopus-qdrant-1":
        print(json.dumps([{"Config": {"Image": "qdrant/qdrant:v1.17.0"}}]))
    else:
        print(json.dumps([{"Config": {"Image": "ghcr.io/octopusreview/octopus-selfhost:" + state["version"], "Env": state["web_environment"]}, "Image": "test-image-" + state["version"], "State": {"Running": state["running"], "Health": {"Status": "unhealthy" if state.get("fail_new_health") and state["version"] == "1.3.3" else "healthy"}}}]))
elif args[:2] == ["image", "inspect"]:
    version = "1.3.3" if "1.3.3" in args[-1] else "1.0.122"
    digest = ("sha256:dd36e9e7b9a8c092cf4382c1129500aa776e0848d72f28e45fdb5ac3e53fd043" if version == "1.3.3" else
              "sha256:7a65a6009136376a74ff0a4dd58fae26c10f610879bed7f9c97adb0530c7eb78")
    print(json.dumps([{"RepoDigests": ["ghcr.io/octopusreview/octopus-selfhost@" + digest]}]))
elif args[0] == "pull":
    pass
elif args[0] == "run":
    assert entry["directory"] == "migrations-src"
    assert state["version"] == "1.0.122" and not state["running"], "migrations require the write barrier"
    if state.get("signal_migrate"):
        os.kill(os.getppid(), signal.SIGTERM)
        time.sleep(0.15)  # The attached migration remains in flight after SIGTERM.
    state["count"] = 36 if state.get("fail_migrate") else 61
    save()
    if state.get("signal_migrate"):
        (root / "migration-completed").write_text("completed before rollback")
    if state.get("fail_migrate"):
        sys.exit(1)
elif args[0] == "exec":
    if "node" in args:
        print("healthy" if "/api/health" in args[-1] else json.dumps({"version": state["version"]}))
    elif "pg_dump" in args:
        assert not state["running"], "backup requires the write barrier"
        if state.get("fail_dump"):
            sys.exit(1)
        sys.stdout.buffer.write(b"PGDMP disposable fixture")
    elif "pg_restore" in args:
        assert sys.stdin.buffer.read().startswith(b"PGDMP")
        if "--list" in args:
            if state.get("fail_backup_verification"):
                sys.exit(1)
            print("no table entries" if state.get("backup_missing_table") else "1; 1259 123 TABLE public fixture octopus")
        else:
            if state.get("fail_restore"):
                sys.exit(1)
            state["count"] = 35
            state["models"] = 0
            save()
    elif "psql" in args:
        if "-q" in args:
            assert not state["running"], "model changes require the write barrier"
            if state.get("fail_models"):
                sys.exit(1)
            assert b'ON CONFLICT ("modelId") DO NOTHING' in sys.stdin.buffer.read()
            state["models"] = 10
            save()
        elif "-c" in args:
            if state.get("signal_migrate"):
                assert (root / "migration-completed").exists(), "restore raced an active migration"
            assert args[-4:] == ["-c", "DROP DATABASE octopus WITH (FORCE)", "-c", "CREATE DATABASE octopus OWNER octopus"]
            state["count"] = 0
            save()
        else:
            query = args[-1]
            if "_prisma_migrations" in query:
                print(str(state["count"]) + "|0|" + ("20260813200000_retire_opus_4647_reorder_models" if state["count"] == 35 else "20261001000000_newest"))
            elif "to_regclass" in query:
                print("f" if state.get("jobs_absent") else "t")
            elif "pgboss.job" in query:
                state["jobs_probes"] = state.get("jobs_probes", 0) + 1
                save()
                print(state.get("jobs_recheck", state.get("jobs", 0)) if state["jobs_probes"] > 1 else state.get("jobs", 0))
            elif "claude-opus-5-5" in query:
                print("2")
            elif "available_models" in query:
                print(state["models"])
            else:
                raise RuntimeError("unexpected SQL probe")
    else:
        raise RuntimeError("unexpected exec call")
else:
    raise RuntimeError("unexpected Docker call")
'''


@pytest.fixture
def operator(tmp_path):
    octopus = tmp_path / "octopus"
    octopus.mkdir()
    (octopus / "docker-compose.selfhost.yml").write_text("# disposable compose fixture\n")
    env_bytes = b"# private comment\r\nOTHER=env-secret-sentinel\nOCTOPUS_VERSION=1.0.122\r\nLAST=value without final newline"
    (octopus / ".env").write_bytes(env_bytes)
    (octopus / ".env").chmod(0o640)
    repo = tmp_path / "repo"
    repo.mkdir()
    docker_dir = tmp_path / "docker-state"
    docker_dir.mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for command in ("docker", "git", "fence"):
        stub = binaries / command
        stub.write_text("#!" + sys.executable + "\n" + STUB)
        stub.chmod(0o755)
    state_file = tmp_path / "state.json"
    default_state = {
        "version": "1.0.122", "count": 35, "models": 0, "fenced": False, "running": True,
        "origin": "https://github.com/octopusreview/octopus",
        "web_environment": ["UNRELATED=env-secret-sentinel", "DATABASE_URL=" + DATABASE_URL],
        "compose_environment": {"DATABASE_URL": DATABASE_URL, "PRIVATE": "env-secret-sentinel"},
    }
    state_file.write_text(json.dumps(default_state))
    script = tmp_path / "action.sh"
    original_source = ACTION.read_text()
    isolated_source = original_source.replace("/opt/octopus", str(octopus)).replace("/opt/ed-finder", str(repo)).replace("/var/lib/docker", str(docker_dir))
    # Only the injected new-web health failure gets a short real timeout loop.
    isolated_source = isolated_source.replace(
        "time.monotonic() + 180",
        "time.monotonic() + (1 if version == TO_VERSION and os.environ.get('OCTOPUS_TEST_FAIL_NEW_HEALTH') == '1' else 180)",
    )
    script.write_text(
        "hostname() { printf '%s\\n' ed-finder-prod; }\n"
        "id() { printf '%s\\n' 0; }\n"
        "v3_purge_state_check() { fence; }\n" + isolated_source
    )
    environment = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ["PATH"], OCTOPUS_TEST_ROOT=str(tmp_path))
    for filename, variable in (
        ("package.json", "OCTOPUS_PACKAGE_JSON_B64"),
        ("package-lock.json", "OCTOPUS_PACKAGE_LOCK_B64"),
        ("openai-models.sql", "OCTOPUS_MODELS_SQL_B64"),
    ):
        environment[variable] = base64.b64encode((PAYLOAD / filename).read_bytes()).decode()

    def execute(mode="apply", *, state=None, corrupt=None):
        if state:
            state_file.write_text(json.dumps(default_state | state))
        invocation_env = environment.copy()
        if state and state.get("fail_new_health"):
            invocation_env["OCTOPUS_TEST_FAIL_NEW_HEALTH"] = "1"
        if corrupt:
            invocation_env[corrupt] = base64.b64encode(b"wrong reviewed bytes").decode()
        result = subprocess.run(
            ["bash", str(script), *([mode] if isinstance(mode, str) else mode)], cwd=repo,
            env=invocation_env, text=True, capture_output=True, check=False, timeout=25,
        )
        assert "env-secret-sentinel" not in result.stdout + result.stderr
        web_environment = (default_state | (state or {}))["web_environment"]
        for value in web_environment or []:
            if isinstance(value, str) and value.startswith("DATABASE_URL="):
                database_url = value.removeprefix("DATABASE_URL=")
                if database_url:
                    assert database_url not in result.stdout + result.stderr
        compose_environment = (default_state | (state or {}))["compose_environment"]
        if isinstance(compose_environment, dict):
            compose_values = [compose_environment.get("DATABASE_URL")]
        elif isinstance(compose_environment, list):
            compose_values = [value.split("=", 1)[1] for value in compose_environment
                              if isinstance(value, str) and value.startswith("DATABASE_URL=")]
        else:
            compose_values = []
        for database_url in compose_values:
            if isinstance(database_url, str) and database_url:
                assert database_url not in result.stdout + result.stderr
        return result, _receipt(result), _events(tmp_path / "commands.jsonl")

    return execute, octopus, env_bytes, state_file


@pytest.mark.parametrize("mode", [[], ["apply", "extra"], "", "upgrade", "APPLY", "--apply"])
def test_only_exact_preflight_and_apply_mode_are_accepted(operator, mode):
    execute, _, _, _ = operator
    result, report, commands = execute(mode)
    assert result.returncode != 0
    assert report["reason"] == "invalid_mode"
    assert not commands


def test_preflight_reports_fence_without_any_mutation(operator):
    execute, octopus, before_env, _ = operator
    before = {path.name: path.read_bytes() for path in octopus.iterdir()}
    result, report, commands = execute("preflight", state={"fenced": True})
    assert result.returncode == 0, report
    assert report["operation"] == "octopus-upgrade-preflight"
    assert report["verdict"] == "ready"
    assert report["purge_fence_clear"] is False
    assert report["purge_state"]["failures"] == ["purge_active"]
    assert report["web_version"] == "1.0.122"
    assert report["active_background_jobs"] == 0
    assert report["git"]["status_files"] == [
        "docker-compose.selfhost.yml",
        "docker-compose.selfhost.yml.before-qdrant-healthcheck-repair.20261031T120000Z",
    ]
    assert before == {path.name: path.read_bytes() for path in octopus.iterdir()}
    assert (octopus / ".env").read_bytes() == before_env
    for event in commands:
        args = event["args"]
        assert not {"pull", "up", "stop", "run", "fetch", "pg_dump", "pg_restore"}.intersection(args)
        if "psql" in args:
            assert "-tAc" in args
            assert args[-1].lower().startswith("select ")


@pytest.mark.parametrize("mode", ["preflight", "apply"])
@pytest.mark.parametrize("suffix", ["", ".git"])
def test_exact_octopus_origins_are_accepted(operator, mode, suffix):
    execute, _, _, _ = operator
    result, report, _ = execute(mode, state={"origin": "https://github.com/octopusreview/octopus" + suffix})
    assert result.returncode == 0, report
    assert report["git"]["origin_matches"] is True


@pytest.mark.parametrize("mode", ["preflight", "apply"])
@pytest.mark.parametrize("origin", [
    "https://github.com/octopusreview/octopus/",
    "https://github.com/octopusreview/octopus.git/",
    "http://github.com/octopusreview/octopus",
    "git@github.com:octopusreview/octopus.git",
    "https://github.com/other/octopus",
    "https://github.com/octopusreview/octopus.git?extra=true",
    "https://github.com.example/octopusreview/octopus",
])
def test_other_octopus_origins_block_before_changes(operator, mode, origin):
    execute, octopus, before_env, _ = operator
    result, report, commands = execute(mode, state={"origin": origin})
    assert (result.returncode == 0) is (mode == "preflight")
    assert report["verdict"] == "blocked"
    assert report["git"]["origin_matches"] is False
    assert "unexpected_git_origin" in report["reasons"]
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == before_env
    assert all(not {"pull", "up", "stop", "run", "fetch"}.intersection(event["args"]) for event in commands)


@pytest.mark.parametrize("mode", ["preflight", "apply"])
@pytest.mark.parametrize("scheme", ["postgresql", "postgres"])
@pytest.mark.parametrize("compose_shape", ["mapping", "list"])
def test_running_database_url_with_non_default_password_is_used_without_disclosure(operator, mode, scheme, compose_shape):
    execute, _, _, _ = operator
    database_url = DATABASE_URL.replace("postgresql:", scheme + ":", 1)
    compose_environment = ({"DATABASE_URL": database_url, "OTHER": "value"} if compose_shape == "mapping"
                           else ["OTHER=value", "DATABASE_URL=" + database_url])
    result, report, commands = execute(mode, state={
        "web_environment": ["DATABASE_URL=" + database_url], "compose_environment": compose_environment,
    })
    assert result.returncode == 0, report
    assert report["verdict"] == "ready"
    assert report["database_url_shape_ok"] is True
    assert report["database_url_matches_compose"] is True
    assert database_url not in json.dumps(report)
    assert database_url not in result.stdout + result.stderr
    assert all(database_url not in json.dumps(event["args"]) for event in commands)
    migrators = [event for event in commands if event.get("directory") == "migrations-src"]
    if mode == "apply":
        assert len(migrators) == 1
        assert migrators[0]["database_url"] == database_url
        args = migrators[0]["args"]
        assert args[args.index("--env") + 1] == "DATABASE_URL"
    else:
        assert not migrators


@pytest.mark.parametrize("mode", ["preflight", "apply"])
@pytest.mark.parametrize("compose_shape", ["mapping", "list"])
@pytest.mark.parametrize("rendered_url", [
    DATABASE_URL.replace("disposable-non-default-password", "different-disposable-password"),
    DATABASE_URL.replace("postgresql:", "postgres:"),
    DATABASE_URL.replace("disposable-", "%64isposable-"),
], ids=["different-password", "equivalent-scheme", "equivalent-password-encoding"])
def test_rendered_database_url_must_match_running_value_byte_for_byte(operator, mode, compose_shape, rendered_url):
    execute, octopus, before_env, state_file = operator
    compose_environment = ({"DATABASE_URL": rendered_url} if compose_shape == "mapping"
                           else ["DATABASE_URL=" + rendered_url])
    result, report, commands = execute(mode, state={"compose_environment": compose_environment})
    assert (result.returncode == 0) is (mode == "preflight")
    assert report["verdict"] == "blocked"
    assert report["database_url_shape_ok"] is True
    assert report["database_url_matches_compose"] is False
    assert report["reasons"] == ["unexpected_database_url"]
    for database_url in (DATABASE_URL, rendered_url):
        assert database_url not in json.dumps(report)
        assert database_url not in result.stdout + result.stderr
        assert all(database_url not in json.dumps(event["args"]) for event in commands)
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == before_env
    assert all(not {"pull", "up", "stop", "run", "fetch", "pg_dump", "pg_restore"}.intersection(event["args"]) for event in commands)
    state = json.loads(state_file.read_text())
    assert state["version"] == "1.0.122" and state["count"] == 35 and state["models"] == 0 and state["running"]


@pytest.mark.parametrize("mode", ["preflight", "apply"])
@pytest.mark.parametrize("compose_environment", [
    {},
    [],
    None,
    {"OTHER": "value"},
    ["OTHER=value"],
    {"DATABASE_URL": None},
    {"DATABASE_URL": 42},
    ["DATABASE_URL"],
    ["DATABASE_URL="],
    ["DATABASE_URL=" + DATABASE_URL, "DATABASE_URL=" + DATABASE_URL],
    ["DATABASE_URL=" + DATABASE_URL, "DATABASE_URL=" + DATABASE_URL.replace("disposable-", "different-")],
], ids=[
    "empty-mapping", "empty-list", "missing-environment", "mapping-missing-url", "list-missing-url",
    "null-url", "non-string-url", "bare-key", "empty-url", "duplicate-equal", "duplicate-different",
])
def test_missing_or_duplicate_rendered_database_url_blocks_before_changes(operator, mode, compose_environment):
    execute, octopus, before_env, _ = operator
    result, report, commands = execute(mode, state={"compose_environment": compose_environment})
    assert (result.returncode == 0) is (mode == "preflight")
    assert report["verdict"] == "blocked"
    assert report["database_url_shape_ok"] is True
    assert report["database_url_matches_compose"] is False
    assert report["reasons"] == ["unexpected_database_url"]
    assert DATABASE_URL not in json.dumps(report)
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == before_env
    assert all(not {"pull", "up", "stop", "run", "fetch", "pg_dump", "pg_restore"}.intersection(event["args"]) for event in commands)


@pytest.mark.parametrize("mode", ["preflight", "apply"])
@pytest.mark.parametrize("web_environment", [
    ["DATABASE_URL=" + DATABASE_URL.replace("//octopus:", "//other:")],
    ["DATABASE_URL=" + DATABASE_URL.replace("@postgres:", "@other:")],
    ["DATABASE_URL=" + DATABASE_URL.replace(":5432/", ":5433/")],
    ["DATABASE_URL=" + DATABASE_URL.replace(":5432/octopus", ":5432/other")],
    ["DATABASE_URL=" + DATABASE_URL.replace("postgresql:", "mysql:")],
    ["DATABASE_URL=postgresql://octopus@postgres:5432/octopus"],
    ["DATABASE_URL=postgresql://octopus:@postgres:5432/octopus"],
    ["DATABASE_URL=" + DATABASE_URL + "?sslmode=require"],
    ["DATABASE_URL=" + DATABASE_URL + "#fragment"],
    ["DATABASE_URL=" + DATABASE_URL, "DATABASE_URL=" + DATABASE_URL],
    ["OTHER=value"],
    ["DATABASE_URL=" + DATABASE_URL.replace(":5432/", ":invalid/")],
    ["DATABASE_URL=" + DATABASE_URL.replace(":5432/", ":65536/")],
    ["DATABASE_URL=" + DATABASE_URL.replace("@postgres:", "@[postgres:")],
    ["DATABASE_URL="],
    None,
], ids=[
    "wrong-user", "wrong-host", "wrong-port", "wrong-database", "wrong-scheme",
    "missing-password", "empty-password", "query", "fragment", "duplicate", "absent",
    "invalid-port", "port-out-of-range", "invalid-host", "empty-url", "missing-environment",
])
def test_database_url_shape_violation_blocks_without_disclosure_or_changes(operator, mode, web_environment):
    execute, octopus, before_env, _ = operator
    result, report, commands = execute(mode, state={"web_environment": web_environment})
    assert (result.returncode == 0) is (mode == "preflight")
    assert report["verdict"] == "blocked"
    assert report["database_url_shape_ok"] is False
    assert report["database_url_matches_compose"] is False
    assert report["reasons"] == ["unexpected_database_url"]
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == before_env
    assert all(not {"pull", "up", "stop", "run", "fetch"}.intersection(event["args"]) for event in commands)


def test_missing_background_job_table_is_reported_as_null(operator):
    execute, _, _, _ = operator
    result, report, _ = execute("preflight", state={"jobs_absent": True})
    assert result.returncode == 0
    assert report["active_background_jobs"] is None
    assert report["verdict"] == "ready"


def test_apply_refuses_purge_before_pulls_backup_or_env_edit(operator):
    execute, octopus, before_env, _ = operator
    result, report, commands = execute(state={"fenced": True})
    assert result.returncode != 0
    assert report["reason"] == "purge_state_refused"
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == before_env
    assert [event["tool"] for event in commands] == ["docker", "fence"]
    assert commands[0]["args"] == ["compose", "version"]


@pytest.mark.parametrize("variable", ["OCTOPUS_PACKAGE_JSON_B64", "OCTOPUS_PACKAGE_LOCK_B64", "OCTOPUS_MODELS_SQL_B64"])
def test_each_payload_checksum_mismatch_stops_before_changes(operator, variable):
    execute, octopus, before_env, _ = operator
    result, report, commands = execute(corrupt=variable)
    assert result.returncode != 0
    assert report["reason"].startswith("payload_sha256_mismatch:")
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == before_env
    assert all(event["args"] == ["compose", "version"] or event["tool"] == "fence" for event in commands)


def _find_event(commands, predicate, start=0):
    return next(index for index in range(start, len(commands)) if predicate(commands[index]))


def test_apply_holds_write_barrier_until_all_database_changes_and_preserves_env_bytes(operator):
    execute, octopus, before_env, state_file = operator
    result, report, commands = execute()
    assert result.returncode == 0, report
    assert report["status"] == "passed"
    assert report["migrations_before"]["finished"] == 35
    assert "migrations_stage1" not in report
    assert report["migrations_after"]["finished"] == 61
    assert report["image_digest_before"] == FROM_DIGEST
    assert report["image_digest_after"] == TO_DIGEST
    assert report["model_rows_added"] == 10
    assert report["web_stopped_at_step"] == "write_barrier"
    assert isinstance(report["downtime_seconds"], (int, float)) and report["downtime_seconds"] > 0
    expected_env = before_env.replace(b"OCTOPUS_VERSION=1.0.122", b"OCTOPUS_VERSION=1.3.3")
    assert (octopus / ".env").read_bytes() == expected_env
    assert (octopus / ".env").stat().st_mode & 0o777 == 0o640
    assert Path(report["env_backup"]).read_bytes() == before_env
    assert Path(report["database_backup"]).read_bytes().startswith(b"PGDMP")
    assert Path(report["database_backup"]).stat().st_mode & 0o777 == 0o600
    assert (octopus / "backups").stat().st_mode & 0o777 == 0o700
    fence = _find_event(commands, lambda e: e["tool"] == "fence")
    pulls = [index for index, event in enumerate(commands) if event["args"][:1] == ["pull"]]
    source = _find_event(commands, lambda e: e["tool"] == "git" and "archive" in e["args"])
    jobs = _find_event(commands, lambda e: "psql" in e["args"] and "from pgboss.job" in e["args"][-1], source)
    stop = _find_event(commands, lambda e: "stop" in e["args"])
    dump = _find_event(commands, lambda e: "pg_dump" in e["args"])
    verified = _find_event(commands, lambda e: "pg_restore" in e["args"] and "--list" in e["args"])
    migrators = [index for index, event in enumerate(commands) if event.get("directory") == "migrations-src"]
    assert len(migrators) == 1
    migrate = migrators[0]
    models = _find_event(commands, lambda e: "psql" in e["args"] and "-q" in e["args"])
    env_edit = _find_event(commands, lambda e: bytes.fromhex(e["env_bytes"]) == expected_env)
    switched = _find_event(commands, lambda e: "up" in e["args"])
    health = _find_event(commands, lambda e: "node" in e["args"] and "/api/health" in e["args"][-1], switched)
    assert len(pulls) == 2 and fence < min(pulls) <= max(pulls) < source < jobs < stop < dump < verified < migrate < models < env_edit
    assert env_edit == switched < health
    assert not any("pg_dump" in event["args"] for event in commands[:stop])
    assert not any("up" in event["args"] for event in commands[stop:env_edit])
    assert all(not event["running"] for event in commands[stop + 1:switched + 1])
    assert len(commands[migrate]["migrations"]) == 61
    assert "20260929150000_sonnet55" in commands[migrate]["migrations"]
    assert bytes.fromhex(commands[migrate]["env_bytes"]) == before_env
    assert commands[migrate]["package_hashes"] == {name: PINS[name] for name in ("package.json", "package-lock.json")}
    assert json.loads(state_file.read_text())["count"] == 61
    args = commands[migrate]["args"]
    assert args.count("--mount") == 1
    assert args[args.index("--network") + 1] == "octopus_default"
    assert "--rm" in args
    assert "npm ci --ignore-scripts --no-audit --no-fund" in args[-1]
    assert args[-1].count("prisma migrate deploy") == 1
    mount = args[args.index("--mount") + 1]
    assert not Path(mount.split("src=", 1)[1].split(",dst=", 1)[0]).parent.exists(), "temporary migration files must be removed"


@pytest.mark.parametrize("failure,reason", [("fail_dump", "backup_command_failed"), ("fail_backup_verification", "backup_verification_failed"), ("backup_missing_table", "backup_verification_failed")])
def test_backup_failure_restarts_old_web_without_restoring_untouched_database(operator, failure, reason):
    execute, octopus, before_env, state_file = operator
    result, report, commands = execute(state={failure: True})
    assert result.returncode != 0
    assert report["status"] == "stopped", report
    assert report["reason"] == reason
    assert report["failed_step"] == "backup"
    assert report["web_stopped_at_step"] == "write_barrier"
    assert report["downtime_seconds"] > 0
    stop = _find_event(commands, lambda e: "stop" in e["args"])
    dump = _find_event(commands, lambda e: "pg_dump" in e["args"])
    start = _find_event(commands, lambda e: "up" in e["args"])
    healthy = _find_event(commands, lambda e: "node" in e["args"] and "/api/health" in e["args"][-1], start)
    assert stop < dump < start < healthy
    assert commands[healthy]["version"] == "1.0.122"
    assert any(e["args"][:2] == ["image", "inspect"] and "1.0.122" in e["args"][-1] for e in commands[start:])
    assert not any("DROP DATABASE octopus WITH (FORCE)" in e["args"] or "--no-owner" in e["args"] or e.get("directory") for e in commands)
    assert (octopus / ".env").read_bytes() == before_env
    state = json.loads(state_file.read_text())
    assert state["count"] == 35 and state["version"] == "1.0.122" and state["running"]


@pytest.mark.parametrize("failure,reason", [("fail_stop", "write_barrier_command_failed"), ("stop_stays_running", "web_still_running")])
def test_failed_write_barrier_restarts_old_web_without_backup_or_restore(operator, failure, reason):
    execute, octopus, before_env, state_file = operator
    result, report, commands = execute(state={failure: True})
    assert result.returncode != 0
    assert report["status"] == "stopped", report
    assert report["reason"] == reason
    assert report["failed_step"] == "write_barrier"
    assert report["downtime_seconds"] > 0
    assert not any("pg_dump" in e["args"] or "pg_restore" in e["args"] or "DROP DATABASE octopus WITH (FORCE)" in e["args"] for e in commands)
    assert any("up" in e["args"] for e in commands)
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == before_env
    assert json.loads(state_file.read_text())["running"]


def test_model_failure_restores_database_before_starting_old_web(operator):
    execute, octopus, before_env, state_file = operator
    result, report, commands = execute(state={"fail_models": True})
    assert result.returncode != 0
    assert report["status"] == "rolled_back", report
    assert report["reason"] == "models_insert_failed"
    assert report["failed_step"] == "models"
    models = _find_event(commands, lambda e: "psql" in e["args"] and "-q" in e["args"])
    restore = _find_event(commands, lambda e: "--no-owner" in e["args"])
    start = _find_event(commands, lambda e: "up" in e["args"])
    assert models < restore < start
    assert all(bytes.fromhex(e["env_bytes"]) == before_env for e in commands)
    assert (octopus / ".env").read_bytes() == before_env
    state = json.loads(state_file.read_text())
    assert state["count"] == 35 and state["version"] == "1.0.122" and state["running"]


def test_migration_failure_restores_database_and_old_web_in_order(operator):
    execute, octopus, before_env, state_file = operator
    result, report, commands = execute(state={"fail_migrate": True})
    assert result.returncode != 0
    assert report["status"] == "rolled_back", report
    assert report["reason"] == "migrate_command_failed"
    assert report["failed_step"] == "migrate"
    assert report["rollback_migrations"]["finished"] == 35
    assert report["web_stopped_at_step"] == "write_barrier"
    assert report["downtime_seconds"] > 0
    migrate = _find_event(commands, lambda e: e.get("directory") == "migrations-src")
    stop = _find_event(commands, lambda e: "stop" in e["args"], migrate)
    recreate = _find_event(commands, lambda e: "DROP DATABASE octopus WITH (FORCE)" in e["args"])
    restore = _find_event(commands, lambda e: "pg_restore" in e["args"] and "--no-owner" in e["args"])
    verified = _find_event(commands, lambda e: "psql" in e["args"] and "_prisma_migrations" in e["args"][-1], restore)
    start = _find_event(commands, lambda e: "up" in e["args"])
    version_probe = _find_event(commands, lambda e: "node" in e["args"] and "/api/version" in e["args"][-1], start)
    assert migrate < stop < recreate < restore < verified < start < version_probe
    assert commands[version_probe]["version"] == "1.0.122"
    assert (octopus / ".env").read_bytes() == before_env
    assert Path(report["database_backup"]).exists()
    state = json.loads(state_file.read_text())
    assert state["count"] == 35 and state["running"]


def test_already_upgraded_apply_changes_nothing(operator):
    execute, octopus, before_env, _ = operator
    upgraded_env = before_env.replace(b"OCTOPUS_VERSION=1.0.122", b"OCTOPUS_VERSION=1.3.3")
    (octopus / ".env").write_bytes(upgraded_env)
    result, report, commands = execute(state={"version": "1.3.3", "count": 61, "models": 10})
    assert result.returncode == 0, report
    assert report["status"] == "already_done"
    assert report["verdict"] == "already_upgraded"
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == upgraded_env
    assert all(not {"pull", "up", "stop", "run", "fetch"}.intersection(event["args"]) for event in commands)


def test_active_background_jobs_block_apply_before_changes(operator):
    execute, octopus, before_env, _ = operator
    result, report, commands = execute(state={"jobs": 1})
    assert result.returncode != 0
    assert report["reason"] == "preflight_blocked"
    assert "active_background_jobs" in report["reasons"]
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == before_env
    assert all(not {"pull", "up", "stop", "run", "fetch"}.intersection(event["args"]) for event in commands)


def test_active_jobs_at_write_barrier_refuse_before_stopping_web(operator):
    execute, octopus, before_env, state_file = operator
    result, report, commands = execute(state={"jobs_recheck": 1})
    assert result.returncode != 0
    assert report["status"] == "stopped", report
    assert report["reason"] == "active_background_jobs"
    assert report["failed_step"] == "write_barrier"
    assert any("archive" in event["args"] for event in commands)
    assert json.loads(state_file.read_text())["jobs_probes"] == 2
    assert all(not {"stop", "up", "run", "pg_dump", "pg_restore"}.intersection(event["args"]) for event in commands)
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == before_env
    assert json.loads(state_file.read_text())["running"]


@pytest.mark.parametrize("version_bytes", [b"OCTOPUS_VERSION=env-secret-sentinel", b"OCTOPUS_VERSION=1.0.122\nOCTOPUS_VERSION=1.0.122"])
def test_invalid_version_lines_fail_without_leaking_environment(operator, version_bytes):
    execute, octopus, before_env, _ = operator
    malformed_env = before_env.replace(b"OCTOPUS_VERSION=1.0.122", version_bytes)
    (octopus / ".env").write_bytes(malformed_env)
    result, report, commands = execute()
    assert result.returncode != 0
    assert report["reason"] == "preflight_blocked"
    assert report["env_version"]["value"] is None
    assert not (octopus / "backups").exists()
    assert (octopus / ".env").read_bytes() == malformed_env
    assert all(not {"pull", "up", "stop", "run", "fetch"}.intersection(event["args"]) for event in commands)


def test_new_web_health_timeout_restores_original_env_and_database(operator):
    execute, octopus, before_env, state_file = operator
    result, report, commands = execute(state={"fail_new_health": True})
    assert result.returncode != 0
    assert report["status"] == "rolled_back", report
    assert report["reason"] == "web_health_timeout"
    assert report["failed_step"] == "switch_web"
    assert report["rollback_migrations"]["finished"] == 35
    assert report["web_stopped_at_step"] == "write_barrier"
    assert report["downtime_seconds"] > 0
    start = _find_event(commands, lambda e: "up" in e["args"])
    failed_health = _find_event(commands, lambda e: e["args"] == ["inspect", "octopus-web-1"] and e["version"] == "1.3.3", start)
    stop = _find_event(commands, lambda e: "stop" in e["args"], start)
    restore = _find_event(commands, lambda e: "pg_restore" in e["args"] and "--no-owner" in e["args"])
    restart = _find_event(commands, lambda e: "up" in e["args"], start + 1)
    assert start < failed_health < stop < restore < restart
    assert bytes.fromhex(commands[stop]["env_bytes"]) == before_env
    assert (octopus / ".env").read_bytes() == before_env
    assert (octopus / ".env").stat().st_mode & 0o777 == 0o640
    state = json.loads(state_file.read_text())
    assert state["count"] == 35 and state["version"] == "1.0.122" and state["running"]


def test_failed_restore_names_rollback_step_and_original_failure(operator):
    execute, _, _, _ = operator
    result, report, commands = execute(state={"fail_migrate": True, "fail_restore": True})
    assert result.returncode != 0
    assert report["status"] == "rollback_failed"
    assert report["reason"] == "migrate_command_failed"
    assert report["rollback_failed_step"] == "rollback_restore_database"
    assert not any("up" in event["args"] for event in commands)


def test_sigterm_during_attached_migration_waits_then_rolls_back(operator):
    execute, octopus, before_env, state_file = operator
    result, report, commands = execute(state={"signal_migrate": True})
    assert result.returncode != 0
    assert report["status"] == "rolled_back", report
    assert report["reason"] == "interrupted_signal_15"
    assert report["failed_step"] == "migrate"
    assert report["rollback_migrations"]["finished"] == 35
    assert (octopus.parent / "migration-completed").read_text() == "completed before rollback"
    assert json.loads(state_file.read_text())["count"] == 35
    assert json.loads(state_file.read_text())["version"] == "1.0.122"
    assert (octopus / ".env").read_bytes() == before_env
    migrate = _find_event(commands, lambda event: event.get("directory") == "migrations-src")
    recreate = _find_event(commands, lambda event: "DROP DATABASE octopus WITH (FORCE)" in event["args"])
    assert migrate < recreate


def test_apply_rerun_accepts_its_own_backups_and_changes_nothing(operator):
    execute, octopus, _, _ = operator
    first, initial_report, initial_commands = execute()
    assert first.returncode == 0, initial_report
    snapshots = {path.name: path.read_bytes() for path in (octopus / "backups").iterdir()}
    second, report, commands = execute()
    assert second.returncode == 0, report
    assert report["status"] == "already_done"
    assert report["verdict"] == "already_upgraded"
    assert report["git"]["status_files"] == [
        "docker-compose.selfhost.yml",
        "docker-compose.selfhost.yml.before-qdrant-healthcheck-repair.20261031T120000Z",
        *["backups/" + name for name in sorted(snapshots)],
    ]
    assert snapshots == {path.name: path.read_bytes() for path in (octopus / "backups").iterdir()}
    assert all(not {"pull", "up", "stop", "run", "fetch"}.intersection(event["args"])
               for event in commands[len(initial_commands):])
