#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
early_stop() {
  printf '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"octopus-upgrade-%s","status":"stopped","reason":"%s"}\n' "${MODE//[^a-z]/}" "$1"
  exit 1
}
[ "$#" -eq 1 ] || early_stop invalid_mode
case "$MODE" in preflight|apply) ;; *) early_stop invalid_mode ;; esac
if command -v python3.14 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.14)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  early_stop python3_unavailable
fi
"$PYTHON_BIN" -I -S -c 'import platform,sys; sys.exit(0 if platform.python_implementation() == "CPython" and sys.version_info[:2] == (3, 14) else 1)' || early_stop python314_required
[ "$(hostname -s)" = ed-finder-prod ] || early_stop unexpected_host
[ "$(id -u)" -eq 0 ] || early_stop root_required
[ "$(pwd -P)" = /opt/ed-finder ] || early_stop unexpected_working_directory
[ -d /opt/octopus ] || early_stop octopus_directory_missing
[ -f /opt/octopus/docker-compose.selfhost.yml ] || early_stop compose_file_missing
[ -f /opt/octopus/.env ] || early_stop env_file_missing
command -v docker >/dev/null 2>&1 || early_stop docker_missing
docker compose version >/dev/null 2>&1 || early_stop docker_compose_missing
declare -F v3_purge_state_check >/dev/null || early_stop purge_state_helper_missing

WORK_DIR="$(mktemp -d)"
chmod 700 "$WORK_DIR"
trap 'rm -rf -- "$WORK_DIR"' EXIT
# Only the trusted-main prepared stream supplies these bytes; never caller input.
export OCTOPUS_PACKAGE_JSON_B64 OCTOPUS_PACKAGE_LOCK_B64 OCTOPUS_MODELS_SQL_B64
PURGE_CLEAR=false
if v3_purge_state_check > "$WORK_DIR/purge-state.json"; then PURGE_CLEAR=true; fi
"$PYTHON_BIN" -I -S - "$MODE" "$WORK_DIR" "$PURGE_CLEAR" <<'OCTOPUS_UPGRADE_PYTHON'
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

FROM_VERSION = "1.0.122"
FROM_COMMIT = "55583ac832472ad8b535f1f678f9c11837f7cfdb"
FROM_IMAGE_DIGEST = "sha256:7a65a6009136376a74ff0a4dd58fae26c10f610879bed7f9c97adb0530c7eb78"
TO_VERSION = "1.3.3"
TO_COMMIT = "634c32d71f06576e5e71ee2895d694668fd15a7a"
TO_IMAGE = "ghcr.io/octopusreview/octopus-selfhost:1.3.3"
TO_IMAGE_DIGEST = "sha256:dd36e9e7b9a8c092cf4382c1129500aa776e0848d72f28e45fdb5ac3e53fd043"
MIGRATOR_IMAGE = "ghcr.io/brianstewart377-rgb/ed-finder/mirror/node@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf"
OCTOPUS_REMOTES = ("https://github.com/octopusreview/octopus", "https://github.com/octopusreview/octopus.git")
PAYLOADS = {
    "package.json": ("OCTOPUS_PACKAGE_JSON_B64", "fe6e369eac296a68d283576f484093f6a0213fc77cf97998d79463d07f1f0d5e"),
    "package-lock.json": ("OCTOPUS_PACKAGE_LOCK_B64", "871e50428cfae28914c7d871b8a70f9b0cd27704ac47d3ff9216c9ec92694ba0"),
    "openai-models.sql": ("OCTOPUS_MODELS_SQL_B64", "bbf4daa73643b00f1b979b43f0950ffda5357e24ff84dff766053646fcdd70d3"),
}
BEFORE_COUNT, AFTER_COUNT = 35, 61
BEFORE_NEWEST = "20260813200000_retire_opus_4647_reorder_models"
IMAGE_REPO = "ghcr.io/octopusreview/octopus-selfhost"
OCTOPUS_DIR = Path("/opt/octopus")
ENV_FILE = OCTOPUS_DIR / ".env"
COMPOSE = ["docker", "compose", "--project-directory", str(OCTOPUS_DIR), "-f", str(OCTOPUS_DIR / "docker-compose.selfhost.yml")]
mode, work, purge_clear = sys.argv[1], Path(sys.argv[2]), sys.argv[3] == "true"
result = {"schema_version": "ed-finder/operator-operation-result/v1", "operation": "octopus-upgrade-" + mode}
rollback_required = False
web_restart_required = False
downtime_started = None
env_changed = False
step = "payload_verification"
defer_signal = False
pending_signal = None


