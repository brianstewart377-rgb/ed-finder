#!/usr/bin/env python3.14
"""Credential-free, read-only Ratings V4 release evidence (CPython 3.14).

Run manually after a governed release, never against production from tests/CI.
HTTPS is required except literal loopback HTTP addresses for disposable tests.
Eight sequential GETs, no retries, redirects, cookies, authentication or proxies.

Sol, Achenar and Alioth are retained in the frozen real-system cohort at
docs/development/ratings-v4-freeze/cohort.json. Its canonical source is the
complete published generation's source, as recorded in
docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json
(ratings_v4_prod_p4_parallel_v1, 198,528,286 completed systems). These fixed
identities exercise mixed, ELW-heavy and depleted-reserve systems respectively.
Their presence is checked afresh on every run; scores are not hard-coded.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.client import HTTPException
import ipaddress
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


DEFAULT_BASE_URL = "https://ed-finder.app"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TIMEOUT_SECONDS = 30.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
SYSTEMS = ((10477373803, "Sol"), (164098653, "Achenar"), (1109989017963, "Alioth"))
ECONOMIES = (
    "Agriculture", "Refinery", "Industrial", "HighTech", "Military", "Tourism", "Extraction",
)
IDENTITY_FIELDS = {
    "derived_generation_id": "str",
    "publication_sequence": "int",
    "canonical_generation_id": "str",
    "canonical_publication_sequence": "int",
    "scorer_version": "str",
    "mechanics_version": "str",
}

# Standard-library mirror of the required JSON fields in the Pydantic response
# models: apps/api/src/routers/ratings_v4.py and apps/api/src/models.py (health).
# Extra fields are tolerated as Pydantic does. Tests compare the required fields
# to the source models so a contract change cannot silently weaken this check.
MODEL_FIELDS = {
    "HealthResponse": {"status": "str", "database": "str", "version": "str", "build_sha": "str"},
    "GenerationResponse": {
        **IDENTITY_FIELDS, "published_at": "datetime", "validation_receipt": "object",
    },
    "RatingSummaryResponse": {
        "economy": "str", "potential_score": "int", "specialisation_quality": "int | None",
        "specialisation_quality_min": "int", "specialisation_quality_max": "int",
        "evidence_completeness": "float", "confidence": "float",
    },
    "EvidenceFeatureResponse": {
        "feature_type": "str", "known": "bool", "weight": "float", "confidence": "float",
        "provenance": "str | None", "value": "str | bool | None",
    },
    "SpecialisationConstraintResponse": {
        "rule_id": "str", "satisfied": "bool | None", "feature_type": "str",
        "confidence": "float", "provenance": "str | None",
    },
    "CandidateContributionResponse": {
        "candidate_id": "str", "native": "bool", "modifier": "bool", "base_score": "int",
        "positive_rules": "list[str]", "negative_rules": "list[str]",
        "positive_adjustment": "int", "negative_adjustment": "int", "local_score": "int",
        "system_weight": "float", "contributors": "list[str]", "evidence": "list[EvidenceFeatureResponse]",
    },
    "CandidateSpecialisationResponse": {
        "candidate_id": "str", "intrinsic_quality": "int", "quality": "int | None",
        "minimum_quality": "int", "maximum_quality": "int", "competing_economies": "list[str]",
        "preferred_specialisation": "bool", "constraints": "list[SpecialisationConstraintResponse]",
    },
}
MODEL_FIELDS["RatingExplanationResponse"] = {
    **MODEL_FIELDS["RatingSummaryResponse"], "best_candidate_id": "str | None",
    "local_scores": "list[int]", "explanation": "list[str]", "mechanics_version": "str",
    "scorer_version": "str", "contributions": "list[CandidateContributionResponse]",
    "best_specialisation_candidate_id": "str | None",
    "specialisation_candidates": "list[CandidateSpecialisationResponse]",
}
MODEL_FIELDS["SystemRatingsResponse"] = {
    **IDENTITY_FIELDS, "system_id64": "int", "ratings": "list[RatingSummaryResponse]",
}
MODEL_FIELDS["SystemExplanationResponse"] = {
    **IDENTITY_FIELDS, "system_id64": "int", "ratings": "list[RatingExplanationResponse]",
}
SCORE_FIELDS = {
    "potential_score", "specialisation_quality", "specialisation_quality_min", "specialisation_quality_max",
    "base_score", "local_score", "intrinsic_quality", "quality", "minimum_quality", "maximum_quality",
}
UNIT_FIELDS = {"evidence_completeness", "confidence", "system_weight"}


def validate_shape(value: object, descriptor: str, path: str = "response") -> None:
    """Validate required fields and JSON types without coercion or dependencies."""
    if " | " in descriptor:
        for option in descriptor.split(" | "):
            try:
                validate_shape(value, option, path)
                return
            except ValueError:
                pass
        raise ValueError(f"{path}: expected {descriptor}")
    if descriptor.startswith("list["):
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected array")
        for index, item in enumerate(value):
            validate_shape(item, descriptor[5:-1], f"{path}[{index}]")
        return
    if descriptor in MODEL_FIELDS:
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected object")
        for field, kind in MODEL_FIELDS[descriptor].items():
            location = f"{path}.{field}"
            if field not in value:
                raise ValueError(f"{location}: required field missing")
            item = value[field]
            validate_shape(item, kind, location)
            if item is not None and field in SCORE_FIELDS and not 0 <= item <= 100:
                raise ValueError(f"{location}: outside 0–100")
            if field in UNIT_FIELDS and not 0 <= item <= 1:
                raise ValueError(f"{location}: outside 0–1")
            if field == "local_scores" and any(not 0 <= score <= 100 for score in item):
                raise ValueError(f"{location}: outside 0–100")
        return
    valid = False
    if descriptor == "None":
        valid = value is None
    elif descriptor == "float":
        try:
            valid = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            valid = False
    elif descriptor == "datetime":
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value)
                valid = True
            except ValueError:
                pass
    else:
        valid = type(value) is {"str": str, "int": int, "bool": bool, "object": dict}[descriptor]
    if not valid:
        raise ValueError(f"{path}: expected {descriptor}")


def validate_generation(value: dict) -> None:
    validate_shape(value, "GenerationResponse")
    for field in IDENTITY_FIELDS:
        if not value[field]:
            raise ValueError(f"response.{field}: must be nonempty/positive")
    if value["publication_sequence"] < 1 or value["canonical_publication_sequence"] < 1:
        raise ValueError("response: publication sequences must be positive")


def validate_system(value: dict, generation: dict | None, system_id64: int, *, explanation: bool) -> None:
    validate_shape(value, "SystemExplanationResponse" if explanation else "SystemRatingsResponse")
    if generation is None:
        raise ValueError("response: no valid generation endpoint baseline")
    for field in IDENTITY_FIELDS:
        if value[field] != generation[field]:
            raise ValueError(f"response.{field}: differs from generation endpoint")
    if value["system_id64"] != system_id64:
        raise ValueError("response.system_id64: differs from requested system")
    economies = [row["economy"] for row in value["ratings"]]
    if len(economies) != 7 or set(economies) != set(ECONOMIES):
        raise ValueError("response.ratings: expected exactly seven distinct economies")
    if explanation:
        for row in value["ratings"]:
            for field in ("scorer_version", "mechanics_version"):
                if row[field] != generation[field]:
                    raise ValueError(f"response.ratings.{field}: differs from generation endpoint")


def rating_summaries(value: dict) -> dict:
    return {
        row["economy"]: {field: row[field] for field in MODEL_FIELDS["RatingSummaryResponse"]}
        for row in value["ratings"]
    }


def validate_base_url(value: str) -> str:
    """Only a bare origin; refuse credential-bearing URLs before any I/O/logging."""
    try:
        parsed = urlsplit(value)
        loopback = parsed.hostname in ("127.0.0.1", "::1")
        if parsed.hostname:
            try:
                loopback = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                pass
        if (
            not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or any(character.isspace() or ord(character) < 32 for character in value)
            or "\\" in value or parsed.port == 0
            or not (parsed.scheme == "https" or (parsed.scheme == "http" and loopback))
        ):
            raise ValueError
    except ValueError:
        raise ValueError("base URL must be a credential-free HTTPS origin (HTTP only on literal loopback)") from None
    return value.rstrip("/")


def validate_timeout(value: float) -> float:
    if not math.isfinite(value) or not 0 < value <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout must be finite and greater than 0, at most {MAX_TIMEOUT_SECONDS:g} seconds")
    return value


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _invalid_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite JSON number")
    return parsed


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _get_json(url: str, timeout: float) -> dict:
    """One GET in a killable child: socket bounds plus the parent's total deadline."""
    status = None
    try:
        # ProxyHandler({}) ignores proxy environment variables (including credentials).
        # Default HTTPSHandler retains certificate/hostname verification.
        opener = build_opener(ProxyHandler({}), NoRedirects())
        request = Request(url, method="GET", headers={
            "Accept": "application/json", "Cache-Control": "no-cache",
            "User-Agent": "ed-finder-ratings-v4-public-smoke/1",
        })
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            if status != 200:
                return {"status": status, "error": "expected HTTP 200"}
            if response.headers.get_content_type() != "application/json":
                return {"status": status, "error": "expected application/json"}
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            return {"status": status, "error": "response exceeds 4 MiB limit"}
        payload = json.loads(body, parse_constant=_invalid_constant, parse_float=_finite_float,
                             object_pairs_hook=_unique_object)
        return {"status": status, "payload": payload}
    except HTTPError as exc:
        # Do not copy arbitrary error bodies, headers or credential-bearing redirects.
        with exc:
            return {"status": exc.code, "error": "expected HTTP 200 (redirects refused)"}
    except (TimeoutError, URLError, OSError, HTTPException) as exc:
        timeout_error = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
        return {"status": status, "error": "request timeout" if timeout_error else "HTTPS/HTTP transport failed"}
    except (ValueError, UnicodeError, RecursionError):
        return {"status": status, "error": "invalid JSON response"}


