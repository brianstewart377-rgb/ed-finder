import re
import shlex
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / ".github" / "workflows" / "codex-laptop.yml"
DISPATCH = ROOT / ".github" / "workflows" / "codex-dispatch.yml"
EXPECTED_CODEX_MODEL = "gpt-5.6-sol"
EXPECTED_CODEX_REASONING_EFFORT = "high"


class _NoBoolCoercionLoader(yaml.SafeLoader):
    pass


_NoBoolCoercionLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:bool"
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _load(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_NoBoolCoercionLoader)


def _execution_steps() -> list[dict]:
    steps = _load(WORKER)["jobs"]["codex"]["steps"]
    return [step for step in steps if step.get("name", "").startswith("Run Codex ")]


def _codex_commands(script: str) -> list[str]:
    commands = re.findall(r"(?m)^\s*(codex exec .*?(?:\\\n\s+.*?)*)(?=\n[^ ]|\Z)", script)
    return [re.sub(r"\\\n\s*", " ", command) for command in commands]


def test_active_worker_workflow_parses_and_has_both_execution_modes() -> None:
    workflow = _load(WORKER)
    assert set(workflow["on"]["workflow_dispatch"]["inputs"]) == {
        "task",
        "mode",
        "target_branch",
        "request_id",
    }
    assert [step["name"] for step in _execution_steps()] == [
        "Run Codex investigation",
        "Run Codex implementation",
    ]


def test_every_codex_exec_has_the_same_hard_pinned_model_contract() -> None:
    commands = [
        command
        for step in _execution_steps()
        for command in _codex_commands(step["run"])
    ]
    assert len(commands) == 2

    governed_options = []
    for command in commands:
        tokens = shlex.split(command)
        assert tokens[:2] == ["codex", "exec"]
        assert tokens[tokens.index("--model") + 1] == EXPECTED_CODEX_MODEL
        assert tokens[tokens.index("--config") + 1] == (
            f'model_reasoning_effort="{EXPECTED_CODEX_REASONING_EFFORT}"'
        )
        assert "--strict-config" in tokens
        assert "--ignore-user-config" in tokens
        governed_options.append(tokens[2 : tokens.index("--sandbox")])

    assert governed_options[0] == governed_options[1]


def test_request_cannot_override_model_or_enable_a_fallback() -> None:
    worker_text = WORKER.read_text(encoding="utf-8")
    dispatch_text = DISPATCH.read_text(encoding="utf-8")
    commands = [
        command
        for step in _execution_steps()
        for command in _codex_commands(step["run"])
    ]

    assert 'extra=set(d)-{"task","mode","target_branch"}' in dispatch_text
    assert not re.search(r"inputs\.(?:model|.*effort)|CODEX_(?:MODEL|.*EFFORT):", worker_text)
    assert all("${" not in command and "||" not in command for command in commands)
    assert worker_text.count("codex exec ") == 3  # two calls plus the help capability probe
    assert "gpt-6-astra" not in worker_text
    assert "REQUIRED_CODEX_REASONING_EFFORT='max'" not in worker_text
    assert 'model_reasoning_effort="max"' not in worker_text
    assert 'model_reasoning_effort="xhigh"' not in worker_text


def test_cli_capability_gate_and_sanitised_attestations_precede_execution() -> None:
    workflow = _load(WORKER)
    steps = workflow["jobs"]["codex"]["steps"]
    names = [step.get("name") for step in steps]
    gate_index = names.index("Verify required Codex model contract")
    gate = steps[gate_index]["run"]

    assert gate_index < names.index("Run Codex investigation")
    assert gate_index < names.index("Run Codex implementation")
    for required in (
        "codex exec --help",
        "--model <MODEL>",
        "--config <key=value>",
        "--strict-config",
        "--ignore-user-config",
        "codex --version",
        "exit 69",
    ):
        assert required in gate

    for step, mode, branch in zip(
        _execution_steps(), ("investigate", "implement"), ("main", None), strict=True
    ):
        script = step["run"]
        invocation = script.index("codex exec --ignore-user-config")
        attestation = script.index("CODEX_ATTESTATION")
        assert attestation < invocation
        assert (
            f"readonly REQUIRED_CODEX_MODEL='{EXPECTED_CODEX_MODEL}'"
            in script[:attestation]
        )
        assert (
            "readonly REQUIRED_CODEX_REASONING_EFFORT="
            f"'{EXPECTED_CODEX_REASONING_EFFORT}'"
            in script[:attestation]
        )
        assert (
            '"$CODEX_CLI_VERSION" "$REQUIRED_CODEX_MODEL" '
            '"$REQUIRED_CODEX_REASONING_EFFORT"'
            in script[attestation:invocation]
        )
        for field in (
            "cli_version=%s",
            "model=%s",
            "reasoning_effort=%s",
            "request_id=%s",
            f"mode={mode}",
            "branch=%s",
            "base_sha=%s",
        ):
            assert field in script[:invocation]
        assert "tr -c 'A-Za-z0-9._-' '_'" in script[:invocation]
        if branch is not None:
            assert step["env"]["CODEX_BRANCH"] == branch


def test_implementation_result_sha_is_exposed_and_written_to_job_summary() -> None:
    workflow = _load(WORKER)
    codex_job = workflow["jobs"]["codex"]
    push_steps = workflow["jobs"]["push"]["steps"]
    seal = next(step for step in codex_job["steps"] if step.get("id") == "sealed")
    summary = next(step for step in push_steps if step.get("name") == "Implementation branch summary")

    assert codex_job["outputs"]["result_sha"] == "${{ steps.sealed.outputs.result_sha }}"
    assert 'echo "result_sha=$candidate_sha" >> "$GITHUB_OUTPUT"' in seal["run"]
    assert 'echo "CODEX_RESULT_SHA=$candidate_sha"' in seal["run"]
    assert summary["env"]["CODEX_RESULT_SHA"] == "${{ needs.codex.outputs.result_sha }}"
    assert 'echo "CODEX_RESULT_SHA=$CODEX_RESULT_SHA"' in summary["run"]
    assert '>> "$GITHUB_STEP_SUMMARY"' in summary["run"]