class Stopped(Exception):
    pass


class Interrupted(Stopped):
    pass


def require(condition, reason):
    if not condition:
        raise Stopped(reason)


def run(args, *, data=None, output=None, env=None, strip=True, timeout=None, defer_interruption=True):
    # Capture diagnostics: rendered Compose, environment and tool errors may
    # contain credentials. Only controlled reason codes reach the receipt.
    global defer_signal
    # An interrupted attached migrator must finish before DB restore begins.
    # Defer termination until docker run returns, rather than orphaning Prisma.
    defer_signal = defer_interruption
    try:
        completed = subprocess.run(args, input=data, stdout=output or subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env, check=False, timeout=timeout)
    finally:
        defer_signal = False
    if pending_signal is not None:
        raise Interrupted("interrupted_signal_" + str(pending_signal))
    require(completed.returncode == 0, step + "_command_failed")
    if output is not None:
        return ""
    text = completed.stdout.decode()
    return text.strip() if strip else text


def sql(query):
    return run(["docker", "exec", "octopus-postgres-1", "psql", "-U", "octopus", "-d", "octopus", "-tAc", query])


def active_background_jobs():
    present = sql("SELECT to_regclass('pgboss.job') IS NOT NULL")
    require(present in ("t", "f"), "invalid_background_jobs_probe")
    return int(sql("select count(*) from pgboss.job where state='active'")) if present == "t" else None


def migrations():
    rows = sql('SELECT count(*) FILTER (WHERE finished_at IS NOT NULL AND rolled_back_at IS NULL), '
               'count(*) FILTER (WHERE finished_at IS NULL OR rolled_back_at IS NOT NULL), '
               'max(migration_name) FROM "_prisma_migrations"').split("|")
    require(len(rows) == 3, "invalid_migration_probe")
    return {"finished": int(rows[0]), "not_finished_or_rolled_back": int(rows[1]), "newest": rows[2]}


def require_migrations(count):
    state = migrations()
    require(state["finished"] == count and state["not_finished_or_rolled_back"] == 0, "unexpected_migration_counts")
    return state


def container(name, timeout=None):
    return json.loads(run(["docker", "inspect", name], timeout=timeout))[0]


def running_database_url(web):
    environment = web.get("Config", {}).get("Env")
    if not isinstance(environment, list):
        return None
    entries = [entry for entry in environment if isinstance(entry, str) and entry.startswith("DATABASE_URL=")]
    if len(entries) != 1:
        return None
    value = entries[0].split("=", 1)[1]
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in ("postgresql", "postgres") and parsed.username == "octopus"
                 and bool(parsed.password) and parsed.hostname == "postgres" and parsed.port == 5432
                 and parsed.path == "/octopus" and not parsed.query and not parsed.fragment)
    except ValueError:
        # Parser diagnostics can contain credentials; expose only a boolean.
        return None
    return value if valid else None


def database_url_matches_compose(environment, value):
    if value is None:
        return False
    if isinstance(environment, dict):
        return environment.get("DATABASE_URL") == value
    if isinstance(environment, list):
        entries = [entry for entry in environment
                   if isinstance(entry, str) and entry.split("=", 1)[0] == "DATABASE_URL"]
        return len(entries) == 1 and entries[0] == "DATABASE_URL=" + value
    return False


def image_digest(info, timeout=None):
    digests = json.loads(run(["docker", "image", "inspect", info["Image"]], timeout=timeout))[0].get("RepoDigests", [])
    matches = [d.split("@", 1)[1] for d in digests if d.startswith(IMAGE_REPO + "@")]
    require(len(matches) == 1, "running_image_digest_unresolved")
    return matches[0]


def web_version(timeout=10):
    body = run(["docker", "exec", "octopus-web-1", "node", "-e",
                "fetch('http://127.0.0.1:3000/api/version').then(r=>r.text()).then(t=>console.log(t))"], timeout=timeout)
    payload = json.loads(body)
    return payload.get("version") if isinstance(payload, dict) else None


