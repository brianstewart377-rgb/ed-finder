import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/normalize_octopus_review_head.py"
WORKFLOW = ROOT / ".github/workflows/octopus-review-head-normalizer.yml"


def _module():
    spec = importlib.util.spec_from_file_location("octopus_head_normalizer", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalizer_replaces_bogus_footer_with_exact_full_sha():
    module = _module()
    sha = "a" * 40
    body = "## 🐙 Octopus Review\n\nSummary\n\nLast reviewed commit: abc1234\n\n### Checklist\n- [x] done\n"
    normalized = module.normalize_review_body(body, sha)
    assert normalized.count("Last reviewed commit:") == 1
    assert f"Last reviewed commit: {sha}" in normalized
    assert "abc1234" not in normalized
    assert normalized.index(f"Last reviewed commit: {sha}") < normalized.index("### Checklist")


def test_normalizer_inserts_footer_when_model_omits_it():
    module = _module()
    sha = "b" * 40
    body = "## 🐙 Octopus Review\n\nSummary\n\n### Checklist\n- [x] done\n"
    normalized = module.normalize_review_body(body, sha)
    assert normalized.count("Last reviewed commit:") == 1
    assert f"Last reviewed commit: {sha}" in normalized


def test_normalizer_collapses_multiple_model_footers():
    module = _module()
    sha = "c" * 40
    body = (
        "## 🐙 Octopus Review\n\n"
        "Last reviewed commit: deadbeef\n"
        "Text\n"
        "Last reviewed commit: cafebabe\n"
    )
    normalized = module.normalize_review_body(body, sha)
    assert normalized.count("Last reviewed commit:") == 1
    assert normalized.rstrip().endswith(f"Last reviewed commit: {sha}")


def test_normalizer_rejects_non_octopus_body_and_bad_sha():
    module = _module()
    for body, sha in [
        ("ordinary comment", "a" * 40),
        ("## 🐙 Octopus Review\n", "abc1234"),
        ("## 🐙 Octopus Review\n", "A" * 40),
    ]:
        try:
            module.normalize_review_body(body, sha)
        except module.NormalizerError:
            pass
        else:
            raise AssertionError("unsafe input was accepted")


def test_workflow_is_default_branch_event_postprocessor_with_minimal_permissions():
    source = WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(source)
    assert "pull_request_target" not in source
    assert "issue_comment:" in source
    assert "types: [created, edited]" in source
    assert "octopus-fc8f7111f1[bot]" in source
    assert "ref: main" in source
    assert "persist-credentials: false" in source
    assert "issues: write" in source
    assert "pull-requests: read" in source
    assert "contents: read" in source
    assert "contents: write" not in source
    assert "pull-requests: write" not in source
    assert "normalize_octopus_review_head.py" in source
    assert isinstance(data, dict)


def test_script_never_takes_comment_body_or_token_as_shell_arguments():
    source = SCRIPT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "GITHUB_TOKEN" in source
    assert "--body" not in workflow
    assert "github.event.comment.body" not in workflow
    assert "github.event.comment.body" not in source
    assert "PATCH" in source
    assert "/issues/comments/" in source
    assert "/pulls/" in source
