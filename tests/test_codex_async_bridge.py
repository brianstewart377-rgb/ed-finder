from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / ".github" / "workflows" / "codex-dispatch.yml"
WORKER = ROOT / ".github" / "workflows" / "codex-laptop.yml"
OPS_DOC = ROOT / "docs" / "development" / "chatgpt-ops-control-plane.md"


def test_codex_request_push_is_acknowledged_by_short_dispatch_workflow() -> None:
    text = DISPATCH.read_text(encoding="utf-8")

    assert "branches:\n      - codex-task-requests" in text
    assert "actions: write" in text
    assert "timeout-minutes: 2" in text
    assert "codex-laptop.yml/dispatches" in text
    assert 'extra=set(d)-{"task","mode","target_branch"}' in text
    assert '"target_branch": os.environ["CODEX_TARGET_BRANCH"]' in text
    assert "CODEX_TARGET_BRANCH=${CODEX_TARGET_BRANCH:-new-branch}" in text
    assert "CODEX_DISPATCH_ACCEPTED=true" in text
    assert "CODEX_WORKER_RUN_ID=" in text
    assert "Do not wait for it here." in text


def test_long_codex_worker_only_runs_from_explicit_dispatch() -> None:
    text = WORKER.read_text(encoding="utf-8")
    trigger = text.split("on:", 1)[1].split("permissions:", 1)[0]

    assert "workflow_dispatch:" in trigger
    assert "request_id:" in trigger
    assert "target_branch:" in trigger
    assert "run-name: Codex Worker · ${{ inputs.request_id }}" in text
    assert "timeout-minutes: 120" in text
    assert "codex exec --sandbox workspace-write" in text
    assert "danger-full-access" not in text
    assert "codex-task-requests" not in trigger


def test_codex_host_has_no_repository_permission_and_push_is_ephemeral() -> None:
    text = WORKER.read_text(encoding="utf-8")
    prepare_job = text.split("  prepare:", 1)[1].split("\n  codex:", 1)[0]
    codex_job = text.split("  codex:", 1)[1].split("\n  push:", 1)[0]
    push_job = text.split("\n  push:", 1)[1]

    assert "runs-on: ubuntu-latest" in prepare_job
    assert "permissions:\n      contents: read" in prepare_job
    assert "runs-on: [self-hosted, Linux, X64]" in codex_job
    assert "permissions:\n      actions: read" in codex_job
    assert "contents: read" not in codex_job
    assert "contents: write" not in codex_job
    assert "CODEX_WORKER_GIT_TOKEN" not in codex_job
    assert "GITHUB_TOKEN" not in codex_job
    assert "${{ github.token }}" not in codex_job
    assert "runs-on: ubuntu-latest" in push_job
    assert "runs-on: [self-hosted, Linux, X64]" not in push_job
    assert "permissions:\n      actions: read\n      contents: write" in push_job
    assert "pull-requests: write" not in text


def test_reused_runner_requires_disposable_boundary_before_token_bearing_actions() -> None:
    text = WORKER.read_text(encoding="utf-8")
    codex_job = text.split("  codex:", 1)[1].split("\n  push:", 1)[0]
    boundary_position = codex_job.index("- name: Require disposable single-use execution boundary")
    download_position = codex_job.index("- name: Download trusted source bundle")
    boundary = codex_job.split(
        "- name: Require disposable single-use execution boundary", 1
    )[1].split("- name: Download trusted source bundle", 1)[0]

    # The boundary gate must run before anything that downloads source or runs Codex.
    assert boundary_position < download_position
    # Trust comes from a host-owned marker read from the runner process
    # environment, not a workflow-level ${{ }} expression the repo could set.
    assert '"${CODEX_WORKER_EPHEMERAL_BOUNDARY:-}" != "1"' in boundary
    assert "${{" not in boundary
    assert "exit 72" in boundary
    assert "CODEX_RUNNER_DISPOSABLE_BOUNDARY=ATTESTED" in boundary
    # The unsound in-job process-killing quarantine must be gone entirely: it
    # could kill sibling runners (same-UID) and miss root/other-UID helpers.
    assert "kill -KILL" not in codex_job
    assert "kill -STOP" not in codex_job
    assert "collect_victims" not in codex_job
    assert "CODEX_RUNNER_PROCESS_QUARANTINE" not in codex_job
    assert codex_job.count("codex exec --sandbox workspace-write") == 2
    assert "danger-full-access" not in codex_job


