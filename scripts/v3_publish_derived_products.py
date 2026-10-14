#!/usr/bin/env python3
"""Publish both Finder products atomically after the deployed-image plan probe."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.operator.lib import f2d_operator_identity  # noqa: E402


SCHEMA_VERSION = "ed-finder/v3-publish-derived-products-program/v1"
PRODUCTS = ("system_search", "system_archetype")
ACTOR_PATTERN = re.compile(r"[A-Za-z0-9._@:/-]{1,128}\Z")
DATABASE_URL_ENV = "V3_PUBLISH_DERIVED_PRODUCTS_DATABASE_URL"


class PublicationRefusal(RuntimeError):
    """A refusal requiring rollback and a stable process exit code."""

    def __init__(self, exit_code: int, reason: str) -> None:
        self.exit_code = exit_code
        self.reason = reason
        super().__init__(reason)


def refuse_unlisted_checkout_modules() -> None:
    """Refuse a loaded repository module not covered by the operator manifest."""
    root = ROOT.resolve()
    listed = {
        entry for entry in f2d_operator_identity.manifest_entries(ROOT)
        if not entry.startswith("requirement:")
    }
    unlisted: list[str] = []
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        try:
            relative = Path(filename).resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        if relative.endswith((".pyc", ".pyo")):
            relative = (
                relative.rsplit("__pycache__/", 1)[0]
                + relative.rsplit("/", 1)[-1].split(".")[0] + ".py"
            )
        if relative not in listed:
            unlisted.append(relative)
    if unlisted:
        raise ValueError(
            "loaded checkout module is absent from F2d operator manifest: "
            + ", ".join(sorted(set(unlisted)))
        )


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    """Write private handshake/receipt files without exposing a partial JSON file."""
    from scripts.operator.lib.f2d_evidence import canonical_json

    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(canonical_json(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _wait_for_decision(publish_dir: Path, timeout_seconds: int) -> None:
    decision_path = publish_dir / "commit-decision.json"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if decision_path.exists() or decision_path.is_symlink():
            try:
                if decision_path.is_symlink() or not decision_path.is_file():
                    raise ValueError("decision is not a regular file")
                if decision_path.stat().st_size > 4096:
                    raise ValueError("decision is too large")
                decision = json.loads(decision_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as exc:
                raise PublicationRefusal(77, "commit_decision_malformed") from exc
            if decision == {"decision": "commit"}:
                return
            if (
                isinstance(decision, dict)
                and decision.get("decision") == "abort"
                and isinstance(decision.get("reason"), str)
                and decision["reason"]
                and set(decision) == {"decision", "reason"}
            ):
                raise PublicationRefusal(77, "host_image_digest_check_aborted")
            raise PublicationRefusal(77, "commit_decision_malformed")
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    raise PublicationRefusal(78, "commit_handshake_timeout")


def _view_visibility(connection: Any) -> dict[str, Any]:
    # Design 8.6's "view counts" use the Finder's bounded sentinel rather than
    # a full scan of the 198.5M-row generation inside the publication transaction.
    queries = (
        ("v3_app.system_search", "SELECT count(*) FROM (SELECT 1 FROM v3_app.system_search LIMIT 10001) t"),
        ("v3_app.system_archetype", "SELECT count(*) FROM (SELECT 1 FROM v3_app.system_archetype LIMIT 10001) t"),
        ("v3_app.system_archetype_summary", "SELECT count(*) FROM (SELECT 1 FROM v3_app.system_archetype_summary LIMIT 10001) t"),
    )
    counts = {name: int(connection.execute(query).fetchone()[0]) for name, query in queries}
    if any(value != 10001 for value in counts.values()):
        raise PublicationRefusal(71, "bounded_view_visibility_failed")
    estimates = connection.execute(
        """
        SELECT c.relname, c.reltuples
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'v3_derived'
          AND c.relname IN ('system_search', 'system_archetype')
        ORDER BY c.relname
        """
    ).fetchall()
    if {row[0] for row in estimates} != set(PRODUCTS):
        raise PublicationRefusal(71, "physical_table_estimates_missing")
    return {
        "method": "bounded_sentinel",
        "sentinel_limit": 10001,
        "counts": counts,
        "physical_table_reltuples": {row[0]: float(row[1]) for row in estimates},
    }


def publish_products(
    connection: Any,
    statements_document: dict[str, Any],
    *,
    generation_id: str,
    generation_key: str,
    publication_sequence: int,
    actor: str,
    search_final_insert_at: str,
    archetype_final_insert_at: str,
    dense_anchor_cell: dict[str, Any],
    publish_dir: Path,
    f2d_identity: str,
    handshake_timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Own one transaction; every pre-commit failure rolls back both products."""
    from scripts.operator.lib.f2d_evidence import canonical_sha256, seal
    from scripts.v3_archetype_plan_probe import PlanProbeRefusal, run_plan_probe

    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generation": {
            "derived_generation_id": generation_id,
            "generation_key": generation_key,
            "publication_sequence": publication_sequence,
        },
        "actor": actor,
        "f2d_operator_code_sha256": f2d_identity,
        "read_only": False,
        "canonical_writes_performed": False,
        "application_service_changes_performed": False,
        "publication_performed": False,
        "db_writes_performed": False,
    }
    try:
        if ACTOR_PATTERN.fullmatch(actor) is None:
            raise PublicationRefusal(71, "actor_invalid")
        if not 1 <= handshake_timeout_seconds <= 120:
            raise PublicationRefusal(78, "commit_handshake_timeout_invalid")
        if any((publish_dir / name).exists() or (publish_dir / name).is_symlink()
               for name in ("ready-to-commit.json", "commit-decision.json")):
            raise PublicationRefusal(77, "commit_handshake_files_already_exist")
        if connection.autocommit:
            raise PublicationRefusal(4, "publication_requires_transaction_connection")
        connection.execute("SET LOCAL statement_timeout = '600s'")
        generation = connection.execute(
            """
            SELECT g.generation_key, g.lifecycle_state, c.publication_sequence
            FROM v3_meta.derived_generation g
            JOIN v3_meta.current_derived_generation c
              ON c.singleton AND c.derived_generation_id = g.derived_generation_id
            WHERE g.derived_generation_id = %s
            """,
            (generation_id,),
        ).fetchone()
        if generation != (generation_key, "PUBLISHED", publication_sequence):
            raise PublicationRefusal(71, "generation_not_current_published")
        body["generation"].update(lifecycle_state="PUBLISHED", is_current=True)
        products = connection.execute(
            """
            SELECT product_code, lifecycle_state, validation_receipt->>'status',
                   published_at
            FROM v3_meta.derived_product
            WHERE derived_generation_id = %s
              AND product_code IN ('system_search', 'system_archetype')
            ORDER BY product_code FOR UPDATE
            """,
            (generation_id,),
        ).fetchall()
        if any(row[3] is not None for row in products):
            raise PublicationRefusal(72, "publication_already_happened")
        if (
            {row[0] for row in products} != set(PRODUCTS)
            or any(row[1:3] != ("READY", "VERIFIED") for row in products)
        ):
            raise PublicationRefusal(71, "finder_products_not_ready_verified_unpublished")
        search_at = connection.execute(
            "SELECT v3_meta.publish_derived_product(%s,'system_search',%s)",
            (generation_id, actor),
        ).fetchone()[0]
        archetype_at = connection.execute(
            "SELECT v3_meta.publish_derived_product(%s,'system_archetype',%s)",
            (generation_id, actor),
        ).fetchone()[0]
        transaction_at = connection.execute("SELECT transaction_timestamp()").fetchone()[0]
        if search_at != transaction_at or archetype_at != transaction_at:
            raise PublicationRefusal(71, "publication_timestamp_mismatch")
        audit = connection.execute(
            """
            SELECT a.product_code, a.product_version,
                   encode(a.manifest_sha256, 'hex'), a.published_at, a.actor
            FROM v3_meta.derived_product_publication_audit a
            JOIN v3_meta.derived_product p
              ON p.derived_generation_id = a.derived_generation_id
             AND p.product_code = a.product_code
             AND p.product_version = a.product_version
             AND p.manifest_sha256 = a.manifest_sha256
             AND p.published_at = a.published_at
            WHERE a.derived_generation_id = %s
              AND a.product_code IN ('system_search', 'system_archetype')
            ORDER BY a.product_code
            """,
            (generation_id,),
        ).fetchall()
        if ({row[0] for row in audit} != set(PRODUCTS)
                or any(row[3] != transaction_at or row[4] != actor for row in audit)):
            raise PublicationRefusal(71, "publication_audit_mismatch")
        body["published_at"] = _json_value({"system_search": search_at, "system_archetype": archetype_at})
        body["audit_rows"] = [
            dict(zip(("product_code", "product_version", "manifest_sha256", "published_at", "actor"),
                     _json_value(row), strict=True)) for row in audit
        ]
        body["view_visibility"] = _view_visibility(connection)
        connection.execute("SET LOCAL plan_cache_mode = 'force_generic_plan'")
        connection.execute("SET LOCAL statement_timeout = '60s'")
        try:
            probe_receipt = run_plan_probe(
                connection,
                statements_document,
                generation_id=generation_id,
                search_final_insert_at=search_final_insert_at,
                archetype_final_insert_at=archetype_final_insert_at,
                dense_anchor_cell=dense_anchor_cell,
                allow_unpublished=True,
            )
        except PlanProbeRefusal as exc:
            raise PublicationRefusal(76 if exc.exit_code == 20 else 22, exc.reason) from exc
        body["plan_probe_receipt"] = probe_receipt
        if not isinstance(probe_receipt, dict):
            raise PublicationRefusal(22, "plan_probe_receipt_invalid")
        probe_body = dict(probe_receipt)
        probe_seal = probe_body.pop("content_sha256", None)
        if probe_seal != canonical_sha256(probe_body):
            raise PublicationRefusal(22, "plan_probe_receipt_seal_mismatch")
        if probe_receipt.get("status") != "passed":
            raise PublicationRefusal(22, "plan_probe_failed")
        atomic_json(publish_dir / "ready-to-commit.json", {
            "generation": body["generation"],
            "products": list(PRODUCTS),
            "published_at": body["published_at"],
            "plan_probe_receipt_sha256": probe_receipt["content_sha256"],
        })
        # The host holds the deployment lock and rechecks the image digest now.
        # No SQL statement may intervene between this decision and COMMIT.
        _wait_for_decision(publish_dir, handshake_timeout_seconds)
        connection.commit()
        body.update(status="published", exit_code=0, failures=[],
                    publication_performed=True, db_writes_performed=True)
    except PublicationRefusal as exc:
        connection.rollback()
        body.update(status="refused" if exc.exit_code != 22 else "failed",
                    exit_code=exc.exit_code, failures=[exc.reason])
    except Exception as exc:
        connection.rollback()
        # Never serialize connection errors, which can contain credential DSNs.
        body.update(status="failed", exit_code=4,
                    failures=[f"database_or_handshake_error:{type(exc).__name__}"])
    return seal(body)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statements", type=Path, required=True)
    parser.add_argument("--statements-sha256", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--generation-key", required=True)
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--publication-sequence", type=int, required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--search-final-insert-at", required=True)
    parser.add_argument("--archetype-final-insert-at", required=True)
    parser.add_argument("--dense-anchor-cell", required=True)
    parser.add_argument("--publish-dir", type=Path, default=Path("/publish"))
    parser.add_argument("--handshake-timeout-seconds", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Identity is first, before argument files, database access or other imports.
    try:
        identity = f2d_operator_identity.require_operator_code_identity(ROOT)
        refuse_unlisted_checkout_modules()
    except (f2d_operator_identity.OperatorIdentityError, ValueError):
        print("publication identity refusal", file=sys.stderr)
        return 2
    args = _parser().parse_args(argv)
    from scripts.operator.lib.f2d_evidence import canonical_json
    from scripts.v3_archetype_plan_probe import PlanProbeRefusal, validate_statements_document

    try:
        document = json.loads(args.statements.read_text(encoding="utf-8"))
        dense_anchor_cell = json.loads(args.dense_anchor_cell)
        if not isinstance(document, dict) or not isinstance(dense_anchor_cell, dict):
            raise ValueError("input must be objects")
        document["_runtime"] = {
            "statements_sha256": args.statements_sha256,
            "image_digest": args.image_digest,
            "generation_key": args.generation_key,
            "publication_sequence": args.publication_sequence,
            "f2d_operator_code_sha256": identity,
        }
        validate_statements_document(document)
    except (OSError, ValueError, PlanProbeRefusal):
        print("publication statement input refusal", file=sys.stderr)
        return 22
    dsn = os.environ.get(DATABASE_URL_ENV)
    if not dsn:
        print("publication DSN missing", file=sys.stderr)
        return 4
    try:
        import psycopg

        refuse_unlisted_checkout_modules()
        with psycopg.connect(dsn, autocommit=False) as connection:
            receipt = publish_products(
                connection, document,
                generation_id=args.generation_id,
                generation_key=args.generation_key,
                publication_sequence=args.publication_sequence,
                actor=args.actor,
                search_final_insert_at=args.search_final_insert_at,
                archetype_final_insert_at=args.archetype_final_insert_at,
                dense_anchor_cell=dense_anchor_cell,
                publish_dir=args.publish_dir,
                f2d_identity=identity,
                handshake_timeout_seconds=args.handshake_timeout_seconds,
            )
        # Preserve the sealed COMMIT outcome on stdout even if writing the
        # mounted receipt later fails; the host captures this in its run dir.
        print(canonical_json(receipt), flush=True)
        atomic_json(args.publish_dir / "receipt.json", receipt)
    except Exception as exc:
        print(f"publication error: {type(exc).__name__}", file=sys.stderr)
        return 4
    return int(receipt["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