def fetch(base_url: str, path: str, timeout: float) -> tuple[dict, object]:
    started = time.monotonic()
    try:
        # A socket timeout alone does not bound DNS or a trickling response. Each
        # isolated, stdlib-only child is killed/reaped on the wall-clock deadline.
        completed = subprocess.run(
            [sys.executable, "-I", "-S", str(Path(__file__).resolve()),
             "--_request-worker", base_url, path, str(timeout)],
            capture_output=True, timeout=timeout, check=False,
        )
        result = json.loads(completed.stdout) if completed.returncode == 0 else {"error": "request worker failed"}
    except subprocess.TimeoutExpired:
        result = {"error": "request timeout"}
    except (OSError, ValueError):
        result = {"error": "request worker failed"}
    errors = [result["error"]] if "error" in result else []
    return {
        "path": path, "method": "GET", "status": result.get("status"),
        "latency_ms": round((time.monotonic() - started) * 1000, 3),
        "validation": {"status": "failed" if errors else "passed", "errors": errors},
    }, result.get("payload")


def run_smoke(base_url: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    base_url = validate_base_url(base_url)
    timeout_seconds = validate_timeout(timeout_seconds)
    receipt = {
        "schema_version": "ed-finder/ratings-v4-public-smoke/v1",
        "base_url": base_url, "started_at": datetime.now(timezone.utc).isoformat(),
        "build_sha": None, "database": None, "generation": None,
        "requests": [], "status": "failed",
    }

    def check(path: str, validator) -> dict | None:
        record, payload = fetch(base_url, path, timeout_seconds)
        receipt["requests"].append(record)
        if record["validation"]["status"] == "failed":
            return None
        try:
            validator(payload)
        except ValueError as exc:
            record["validation"] = {"status": "failed", "errors": [str(exc)]}
            return None
        return payload

    def health(payload: dict) -> None:
        validate_shape(payload, "HealthResponse")
        receipt["build_sha"] = payload["build_sha"]
        receipt["database"] = payload["database"]
        if not re.fullmatch(r"[0-9a-f]{40}", payload["build_sha"]):
            raise ValueError("response.build_sha: expected full 40-character Git SHA")
        if payload["status"] != "ok" or payload["database"] != "connected":
            raise ValueError("response: health must be ok with database connected")

    check("/api/health", health)
    generation = check("/api/ratings/v4/generation", validate_generation)
    receipt["generation"] = generation
    for system_id64, _name in SYSTEMS:
        path = f"/api/ratings/v4/systems/{system_id64}"
        summary = check(path, lambda payload: validate_system(payload, generation, system_id64, explanation=False))

        def explanation(payload: dict) -> None:
            validate_system(payload, generation, system_id64, explanation=True)
            if summary is None:
                raise ValueError("response: no valid system ratings baseline")
            if rating_summaries(payload) != rating_summaries(summary):
                raise ValueError("response.ratings: explanation differs from system ratings")

        check(path + "/explanation", explanation)
    if all(record["validation"]["status"] == "passed" for record in receipt["requests"]):
        receipt["status"] = "passed"
    return receipt


def main(argv: list[str] | None = None) -> int:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 14):
        print("CPython 3.14 is required", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="HTTPS origin; literal loopback HTTP for tests")
    parser.add_argument("--receipt", type=Path, required=True, help="JSON receipt output path (also written on failure)")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                        help="total deadline per request, including worker startup (default 10, max 30)")
    args = parser.parse_args(argv)
    try:
        base_url = validate_base_url(args.base_url)
        timeout = validate_timeout(args.timeout_seconds)
    except ValueError as exc:
        parser.error(str(exc))
    receipt = run_smoke(base_url, timeout)
    try:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    except OSError:
        print("Could not write smoke receipt", file=sys.stderr)
        return 1
    print(f"Ratings V4 public smoke: {receipt['status']}; receipt: {args.receipt}")
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--_request-worker":
        # Internal transport entry point remains restricted to the eight reads.
        origin = validate_base_url(sys.argv[2])
        allowed_paths = {"/api/health", "/api/ratings/v4/generation"} | {
            f"/api/ratings/v4/systems/{identifier}{suffix}"
            for identifier, _ in SYSTEMS for suffix in ("", "/explanation")
        }
        if sys.argv[3] not in allowed_paths:
            raise SystemExit(2)
        print(json.dumps(_get_json(origin + sys.argv[3], validate_timeout(float(sys.argv[4]))), allow_nan=False))
    else:
        raise SystemExit(main())