def test_codex_workers_are_not_globally_serialized() -> None:
    text = WORKER.read_text(encoding="utf-8")

    assert "group: codex-worker" not in text
    assert "cancel-in-progress:" not in text


def test_prepare_job_builds_complete_immutable_source_bundle() -> None:
    text = WORKER.read_text(encoding="utf-8")
    prepare_job = text.split("  prepare:", 1)[1].split("\n  codex:", 1)[0]
    checkout = prepare_job.split("- name: Checkout trusted main", 1)[1].split(
        "- name: Resolve immutable request routing", 1
    )[0]
    resolver = prepare_job.split("- name: Resolve immutable request routing", 1)[1].split(
        "- name: Seal trusted source bundle", 1
    )[0]
    source = prepare_job.split("- name: Seal trusted source bundle", 1)[1].split(
        "- name: Upload trusted source bundle", 1
    )[0]

    assert "fetch-depth: 0" in checkout
    assert "persist-credentials: true" in checkout
    assert 'git fetch --no-tags origin "+refs/heads/$target_branch:refs/remotes/origin/$target_branch"' in resolver
    assert 'echo "main_sha=$main_sha" >> "$GITHUB_OUTPUT"' in resolver
    assert "git update-ref refs/heads/codex-source-main" in source
    assert "git update-ref refs/heads/codex-source-target" in source
    assert 'git bundle create "$bundle" "${refs[@]}"' in source
    assert "git bundle verify" in source
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in prepare_job
    assert "retention-days: 1" in prepare_job


def test_self_hosted_job_reconstructs_source_without_network_git_remote() -> None:
    text = WORKER.read_text(encoding="utf-8")
    codex_job = text.split("  codex:", 1)[1].split("\n  push:", 1)[0]
    reconstruction = codex_job.split("- name: Reconstruct credential-free workspace", 1)[1].split(
        "- name: Set up Python 3.12", 1
    )[0]

    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in codex_job
    assert "codex-source-${{ github.run_id }}-${{ github.run_attempt }}" in codex_job
    # Codex CLI auth lives under the runner user's real HOME; the reconstruct
    # step must NOT override HOME/XDG or codex exec would run unauthenticated.
    assert "export HOME=" not in reconstruction
    assert "isolated_home" not in reconstruction
    assert "export XDG_CONFIG_HOME=" not in reconstruction
    assert "export GIT_CONFIG_NOSYSTEM=1" in reconstruction
    assert "export GIT_CONFIG_GLOBAL=/dev/null" in reconstruction
    assert "export GIT_CONFIG_SYSTEM=/dev/null" in reconstruction
    assert "export GIT_ATTR_NOSYSTEM=1" in reconstruction
    assert reconstruction.index("export GIT_CONFIG_NOSYSTEM=1") < reconstruction.index(
        'init "$GITHUB_WORKSPACE"'
    )
    assert 'rm -rf -- "$GITHUB_WORKSPACE"' in reconstruction
    assert 'init "$GITHUB_WORKSPACE"' in reconstruction
    assert 'fetch --no-tags "$bundle" "${refspecs[@]}"' in reconstruction
    assert "refs/heads/codex-source-main:refs/remotes/origin/main" in reconstruction
    assert "refs/heads/codex-source-target:refs/remotes/origin/$CODEX_BRANCH" in reconstruction
    assert "core.hooksPath=/dev/null" in reconstruction
    assert 'config core.hooksPath /dev/null' in reconstruction
    # The default global attributes file ($HOME/.config/git/attributes) is not
    # covered by GIT_ATTR_NOSYSTEM (system-only) or GIT_CONFIG_GLOBAL=/dev/null
    # (config-only); with HOME no longer isolated it must be neutralized on the
    # working-tree checkout via core.attributesFile=/dev/null.
    assert "core.attributesFile=/dev/null" in reconstruction
    assert 'config core.attributesFile /dev/null' in reconstruction
    assert "Credential-free Codex workspace unexpectedly has a network Git remote." in reconstruction
    assert "remote add" not in codex_job
    assert "https://github.com/${GITHUB_REPOSITORY}.git" not in codex_job
    assert "git fetch origin" not in codex_job


