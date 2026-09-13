"""Contract and behavioural tests for the bounded V3 Search follower pause.

Pausing stops a production worker, so the action is checked twice over: the
source must stay inside the narrow pause boundary, and the script is executed
against a stubbed docker and psql so its fail-closed paths are exercised rather
than merely asserted as text.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ACTION = ROOT / "scripts/operator/actions/v3-system-search-f1-pause.sh"
WORKFLOW = ROOT / ".github/workflows/chatgpt-ed-new-ops.yml"
OPERATION = "v3-system-search-f1-pause"

HARNESS = r'''
set -euo pipefail

docker() {
  case "$1 $2" in
    "context show") printf 'default\n' ;;
    "context inspect") printf 'unix:///var/run/docker.sock\n' ;;
    *) docker_case "$@" ;;
  esac
}

docker_case() {
  case "$1" in
    exec) db_query_case "$@" ;;
    ps) printf '%s' "${FAKE_WORKERS}" ;;
    stop)
      printf 'stopped %s\n' "$4"
      : > "${FAKE_STATE}/stopped"
      ;;
    inspect)
      case "$3" in
        *State.Running*)
          case "$4" in
            *postgres) printf 'true\n' ;;
            *) if [ -f "${FAKE_STATE}/stopped" ]; then printf 'false\n'; else printf 'true\n'; fi ;;
          esac ;;
        *generation-key*) printf '%s\n' "${FAKE_GENERATION_KEY}" ;;
        *) printf '\n' ;;
      esac ;;
    *) printf 'unexpected docker %s\n' "$*" >&2; exit 70 ;;
  esac
}

db_query_case() {
  local argument
  for argument in "$@"; do
    case "$argument" in
      *lifecycle_state*) printf 'VALIDATING\n'; return ;;
      *search_build_chunk*)
        if [ -f "${FAKE_STATE}/stopped" ]; then printf '%s\n' "${FAKE_FRONTIER_AFTER}"
        else printf '%s\n' "${FAKE_FRONTIER_BEFORE}"; fi
        return ;;
    esac
  done
  printf 'unexpected db query\n' >&2
  exit 70
}

hostname() {
  if [ "${1:-}" = "-f" ]; then printf '%s\n' "${FAKE_FQDN}"
  else printf '%s\n' "${FAKE_HOSTNAME}"; fi
}

export -f docker docker_case db_query_case hostname

set -- pause
source "${FAKE_ACTION}"
'''


def run_pause(tmp_path, *, workers="edfinder-v3-system-search-p4-opt1\n",
              before="19099\t19098", after="19099\t19098",
              generation_key="ratings_v4_prod_p4_opt1"):
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    harness = tmp_path / "harness.sh"
    harness.write_text(HARNESS, encoding="utf-8")
    return subprocess.run(
        ["bash", str(harness)], text=True, capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "FAKE_ACTION": str(ACTION),
            "FAKE_STATE": str(state),
            "FAKE_WORKERS": workers,
            "FAKE_FRONTIER_BEFORE": before,
            "FAKE_FRONTIER_AFTER": after,
            "FAKE_GENERATION_KEY": generation_key,
            "FAKE_HOSTNAME": "ed-finder-prod",
            "FAKE_FQDN": "nb79a3d.mevnode.com",
        },
    )


def test_pause_operation_is_allowlisted_through_trusted_main():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert f"          - {OPERATION}\n" in workflow
    assert f"|{OPERATION})" in workflow
    assert "trusted-main/scripts/operator/actions/v3-system-search-f1-pause.sh" in workflow
    assert "ref: main" in workflow


def test_pause_operation_can_only_stop_the_worker():
    source = ACTION.read_text(encoding="utf-8")
    assert 'WORKER="edfinder-v3-system-search-p4-opt1"' in source
    assert 'TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"' in source
    assert 'OPERATION_LABEL="ed-finder.operation=v3-system-search-f1"' in source
    assert "docker stop --time \"$STOP_GRACE_SECONDS\"" in source
    assert 'expected exactly one running V3 Search worker' in source
    assert "committed Search progress regressed while pausing" in source
    assert "committed_progress_preserved=true" in source
    assert "resume_operation=v3-system-search-f1-start" in source
    assert "worker_removed=false" in source
    assert "publication_performed=false" in source
    assert "canonical_writes_performed=false" in source
    assert "application_service_changes_performed=false" in source
    for forbidden in (
        "docker rm",
        "docker restart",
        "docker compose",
        "publish_derived_generation(",
        "INSERT INTO ",
        "UPDATE ",
        "DELETE FROM ",
        "TRUNCATE ",
        "DROP ",
        "CREATE INDEX",
        "ALTER TABLE",
    ):
        assert forbidden not in source


def test_pause_operation_has_valid_shell_syntax():
    subprocess.run(["bash", "-n"], input=ACTION.read_text(encoding="utf-8"),
                   text=True, check=True)


def test_pause_stops_the_labelled_worker_and_reports_preserved_progress(tmp_path):
    result = run_pause(tmp_path)
    assert result.returncode == 0, result.stderr
    for line in (
        "operation=v3-system-search-f1-pause",
        "result=stopped",
        "worker=edfinder-v3-system-search-p4-opt1",
        "ratings_lifecycle_state=VALIDATING",
        "worker_removed=false",
        "committed_chunks_before=19099",
        "committed_chunk_frontier_before=19098",
        "committed_chunks_after=19099",
        "committed_progress_preserved=true",
        "publication_performed=false",
        "canonical_writes_performed=false",
    ):
        assert line in result.stdout
    assert "stopped edfinder-v3-system-search-p4-opt1" in result.stdout


def test_pause_fails_closed_without_exactly_one_worker(tmp_path):
    for workers in ("", "one\ntwo\n", "some-other-worker\n"):
        result = run_pause(tmp_path, workers=workers)
        assert result.returncode == 64, result.stdout
        assert "expected exactly one running V3 Search worker" in result.stderr
        assert "result=stopped" not in result.stdout


def test_pause_fails_closed_on_generation_label_mismatch(tmp_path):
    result = run_pause(tmp_path, generation_key="some-other-generation")
    assert result.returncode == 64
    assert "worker generation label mismatch" in result.stderr
    assert "result=stopped" not in result.stdout


def test_pause_refuses_to_report_regressed_committed_progress(tmp_path):
    result = run_pause(tmp_path, before="19099\t19098", after="19004\t19003")
    assert result.returncode == 64
    assert "committed Search progress regressed while pausing" in result.stderr