def web_healthy(timeout=10, deadline=None):
    info = container("octopus-web-1", timeout=timeout)
    if not info.get("State", {}).get("Running"):
        return False
    health = info.get("State", {}).get("Health", {}).get("Status")
    if health is not None and health != "healthy":
        return False
    if deadline is not None:
        require(time.monotonic() < deadline, "web_health_timeout")
        timeout = min(timeout, deadline - time.monotonic())
    return run(["docker", "exec", "octopus-web-1", "node", "-e",
                "fetch('http://127.0.0.1:3000/api/health',{signal:AbortSignal.timeout(5000)}).then(r=>{if(!r.ok)process.exit(1);console.log('healthy')}).catch(()=>process.exit(1))"], timeout=timeout) == "healthy"


def wait_web(version, digest):
    deadline = time.monotonic() + 180

    def budget():
        remaining = deadline - time.monotonic()
        require(remaining > 0, "web_health_timeout")
        return min(10, remaining)

    while True:
        try:
            info = container("octopus-web-1", timeout=budget())
            if (image_digest(info, timeout=budget()) == digest
                    and web_version(timeout=budget()) == version and web_healthy(timeout=budget(), deadline=deadline)):
                require(time.monotonic() <= deadline, "web_health_timeout")
                return
        except Interrupted:
            raise
        except (Stopped, ValueError, KeyError, IndexError, subprocess.TimeoutExpired):
            pass
        require(time.monotonic() < deadline, "web_health_timeout")
        time.sleep(min(2, deadline - time.monotonic()))


def model_count():
    # IDs are extracted only from the checksum-verified, committed SQL.
    ids = ",".join("'" + model + "'" for model in model_ids)
    return int(sql('SELECT count(*) FROM available_models WHERE "modelId" IN (' + ids + ") AND provider='openai' AND category='llm'"))


def edit_env():
    # Bytes preserve unrelated secrets, comments, CRLF and final-newline state.
    original = ENV_FILE.read_bytes()
    lines = original.splitlines(keepends=True)
    indexes = [i for i, line in enumerate(lines) if line.startswith(b"OCTOPUS_VERSION=")]
    require(len(indexes) == 1, "env_version_line_count_changed")
    index = indexes[0]
    require(lines[index].rstrip(b"\r\n") == b"OCTOPUS_VERSION=1.0.122", "env_version_changed")
    lines[index] = lines[index].replace(b"1.0.122", b"1.3.3", 1)
    fd, name = tempfile.mkstemp(prefix=".octopus-version-", dir=OCTOPUS_DIR)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"".join(lines))
            stream.flush()
            os.fsync(stream.fileno())
        metadata = ENV_FILE.stat()
        os.chown(name, metadata.st_uid, metadata.st_gid)
        os.chmod(name, metadata.st_mode & 0o7777)
        os.replace(name, ENV_FILE)
    finally:
        Path(name).unlink(missing_ok=True)


def migrate():
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    run(["docker", "run", "--rm", "--network", network, "--mount",
         "type=bind,src=" + str(work / "migrations-src") + ",dst=/work", "--workdir", "/work",
         "--env", "DATABASE_URL", MIGRATOR_IMAGE, "sh", "-ec",
         "npm ci --ignore-scripts --no-audit --no-fund && cd packages/db && ../../node_modules/.bin/prisma migrate deploy"], env=environment, defer_interruption=True)


