from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewLabTimeouts:
    static: int = 60
    stack_readiness: int = 60
    image_pull: int = 60
    image_pull_attempts: int = 3
    image_pull_backoff_seconds: float = 3.0
    image_build: int = 240
    api_contracts: int = 30
    sse_probe: int = 3
    frontend_build: int = 90
    preview_readiness: int = 30
    cypress: int = 360
    teardown: int = 60


TIMEOUTS = ReviewLabTimeouts()
