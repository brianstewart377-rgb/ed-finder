# Repo Hygiene Contract

This document defines the minimum repo-shape rules that keep ED-Finder from
accumulating prototypes, one-shot scripts, and planning residue in places that
look live.

## Why This Exists

The codebase gets confusing when temporary work can sit next to canonical
product/runtime paths indefinitely. The goal of this contract is simple:

- keep one obvious source of truth for "what is live";
- force temporary work to declare its fate up front;
- make repo-shape drift fail tests instead of relying on memory.

## Canonical Rules

1. `docs/ROADMAP.md` is the only roadmap/control document.
   - Other docs may be implementation records, handoffs, references, or
     archives.
   - If a root-level document is intentionally preserved, it must explain why
     it still lives at repo root.

2. Repo root is allowlist-only for visible files.
   - New visible root files are not allowed unless they are explicitly
     canonical and added to the hygiene allowlist/test.
   - Planning docs, audits, receipts, and historical reports belong under
     `docs/` or `docs/archive/`.

3. Preview/prototype UI must not quietly become live product surface.
   - A prototype may exist in-tree as reference material.
   - It must not be reachable from the canonical runtime entrypoint unless that
     route is explicitly approved as live product.
   - Historical preview routes must be removed or redirected once the real
     surface exists.

4. Operator scripts must declare whether they are active or historical.
   - Active/validated operator commands live under `scripts/operator/`.
   - Completed historical wrappers move under `scripts/operator/archive/`.
   - If tests or preflight still import a script directly, it is still part of
     the active safety surface and should not be archived yet.

5. Every temporary artifact needs a graduation path.
   - For any prototype folder, preview route, one-shot wrapper, or planning
     note, the author must know which of these applies:
     - `promote`
     - `archive`
     - `delete`

6. "Done" includes residue closeout.
   - When a stage or remediation item closes, closeout should include:
     - removing obsolete live routes/entrypoints;
     - archiving detached docs;
     - archiving historical wrappers;
     - updating guard tests if the repo shape changed intentionally.

## Repo Root Policy

Visible files currently allowed at repo root:

- `CHANGES.md`
- `docker-compose.local.yml`
- `docker-compose.review-hosted.yml`
- `docker-compose.review.yml`
- `docker-compose.yml`
- `ED_FINDER_JOURNAL_IMPORT_AND_COLONISATION_ROUTING_DESIGN_V1.md`
- `env.example`
- `Makefile`
- `pyproject.toml`
- `README.md`
- `setup.sh`

Notes:

- Dotfiles such as `.gitignore` are expected and not part of the visible-file
  allowlist check.
- The journal-import design report remains at repo root only because
  `docs/ROADMAP.md` intentionally links to it as a historical design reference.
- Scratch outputs and local clone residue should never be committed at repo
  root.
- Local scratch clone trees such as `_promote_*` belong in ignored local-only
  space, not in the reviewable repo surface.

## PR Checklist

Before merging a change that adds a new route, doc, script, or prototype:

- Is this live runtime surface, historical reference, or local-only scratch?
- If it is temporary, where will it be archived or deleted?
- If it lives at repo root or under an active runtime path, why is that the
  correct canonical location?
- What test or guard stops it from silently becoming load-bearing later?

## Enforcement

This contract is backed by:

- `tests/test_bounded_hygiene_pass.py`
- `tests/test_repo_hygiene_contract.py`
- `.github/PULL_REQUEST_TEMPLATE.md`

If you intentionally change the repo shape, update the policy and the tests in
the same change.