def test_codex_cli_authentication_is_preserved_on_self_hosted_job() -> None:
    text = WORKER.read_text(encoding="utf-8")
    codex_job = text.split("  codex:", 1)[1].split("\n  push:", 1)[0]

    # HOME must never be exported for the self-hosted Codex job (it would hide
    # the runner's `codex login` state). Git isolation is achieved without it.
    assert "export HOME=" not in codex_job
    assert 'echo "HOME=' not in codex_job
    assert "export XDG_CONFIG_HOME=" not in codex_job
    assert "export GIT_CONFIG_GLOBAL=/dev/null" in codex_job
    assert "export GIT_CONFIG_SYSTEM=/dev/null" in codex_job
    assert "export GIT_CONFIG_NOSYSTEM=1" in codex_job


def test_ops_control_plane_docs_match_workflow_change_and_boundary_policy() -> None:
    doc = OPS_DOC.read_text(encoding="utf-8")

    # Token scope must no longer recommend Workflows authority.
    assert "Workflows: read/write" not in doc
    assert "`Contents: read/write`" in doc
    # Docs must state workflow-file changes are rejected by the normal path.
    assert "not supported by this path" in doc
    # Docs must document the host-owned disposable-boundary prerequisite.
    assert "CODEX_WORKER_EPHEMERAL_BOUNDARY" in doc
    assert "ephemeral" in doc


def test_setup_python_receives_no_github_token_on_self_hosted_job() -> None:
    text = WORKER.read_text(encoding="utf-8")
    codex_job = text.split("  codex:", 1)[1].split("\n  push:", 1)[0]
    setup = codex_job.split("- name: Set up Python 3.12", 1)[1].split(
        "- name: Prepare repository state gate", 1
    )[0]

    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in setup
    assert 'python-version: "3.12"' in setup
    assert "token: ''" in setup
    assert "github.token" not in setup


def test_worker_bootstrap_fails_closed_on_wrong_python_before_main_state_gate() -> None:
    text = WORKER.read_text(encoding="utf-8")
    gate = text.split("- name: Prepare repository state gate", 1)[1].split(
        "- name: Verify worker identity", 1
    )[0]
    setup = text.split("  codex:", 1)[1].split("- name: Set up Python 3.12", 1)[1].split(
        "- name: Prepare repository state gate", 1
    )[0]

    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in setup
    assert 'python-version: "3.12"' in setup
    assert "token: ''" in setup
    assert "command -v python" in gate
    assert "sys.version_info[:2] == (3, 12)" in gate
    assert "python -m venv .venv" in gate
    assert "resolve_project_state.py --strict" in gate
    assert "CODEX_MAIN_STATE_GATE=PASS" in gate


def test_selected_target_is_gated_before_dependency_install_or_codex() -> None:
    text = WORKER.read_text(encoding="utf-8")
    select_position = text.index("- name: Select immutable implementation base")
    target_gate_position = text.index("- name: Validate selected implementation state")
    install_position = text.index(
        "- name: Bootstrap pinned Python test environment from selected base"
    )
    codex_position = text.index("- name: Run Codex implementation")

    assert select_position < target_gate_position < install_position < codex_position
    selection = text.split("- name: Select immutable implementation base", 1)[1].split(
        "- name: Validate selected implementation state", 1
    )[0]
    assert 'refs/remotes/origin/$CODEX_BRANCH' in selection
    assert "Sealed target branch SHA does not match the immutable prepared head." in selection
    assert '/usr/bin/git -c core.hooksPath=/dev/null -c core.attributesFile=/dev/null checkout -B "$CODEX_BRANCH" "$CODEX_BASE_SHA"' in selection
    assert "Codex workspace gained a network Git remote." in selection
    target_gate = text.split("- name: Validate selected implementation state", 1)[1].split(
        "- name: Bootstrap pinned Python test environment from selected base", 1
    )[0]
    assert "resolve_project_state.py --strict" in target_gate
    assert "CODEX_TARGET_STATE_GATE=PASS" in target_gate


