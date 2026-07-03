# ED-Finder project context

## Repository and application

- Repository: `brianstewart377-rgb/ed-finder`
- Frontend project: `frontend-v2`
- Main frontend entry: `frontend-v2/src/App.tsx`
- Frontend stack: React, TypeScript, Vite, Vitest, jsdom, TanStack Query.
- Imports use the `@/` alias for `frontend-v2/src`.

## Current application shape

The normal app is hash-routed through `src/hooks/useHashRoute.ts`.

- Unknown hashes fall back to the Finder route.
- `App.tsx` currently owns the normal React Query provider and normal shell/bootstrap tree.
- Normal startup can include Coalsack background resolution, health checks, initial search work, stores, and route rendering.
- Do not assume a DEV-only tool is isolated merely because it uses a special hash. If it must avoid normal startup effects, branch above the normal provider/bootstrap tree.

## Safe engineering defaults

- Prefer narrow, reversible changes.
- Do not infer current branch state from an agent chat. Inspect Git.
- Do not make broad formatting or unrelated cleanup changes during a narrow stage.
- Treat an uncommitted worktree as temporary. It is not a recovery mechanism.
- Use exact branch names and full commit SHAs in handoffs.
- Stage explicit file paths; never use `git add -A` for AI-assisted work.
- Keep test fixtures deterministic and local. Do not make tests depend on live network services.

## Required preflight for any agent

Before editing:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
git diff --check
git ls-files --others --exclude-standard
```

Then read:

```text
docs/ai/PROJECT_CONTEXT.md
docs/ai/CURRENT_STAGE.md
docs/ai/DECISIONS.md
docs/ai/RECOVERY.md
```

If the branch, commit, worktree status, or stage files do not match the expected stage, stop and report the discrepancy.

## R1 Assessment Laboratory boundary

The historical R1 Assessment Laboratory was a DEV-only fixture-backed planning/evaluation tool, not a public ED-Finder feature. Its original local worktree and the specific lost local commit were not recoverable from the available checkout as of 2026-07-01.

That loss remains a historical fact. The approved forward reconstruction now exists in the repository lineage on this branch through the accepted Stage 2B, Stage 3A, and Stage 3B recovery work plus the later continuity records. Treat the repository, not the lost worktree, as the durable R1 baseline.

The reconstructed R1 line must preserve these high-level boundaries:

- DEV-only access at an exact hash, never a normal route or navigation item.
- No normal provider/bootstrap effects, app-data network activity, or persistence writes at that exact DEV entry.
- Production must treat the hash as an ordinary unknown hash and fall back to Finder.
- Production deployable JavaScript, CSS, and HTML must not contain laboratory-only identifiers or load a lab chunk.
- Evaluation must be template/programme-specific; it must not create a universal score, public Finder ranking, or public recommendation surface.

Do not recreate or reinterpret this lab from partial memory. Any later change still requires an explicit written contract, exact branch/base recording, and owner-authorised scope in `CURRENT_STAGE.md`.
