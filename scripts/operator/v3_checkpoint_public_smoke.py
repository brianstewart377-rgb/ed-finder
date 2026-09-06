#!/usr/bin/env python3
"""External, credential-free verification of the exact web AND API release."""
from __future__ import annotations

import argparse
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from v3_checkpoint_deploy import (
    DeploymentError, TARGET_FQDN, get_origin, smoke_origin, wait_for_origin_ready,
)


class BuildIdentity(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.identities = []

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self.in_head = True
        if tag == "meta" and self.in_head:
            values = dict(attrs)
            if values.get("name") == "edfinder-build-sha":
                if len(values) != len(attrs):
                    raise DeploymentError("duplicate web build identity attributes")
                self.identities.append(values.get("content"))

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False


def verify_web_identity(body: bytes, content_type: str, source_sha: str) -> None:
    if "text/html" not in content_type.lower():
        raise DeploymentError("public web identity response is not HTML")
    parser = BuildIdentity()
    try:
        parser.feed(body.decode("utf-8", errors="strict"))
        parser.close()
    except UnicodeError as exc:
        raise DeploymentError("public web identity HTML is not UTF-8") from exc
    if parser.identities != [source_sha]:
        raise DeploymentError("public web build identity mismatch")


def verify_public_checkpoint(source_sha: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise DeploymentError("invalid expected public checkpoint source")
    origin = "http://" + TARGET_FQDN
    wait_for_origin_ready(origin, source_sha)
    outcomes = smoke_origin(origin, source_sha)
    # Read the actual root and the Svelte fallback, not an independently routed
    # sidecar version endpoint: a current API must not mask stale frontend HTML.
    for path in ("/", "/200.html"):
        status, body, content_type = get_origin(origin, path)
        verify_web_identity(body, content_type, source_sha)
        outcomes[path] = {"status": status, "bytes": len(body), "web_build_sha": source_sha}
    return {
        "schema_version": "ed-finder/v3-live-checkpoint-public-smoke/v1",
        "status": "accepted", "origin": origin, "source_sha": source_sha,
        "checks": outcomes, "production": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = verify_public_checkpoint(os.environ.get("EXPECTED_SOURCE_SHA", ""))
        result = 0
    except DeploymentError as exc:
        receipt = {"status": "stopped", "production": False, "failures": [str(exc)]}
        result = 78
    document = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    args.receipt.write_text(document, encoding="utf-8")
    print(document, end="")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