def test_pinned_test_environment_is_installed_from_selected_base() -> None:
    text = WORKER.read_text(encoding="utf-8")
    target_gate_position = text.index("CODEX_TARGET_STATE_GATE=PASS")
    install_position = text.index(
        ".venv/bin/python -m pip install --requirement tests/requirements-ci.txt"
    )

    assert target_gate_position < install_position
    bootstrap = text.split(
        "- name: Bootstrap pinned Python test environment from selected base", 1
    )[1].split("- name: Verify pinned Python test environment", 1)[0]
    assert ".venv/bin/python -m pip install --requirement tests/requirements-ci.txt" in bootstrap


def test_worker_activates_and_verifies_the_pinned_venv() -> None:
    text = WORKER.read_text(encoding="utf-8")
    bootstrap = text.split(
        "- name: Bootstrap pinned Python test environment from selected base", 1
    )[1].split("- name: Verify pinned Python test environment", 1)[0]
    verification = text.split(
        "- name: Verify pinned Python test environment", 1
    )[1].split("- name: Run Codex investigation", 1)[0]

    assert 'echo "VIRTUAL_ENV=$GITHUB_WORKSPACE/.venv" >> "$GITHUB_ENV"' in bootstrap
    assert 'echo "$GITHUB_WORKSPACE/.venv/bin" >> "$GITHUB_PATH"' in bootstrap
    assert "python -m pip check" in verification
    assert "python -m pytest --version" in verification
    assert "python -m ruff --version" in verification


def test_routing_is_resolved_before_codex_and_task_never_enters_outputs() -> None:
    text = WORKER.read_text(encoding="utf-8")
    prepare = text.split("  prepare:", 1)[1].split("\n  codex:", 1)[0]

    assert "Resolve immutable request routing" in prepare
    assert 'INPUT_TASK: ${{ inputs.task }}' in prepare
    assert 'echo "task=' not in prepare
    assert 'echo "branch=$branch" >> "$GITHUB_OUTPUT"' in prepare
    assert 'echo "expected_remote_sha=$expected_remote_sha" >> "$GITHUB_OUTPUT"' in prepare


def test_existing_pr_branch_target_is_validated_and_protected_branches_are_denied() -> None:
    text = WORKER.read_text(encoding="utf-8")
    resolver = text.split("- name: Resolve immutable request routing", 1)[1].split(
        "- name: Seal trusted source bundle", 1
    )[0]

    assert "INPUT_TARGET_BRANCH: ${{ inputs.target_branch }}" in resolver
    assert 'git check-ref-format --branch "$target_branch"' in resolver
    assert (
        "main|master|codex-task-requests|chatgpt-ops-requests|"
        "chatgpt-ed-new-ops-requests" in resolver
    )
    assert "target_branch is only valid for implement mode" in resolver


def test_existing_pr_branch_is_updated_with_atomic_lease_from_prepare_job() -> None:
    text = WORKER.read_text(encoding="utf-8")
    reconstruction = text.split("- name: Reconstruct trusted push repository", 1)[1].split(
        "- name: Push sealed implementation with exact-head lease", 1
    )[0]
    push = text.split("- name: Push sealed implementation with exact-head lease", 1)[1].split(
        "- name: Implementation branch summary", 1
    )[0]

    assert 'CODEX_BRANCH: ${{ needs.prepare.outputs.branch }}' in reconstruction
    assert 'CODEX_EXPECTED_REMOTE_SHA: ${{ needs.prepare.outputs.expected_remote_sha }}' in reconstruction
    assert 'workflow_diff_base="$CODEX_EXPECTED_REMOTE_SHA"' in reconstruction
    assert 'merge-base --is-ancestor "$CODEX_BASE_SHA" "$candidate_sha"' in reconstruction
    assert '--force-with-lease="refs/heads/$CODEX_BRANCH:$CODEX_EXPECTED_REMOTE_SHA"' in push
    assert 'origin "refs/remotes/codex/result:refs/heads/$CODEX_BRANCH"' in push