def rollback():
    global step
    step = "rollback_env"
    if env_changed:
        run(["cp", "--preserve=mode,ownership,timestamps", "--", str(env_backup), str(ENV_FILE)])
    step = "rollback_stop_web"
    run(COMPOSE + ["stop", "web"])
    step = "rollback_recreate_database"
    run(["docker", "exec", "octopus-postgres-1", "psql", "-U", "octopus", "-d", "postgres", "-v", "ON_ERROR_STOP=1",
         "-c", "DROP DATABASE octopus WITH (FORCE)", "-c", "CREATE DATABASE octopus OWNER octopus"])
    step = "rollback_restore_database"
    with dump.open("rb") as stream:
        # stdin is a file, not a potentially unbounded in-memory database copy.
        completed = subprocess.run(["docker", "exec", "-i", "octopus-postgres-1", "pg_restore", "-U", "octopus", "-d", "octopus", "--no-owner"],
                                   stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        require(completed.returncode == 0, "rollback_restore_database_failed")
    step = "rollback_verify_migrations"
    result["rollback_migrations"] = require_migrations(BEFORE_COUNT)
    step = "rollback_start_web"
    run(COMPOSE + ["up", "-d", "--no-deps", "web"])
    step = "rollback_verify_web"
    wait_web(FROM_VERSION, FROM_IMAGE_DIGEST)
    result["downtime_seconds"] = time.monotonic() - downtime_started


def restart_old_web():
    global step
    # No database mutation has begun, so recovery must not restore the dump.
    step = "restart_start_web"
    run(COMPOSE + ["up", "-d", "--no-deps", "web"])
    step = "restart_verify_web"
    wait_web(FROM_VERSION, FROM_IMAGE_DIGEST)
    result["downtime_seconds"] = time.monotonic() - downtime_started


def interrupted(signum, _frame):
    global pending_signal
    if defer_signal:
        pending_signal = signum
    else:
        raise Interrupted("interrupted_signal_" + str(signum))


for watched_signal in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
    signal.signal(watched_signal, interrupted)

try:
    for filename, (variable, expected) in PAYLOADS.items():
        payload = base64.b64decode(os.environ.get(variable, ""), validate=True)
        require(hashlib.sha256(payload).hexdigest() == expected, "payload_sha256_mismatch:" + filename)
        (work / filename).write_bytes(payload)
    model_ids = re.findall(r"\('edf_[^']+',\s*'([a-z0-9.-]+)'", (work / "openai-models.sql").read_text())
    require(len(model_ids) == 10 and len(set(model_ids)) == 10, "invalid_model_ids")
    step = "preflight"
    try:
        result["purge_state"] = json.loads((work / "purge-state.json").read_text())
        require(isinstance(result["purge_state"], dict), "invalid_purge_state_report")
    except (ValueError, Stopped):
        purge_clear = False
        result["purge_state"] = {"failures": ["invalid_purge_state_report"]}
    result["purge_fence_clear"] = purge_clear
    # Fail closed before pulls, git fetch, backups or any application mutation.
    if mode == "apply":
        require(purge_clear, "purge_state_refused")
    config = json.loads(run(COMPOSE + ["config", "--format", "json"]))["services"]
    images = {service: config[service].get("image") for service in ("web", "postgres", "qdrant")}
    result["rendered_images"] = images
    version_lines = [line for line in ENV_FILE.read_bytes().splitlines() if line.startswith(b"OCTOPUS_VERSION=")]
    env_version = version_lines[0].split(b"=", 1)[1].decode() if len(version_lines) == 1 else None
    # Report only recognized version values, never arbitrary environment data.
    result["env_version"] = {"exactly_one_line": len(version_lines) == 1,
                             "value": env_version if env_version in (FROM_VERSION, TO_VERSION) else None}
    head = run(["git", "-C", str(OCTOPUS_DIR), "rev-parse", "HEAD"])
    origin = run(["git", "-C", str(OCTOPUS_DIR), "remote", "get-url", "origin"])
    git_environment = os.environ.copy()
    git_environment["GIT_OPTIONAL_LOCKS"] = "0"
    status = run(["git", "-C", str(OCTOPUS_DIR), "status", "--porcelain", "-z", "--untracked-files=all"],
                 env=git_environment, strip=False)
    entries = status.rstrip("\0").split("\0") if status else []
    names = [entry[3:] for entry in entries]
    result["git"] = {"head": head, "matches_from_commit": head == FROM_COMMIT,
                     "origin_matches": origin in OCTOPUS_REMOTES, "status_files": names}
    allowed_status = bool(entries) and all(
        entry == " M docker-compose.selfhost.yml" or
        re.fullmatch(r"\?\? docker-compose\.selfhost\.yml\.before-qdrant-healthcheck-repair\.[0-9]{8}T[0-9]{6}Z", entry) or
        re.fullmatch(r"\?\? backups/(?:octopus-before-1\.3\.3-[0-9]{8}T[0-9]{6}Z\.dump|env-before-1\.3\.3-[0-9]{8}T[0-9]{6}Z)", entry)
        for entry in entries
    ) and " M docker-compose.selfhost.yml" in entries
    web = container("octopus-web-1")
    database_url = running_database_url(web)
    result["database_url_shape_ok"] = database_url is not None
    result["database_url_matches_compose"] = database_url_matches_compose(config["web"].get("environment"), database_url)
    del config
    before_digest = image_digest(web)
    result["running_web_image_digest"] = before_digest
    before = migrations()
    result["migrations_before"] = before
    active = active_background_jobs()
    result["active_background_jobs"] = active
    version = web_version()
    result["web_version"] = version if version in (FROM_VERSION, TO_VERSION) else None
    result["free_bytes"] = {str(path): shutil.disk_usage(path).free for path in (Path("/var/lib/docker"), OCTOPUS_DIR)}
    postgres = container("octopus-postgres-1")
    qdrant = container("octopus-qdrant-1")
    networks = postgres.get("NetworkSettings", {}).get("Networks", {})
    network = next(iter(networks)) if len(networks) == 1 else None
    openai_before = model_count()
    result["openai_rows_before"] = openai_before
    reasons = []
    checks = {
        "unexpected_postgres_image": images["postgres"] == "postgres:17-alpine",
        "unexpected_qdrant_image": images["qdrant"] == "qdrant/qdrant:v1.17.0",
        "unexpected_database_url": result["database_url_shape_ok"] and result.get("database_url_matches_compose", False),
        "unexpected_running_postgres_image": postgres.get("Config", {}).get("Image") == "postgres:17-alpine",
        "unexpected_running_qdrant_image": qdrant.get("Config", {}).get("Image") == "qdrant/qdrant:v1.17.0",
        "unexpected_git_head": head == FROM_COMMIT,
        "unexpected_git_origin": origin in OCTOPUS_REMOTES,
        "unexpected_git_status": allowed_status,
        "active_background_jobs": active in (None, 0),
        "insufficient_disk_space": min(result["free_bytes"].values()) >= 10 * 1024**3,
        "postgres_network_not_single": network is not None and network not in ("host", "none"),
        "web_not_healthy": web_healthy(),
        "unexpected_running_web_image": web.get("Config", {}).get("Image") == images["web"],
    }
    reasons.extend(reason for reason, ok in checks.items() if not ok)
    ready = (images["web"] == IMAGE_REPO + ":" + FROM_VERSION and before_digest == FROM_IMAGE_DIGEST
             and env_version == FROM_VERSION and version == FROM_VERSION and before["finished"] == BEFORE_COUNT
             and before["not_finished_or_rolled_back"] == 0 and before["newest"] == BEFORE_NEWEST)
    upgraded = (images["web"] == TO_IMAGE and before_digest == TO_IMAGE_DIGEST and env_version == TO_VERSION
                and version == TO_VERSION and before["finished"] == AFTER_COUNT
                and before["not_finished_or_rolled_back"] == 0 and openai_before == 10)
    if not ready and not upgraded:
        reasons.append("unexpected_upgrade_state")
    verdict = "blocked" if reasons else "already_upgraded" if upgraded else "ready"
    result.update(verdict=verdict, reasons=reasons)
    if mode == "preflight":
        result["status"] = "passed"
    elif verdict == "already_upgraded":
        result["status"] = "already_done"
    else:
        require(verdict == "ready", "preflight_blocked")
        step = "pull_images"
        run(["docker", "pull", TO_IMAGE])
        digests = json.loads(run(["docker", "image", "inspect", TO_IMAGE]))[0].get("RepoDigests", [])
        require(IMAGE_REPO + "@" + TO_IMAGE_DIGEST in digests, "target_image_digest_mismatch")
        run(["docker", "pull", MIGRATOR_IMAGE])
        step = "prepare_migrations"
        run(["git", "-C", str(OCTOPUS_DIR), "fetch", "--no-tags", "--depth=1", "origin", TO_COMMIT])
        require(run(["git", "-C", str(OCTOPUS_DIR), "rev-parse", TO_COMMIT + "^{commit}"]) == TO_COMMIT, "target_commit_mismatch")
        archive = work / "migrations.tar"
        with archive.open("wb") as stream:
            run(["git", "-C", str(OCTOPUS_DIR), "archive", TO_COMMIT, "packages/db/prisma", "packages/db/prisma.config.ts"], output=stream)
        directory = work / "migrations-src"
        directory.mkdir()
        run(["tar", "-xf", str(archive), "-C", str(directory)])
        dirs = [path for path in (directory / "packages/db/prisma/migrations").iterdir() if path.is_dir()]
        require(len(dirs) == AFTER_COUNT, "migration_directory_count_mismatch")
        for filename in ("package.json", "package-lock.json"):
            shutil.copyfile(work / filename, directory / filename)
        step = "write_barrier"
        # web is the only writer, including the review workers. Recheck jobs
        # immediately before stopping it, then keep it down through all DB work.
        require(active_background_jobs() in (None, 0), "active_background_jobs")
        downtime_started = time.monotonic()
        web_restart_required = True
        result.update(web_stopped_at_step=step, downtime_seconds=None)
        run(COMPOSE + ["stop", "web"])
        require(container("octopus-web-1").get("State", {}).get("Running") is False, "web_still_running")
        step = "backup"
        backup_dir = OCTOPUS_DIR / "backups"
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        backup_dir.chmod(0o700)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        dump = backup_dir / ("octopus-before-1.3.3-" + timestamp + ".dump")
        env_backup = backup_dir / ("env-before-1.3.3-" + timestamp)
        result["database_backup"] = str(dump)
        result["env_backup"] = str(env_backup)
        fd = os.open(dump, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            run(["docker", "exec", "octopus-postgres-1", "pg_dump", "-U", "octopus", "-d", "octopus", "-Fc"], output=stream)
        with dump.open("rb") as stream:
            completed = subprocess.run(["docker", "exec", "-i", "octopus-postgres-1", "pg_restore", "--list"],
                                       stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        require(completed.returncode == 0 and re.search(rb"^\d+;.*\bTABLE\b", completed.stdout, re.M), "backup_verification_failed")
        require(not env_backup.exists(), "env_backup_already_exists")
        run(["cp", "--preserve=mode,ownership,timestamps", "--", str(ENV_FILE), str(env_backup)])
        # Point of no return: every exception from here invokes rollback.
        rollback_required = True
        step = "migrate"
        migrate()
        result["migrations_after"] = require_migrations(AFTER_COUNT)
        step = "models"
        with (work / "openai-models.sql").open("rb") as stream:
            completed = subprocess.run(["docker", "exec", "-i", "octopus-postgres-1", "psql", "-U", "octopus", "-d", "octopus", "-v", "ON_ERROR_STOP=1", "-q"],
                                       stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        require(completed.returncode == 0, "models_insert_failed")
        require(model_count() == 10, "openai_model_rows_missing")
        require(sql("SELECT count(*) FROM available_models WHERE \"modelId\" IN ('claude-opus-5-5','claude-sonnet-5-5')") == "2", "claude_model_rows_missing")
        result["model_rows_added"] = 10 - openai_before
        step = "switch_web"
        # Mark before the atomic edit so even a post-rename failure restores it.
        env_changed = True
        edit_env()
        run(COMPOSE + ["up", "-d", "--no-deps", "web"])
        wait_web(TO_VERSION, TO_IMAGE_DIGEST)
        result["downtime_seconds"] = time.monotonic() - downtime_started
        step = "final_health"
        wait_web(TO_VERSION, TO_IMAGE_DIGEST)
        result["image_digest_before"] = before_digest
        result["image_digest_after"] = TO_IMAGE_DIGEST
        result["status"] = "passed"
except Exception as exc:
    # Never include arbitrary exception/tool text: it can contain env values.
    reason = str(exc) if isinstance(exc, Stopped) else step + "_failed"
    result.update(status="stopped", reason=reason, failed_step=step)
    if mode == "preflight":
        result.update(verdict="blocked", reasons=[reason])
    if web_restart_required:
        # A failed recovery has no healthy endpoint for the downtime interval.
        result["downtime_seconds"] = None
        try:
            pending_signal = None
            for watched_signal in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
                signal.signal(watched_signal, signal.SIG_IGN)
            if rollback_required:
                rollback()
                result["status"] = "rolled_back"
            else:
                restart_old_web()
        except Exception:
            result.update(status="rollback_failed", rollback_failed_step=step)
    print(json.dumps(result, separators=(",", ":")))
    raise SystemExit(1) from None
print(json.dumps(result, separators=(",", ":")))
OCTOPUS_UPGRADE_PYTHON
