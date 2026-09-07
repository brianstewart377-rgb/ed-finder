"""Build the bounded operation artifact on a GitHub-hosted, trusted-main job."""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

ENTRY = "scripts/operator/actions/v3-live-checkpoint-local.sh"
BOOTSTRAP = "scripts/operator/v3_checkpoint_bootstrap.py"
LAUNCHER = "scripts/operator/actions/edfinder-v3-checkpoint-launcher"
COMMON = [ENTRY, "deploy/v3-live-checkpoint/target-authority.json"]
FILES = {
    "provision": COMMON + ["scripts/operator/actions/v3-live-checkpoint-provision.sh",
                           "scripts/apply_migrations.sh", "scripts/seed_check.sh", "sql"],
    "deploy": COMMON + ["deploy/v3-live-checkpoint/compose.yml",
                        "scripts/operator/v3_checkpoint_deploy.py",
                        "scripts/operator/actions/v3-app-live-checkpoint-preflight.sh",
                        "scripts/release/v3_release_manifest.py"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=FILES)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["bootstrap", "upgrade"])
    parser.add_argument("--run-id")
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source):
        parser.error("invalid exact source SHA")
    bootstrap = subprocess.check_output(["git", "show", f"{args.source}:{BOOTSTRAP}"])
    launcher = subprocess.check_output(["git", "show", f"{args.source}:{LAUNCHER}"])
    bootstrap_sha256 = hashlib.sha256(bootstrap).hexdigest()
    launcher_sha256 = hashlib.sha256(launcher).hexdigest()
    request = {"source_sha": args.source, "operation": args.operation,
               "bootstrap_sha256": bootstrap_sha256,
               "launcher_sha256": launcher_sha256}
    if args.operation == "deploy":
        if (args.mode is None or args.candidate is None or args.run_id is None
                or not re.fullmatch(r"[1-9][0-9]{0,19}", args.run_id)):
            parser.error("deployment needs a mode, run and verified candidate directory")
        request.update(mode=args.mode, release_run_id=args.run_id)
    elif any(value is not None for value in (args.mode, args.run_id, args.candidate)):
        parser.error("provision cannot carry deployment inputs")
    # git archive reads committed objects, not changed working-tree files.
    payload = subprocess.check_output(["git", "archive", args.source, *FILES[args.operation]])
    args.output.write_bytes(payload)
    with tarfile.open(args.output, "a") as archive:
        entries = {"operation.json": json.dumps(request, sort_keys=True).encode()}
        if args.operation == "deploy":
            for name in ("v3-application-release.json", "v3-application-release.json.sha256"):
                entries["artifacts/candidate/" + name] = (args.candidate / name).read_bytes()
        for name, data in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"bundle_sha256={digest}\n")
        output.write(f"bootstrap_sha256={bootstrap_sha256}\n")
        output.write(f"launcher_sha256={launcher_sha256}\n")
    print("Sealed checkpoint operation bundle")


if __name__ == "__main__":
    main()