def test_existing_pr_update_requires_non_github_token_so_checks_retrigger() -> None:
    text = WORKER.read_text(encoding="utf-8")
    push = text.split("- name: Push sealed implementation with exact-head lease", 1)[1].split(
        "- name: Implementation branch summary", 1
    )[0]

    assert "CODEX_WORKER_GIT_TOKEN: ${{ secrets.CODEX_WORKER_GIT_TOKEN }}" in push
    assert 'if [ "$CODEX_UPDATE_EXISTING" = true ] && [ -z "$CODEX_WORKER_GIT_TOKEN" ]; then' in push
    assert "Existing PR branch updates require CODEX_WORKER_GIT_TOKEN" in push
    assert "REQUIRES_PRIVILEGED" not in push
    assert 'push_token="${CODEX_WORKER_GIT_TOKEN:-$GITHUB_TOKEN}"' in push


def test_codex_workflow_changes_are_rejected_before_any_privileged_push() -> None:
    text = WORKER.read_text(encoding="utf-8")
    reconstruction = text.split("- name: Reconstruct trusted push repository", 1)[1].split(
        "- name: Push sealed implementation with exact-head lease", 1
    )[0]

    assert "'.github/workflows/'" in reconstruction
    assert "trusted push refuses unreviewed workflow activation" in reconstruction
    assert "exit 71" in reconstruction
    assert "requires_privileged" not in reconstruction.lower()


def test_sealed_result_crosses_to_ephemeral_push_job_without_write_credential() -> None:
    text = WORKER.read_text(encoding="utf-8")
    codex_job = text.split("  codex:", 1)[1].split("\n  push:", 1)[0]
    push_job = text.split("\n  push:", 1)[1]
    seal = codex_job.split("- name: Seal implementation result", 1)[1].split(
        "- name: Upload sealed implementation result", 1
    )[0]

    assert "Implementation repository is still shallow; refusing an incomplete bundle." in seal
    assert "update-ref refs/heads/codex-sealed-result" in seal
    assert "bundle create" in seal
    assert "CODEX_WORKER_GIT_TOKEN" not in codex_job
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in codex_job
    assert "retention-days: 1" in codex_job
    assert "needs: [prepare, codex]" in push_job
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in push_job
    assert "CODEX_WORKER_GIT_TOKEN: ${{ secrets.CODEX_WORKER_GIT_TOKEN }}" in push_job


def test_privileged_push_uses_fresh_trusted_repository_and_pinned_remote() -> None:
    text = WORKER.read_text(encoding="utf-8")
    reconstruction = text.split("- name: Reconstruct trusted push repository", 1)[1].split(
        "- name: Push sealed implementation with exact-head lease", 1
    )[0]
    push = text.split("- name: Push sealed implementation with exact-head lease", 1)[1].split(
        "- name: Implementation branch summary", 1
    )[0]

    assert 'trusted_root="$RUNNER_TEMP/codex-trusted-push-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"' in reconstruction
    assert 'remote add origin "https://github.com/${GITHUB_REPOSITORY}.git"' in reconstruction
    assert "GIT_CONFIG_NOSYSTEM=1" in reconstruction
    assert "GIT_CONFIG_GLOBAL=/dev/null" in reconstruction
    assert "GIT_CONFIG_SYSTEM=/dev/null" in reconstruction
    assert "core.hooksPath=/dev/null" in reconstruction
    assert "PATH=/usr/bin:/bin" in reconstruction
    assert "'.github/workflows/'" in reconstruction
    assert "trusted push refuses unreviewed workflow activation" in reconstruction
    assert "https://github.com/" not in push
    assert "GIT_ASKPASS" in push
    assert "PATH=/usr/bin:/bin" in push
