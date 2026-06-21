from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / 'scripts' / 'dev' / 'review_environment.py'
API_SRC = ROOT / 'apps' / 'api' / 'src'
FRONTEND_DIR = ROOT / 'frontend-v2'
COMPOSE_FILE = ROOT / 'docker-compose.review.yml'
VERIFY_BROWSER_SPEC = FRONTEND_DIR / 'e2e' / 'review-environment.spec.js'
VERIFY_TMP_ROOT = Path('/tmp/edfinder-local-review')
LATEST_REPORT_POINTER = VERIFY_TMP_ROOT / 'latest-report.json'
PROJECT_NAME = 'edfinder-review'
CONFIRM_FLAG = '--confirm-local-review-environment'
EXPECTED_REVIEW_DB_NAME = 'edfinder_local_review'
EXPECTED_REVIEW_API_HOST = '127.0.0.1'
EXPECTED_REVIEW_API_PORT = 8001
EXPECTED_REVIEW_API_BIND = '127.0.0.1:8001:8000'
EXPECTED_REVIEW_STACK_MARKER = 'edfinder-review'
EXPECTED_FRONTEND_PREVIEW_HOST = '127.0.0.1'
EXPECTED_FRONTEND_PREVIEW_PORT = 4173
REVIEW_LAB_BROWSER_MARKER = 'EDFINDER_REVIEW_LAB_RUN'
REVIEW_LAB_BROWSER_SUMMARY_SCHEMA_VERSION = 1
REQUIRED_SERVICES = ('review-postgres', 'review-redis', 'review-api')
REQUIRED_REVIEW_SYSTEM_NAMES = ('Review Alpha', 'Review Beta', 'Review Gamma', 'Review Delta')
REQUIRED_PHASE_NAMES = (
    'static',
    'stack',
    'api_contracts',
    'browser_desktop',
    'browser_accessibility',
    'browser_console',
    'teardown',
    'product_observations',
)
STATIC_TEST_FILES = (
    'tests/test_local_review_test_environment.py',
    'tests/test_db_isolation_guardrails.py',
    'tests/test_project_state_resolver.py',
)
DISALLOWED_REFERENCES = (
    'ed-postgres',
    'ed-redis',
    'ed-finder_postgres_data',
    'ed-finder_redis_data',
    'env_file:',
)
REVIEW_SYSTEM_IDS = {
    'alpha': 7200000000001,
    'beta': 7200000000002,
    'gamma': 7200000000003,
    'delta': 7200000000004,
}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from review_runtime_guard import EXPECTED_REVIEW_DATABASE_HOST, EXPECTED_REVIEW_DATABASE_NAME, EXPECTED_REVIEW_REDIS_HOST  # noqa: E402

ReviewMode = Literal['quick', 'full']
PhaseStatus = Literal['passed', 'failed', 'skipped']
SupportRouteValidationMode = Literal[
    'api_contract_validated',
    'browser_only_validated',
    'intentionally_not_exercised',
]


class ReviewLabError(RuntimeError):
    def __init__(self, message: str, *, failure_code: str | None = None, safe_diagnostics: Any | None = None) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.safe_diagnostics = safe_diagnostics


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    purpose: str
    synthetic_data_profile: str
    required_review_only_routes: tuple[str, ...]
    api_contracts: tuple[str, ...]
    browser_journey: tuple[str, ...]
    expected_network_policy: tuple[str, ...]
    evidence_posture: str
    accessibility_checks: tuple[str, ...]
    viewport_checks: tuple[str, ...]
    product_observation_policy: str
    browser_flow_keys: tuple[str, ...] = ()
    requires_product_observations: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'purpose': self.purpose,
            'synthetic_data_profile': self.synthetic_data_profile,
            'required_review_only_routes': list(self.required_review_only_routes),
            'api_contracts': list(self.api_contracts),
            'browser_journey': list(self.browser_journey),
            'expected_network_policy': list(self.expected_network_policy),
            'evidence_posture': self.evidence_posture,
            'accessibility_checks': list(self.accessibility_checks),
            'viewport_checks': list(self.viewport_checks),
            'product_observation_policy': self.product_observation_policy,
            'browser_flow_keys': list(self.browser_flow_keys),
            'requires_product_observations': self.requires_product_observations,
        }


@dataclass(frozen=True)
class SupportRoute:
    route: str
    frontend_caller: str
    required_for_reviewed_flow: bool
    expected_status: int
    review_only_handling: str
    allowed_response_characteristics: tuple[str, ...]
    scenario_coverage: tuple[str, ...]
    validation_mode: SupportRouteValidationMode

    def to_dict(self) -> dict[str, Any]:
        return {
            'route': self.route,
            'frontend_caller': self.frontend_caller,
            'required_for_reviewed_flow': self.required_for_reviewed_flow,
            'expected_status': self.expected_status,
            'review_only_handling': self.review_only_handling,
            'allowed_response_characteristics': list(self.allowed_response_characteristics),
            'scenario_coverage': list(self.scenario_coverage),
            'validation_mode': self.validation_mode,
        }


@dataclass(frozen=True)
class VerifyContext:
    mode: ReviewMode
    scenarios: tuple[ScenarioDefinition, ...]
    run_id: str
    run_dir: Path
    report_path: Path

    def command_text(self) -> str:
        scenario_label = 'all' if tuple(s.name for s in self.scenarios) == () else ','.join(s.name for s in self.scenarios)
        return f"scripts/dev/review_environment.py verify --mode {self.mode} --scenario {scenario_label or 'all'} {CONFIRM_FLAG}"


def elapsed_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)
