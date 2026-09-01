from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_PAIRS = (
    (
        ROOT / ".github/workflows/chatgpt-ops-dispatch.yml",
        ROOT / ".github/workflows/chatgpt-ops.yml",
        "chatgpt-ops-requests",
        ".github/ops-requests/*.json",
        "hetzner-operator",
    ),
    (
        ROOT / ".github/workflows/chatgpt-ed-new-ops-dispatch.yml",
        ROOT / ".github/workflows/chatgpt-ed-new-ops.yml",
        "chatgpt-ed-new-ops-requests",
        ".github/ed-new-ops-requests/*.json",
        "ed-new-operator",
    ),
)


def _workflow(path: Path) -> dict:
    # BaseLoader avoids YAML 1.1 treating the GitHub Actions `on` key as True.
    parsed = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return parsed


def _jobs(path: Path) -> dict:
    jobs = _workflow(path).get("jobs")
    assert isinstance(jobs, dict)
    return jobs


def test_request_branch_workflows_are_unprivileged_push_only_dispatchers() -> None:
    for dispatcher, _, branch, request_glob, environment in WORKFLOW_PAIRS:
        document = _workflow(dispatcher)
        source = dispatcher.read_text(encoding="utf-8")
        triggers = document["on"]

        assert set(triggers) == {"push"}
        assert triggers["push"]["branches"] == [branch]
        assert triggers["push"]["paths"] == [request_glob]
        assert all("environment" not in job for job in _jobs(dispatcher).values())
        assert "secrets." not in source
        assert environment not in source


def test_privileged_executors_are_dispatch_only_with_exact_environments() -> None:
    for _, executor, _, _, environment in WORKFLOW_PAIRS:
        document = _workflow(executor)
        jobs = _jobs(executor)

        assert set(document["on"]) == {"workflow_dispatch"}
        environment_jobs = [
            job for job in jobs.values() if job.get("environment") == environment
        ]
        assert len(environment_jobs) == 1
        assert all(
            job.get("environment") in (None, environment) for job in jobs.values()
        )
        assert all(
            job.get("if") == "github.ref == 'refs/heads/main'" for job in jobs.values()
        )


def test_dispatchers_target_the_trusted_main_executor_revision() -> None:
    for dispatcher, executor, _, _, _ in WORKFLOW_PAIRS:
        source = dispatcher.read_text(encoding="utf-8")

        assert f"actions/workflows/{executor.name}/dispatches" in source
        assert '"ref": "main"' in source
        assert '"ref": os.environ' not in source


def test_each_push_resolves_exactly_one_bounded_json_request() -> None:
    for dispatcher, _, _, request_glob, _ in WORKFLOW_PAIRS:
        source = dispatcher.read_text(encoding="utf-8")

        # Diff the complete push range, including a branch-creation zero before SHA.
        assert "fetch-depth: 0" in source
        assert "0000000000000000000000000000000000000000" in source
        assert '"$base_sha" "$CURRENT_SHA"' in source

        # Every changed path is considered before the sole request is selected.
        assert "git diff --name-only" in source
        assert "changed_files" in source
        assert '"${#changed_files[@]}" -eq 1' in source
        assert request_glob in source
        assert "Unsupported request keys" in source
        assert "Unsupported operation" in source


def test_request_branch_workflow_revision_cannot_gain_operator_secrets() -> None:
    for dispatcher, executor, _, _, environment in WORKFLOW_PAIRS:
        dispatcher_source = dispatcher.read_text(encoding="utf-8")
        executor_source = executor.read_text(encoding="utf-8")

        # The request ref only starts a main-ref run. Secret-consuming steps exist
        # exclusively in the workflow whose definition GitHub loads from main.
        assert "secrets." not in dispatcher_source
        assert environment not in dispatcher_source
        assert "secrets." in executor_source
        assert environment in executor_source
        assert "github.event.before" not in executor_source
        assert "github.sha" not in executor_source


def test_executor_queue_is_durable_and_serializes_without_replaceable_concurrency() -> None:
    for _, executor, _, _, _ in WORKFLOW_PAIRS:
        document = _workflow(executor)
        jobs = _jobs(executor)
        source = executor.read_text(encoding="utf-8")

        # A fixed Actions concurrency group retains only one pending run and can
        # silently replace the middle request. The FIFO gate instead waits for all
        # older run IDs before the environment-bound operation starts.
        assert "concurrency" not in document
        queue_jobs = [job for job in jobs.values() if job.get("environment") is None]
        privileged_jobs = [job for job in jobs.values() if job.get("environment")]
        assert len(queue_jobs) == 1
        assert len(privileged_jobs) == 1
        assert privileged_jobs[0].get("needs") in jobs
        assert "github.run_id" in source
        assert "workflow_dispatch" in source
        assert "in_progress" in source
        assert "queued" in source
