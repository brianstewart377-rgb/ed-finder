# PR #446 frontend dependency upgrade (minus Tailwind) — design

## Context

Dependabot PR #446 (`frontend-dependencies` group, 39 updates) bundles ~30
genuinely minor/patch bumps together with several major, breaking version
jumps: TypeScript 5.7→7.0, Tailwind CSS 3.4→4.3, Vite 6→8, Vitest 2→4,
ESLint 9→10, Recharts 2→3, lucide-react 0.469→1.28, vite-plugin-pwa 0.21→1.3.
Because the whole group is graded by its highest-severity change, Dependabot's
`fetch-metadata` reports the entire PR as `semver-major`, so the repo's
patch/minor auto-merge workflow correctly refuses to touch it — it will sit
open indefinitely unless handled deliberately.

An earlier CI-only fix (PR #451, merged) resolved a Node-version blocker
(jsdom 30 requires Node ≥22.22, CI was pinned to Node 20) that was masking
the real dependency-compatibility work. With that fixed, CI on #446 now fails
on a real TypeScript 7 config incompatibility (`tsconfig.json` `baseUrl`
removed), which is expected — TS7 is one of the majors bundled in.

## Decision: scope

Land everything in #446 **except Tailwind**. Tailwind 3→4 is a full CSS
engine rewrite (new `@theme`-based config, PostCSS plugin package change,
`@tailwind base/components/utilities` → single `@import "tailwindcss"`) with
a large hand-written custom theme (`tailwind.config.js`: colors, shadows,
fonts, border-radius, background gradients) that needs visual verification
against the live app before it can be trusted. That's substantial, separate
work with its own visual-regression risk and deserves its own dedicated pass,
not a slot inside this cleanup.

`tailwindcss`, `autoprefixer`, and the PostCSS Tailwind plugin stay pinned at
their current versions in this effort.

## Decision: how it lands

A new branch off `main`, not a hand-edit of Dependabot's `#446` branch
(Dependabot owns that branch and CLAUDE.md's editing conventions don't apply
to bot-managed branches). A fresh PR carries the non-Tailwind bumps; #446 is
closed once that PR merges. Dependabot will re-propose Tailwind alone (plus
whatever new updates have accumulated) on its next weekly run.

## Decision: commit structure

Three commits, each independently testable and revertible:

1. **Low-risk bulk bump** — the ~30 minor/patch packages (Radix UI pieces,
   TanStack Query + devtools, React 19.1→19.2/react-dom, `@react-three/fiber`,
   `@playwright/test`, `@axe-core/playwright`, `@types/*`, `globals`, `knip`,
   `postcss`, etc.), plus `recharts` and `vite-plugin-pwa` riding along despite
   being major bumps — both are confirmed dead in this codebase (`recharts`
   has zero imports anywhere in `src/`; `vite-plugin-pwa` is referenced only
   by a stale `/// <reference types="vite-plugin-pwa/client" />` comment, no
   plugin is registered in any Vite config), so their major-version bump
   carries no behavioral risk.
   Verify: `yarn install`, `yarn typecheck`, `yarn build`.

2. **TypeScript 7 + ESLint 10** — bump `typescript`, `typescript-eslint`,
   `eslint` and its plugins. Fix `tsconfig.json`: TS7 removed `baseUrl`
   support (error TS5102) and requires `paths` entries to be relative
   (error TS5090) — change `"@/*": ["src/*"]` to `"@/*": ["./src/*"]` and
   drop `"baseUrl": "."`. ESLint is already on flat config
   (`eslint.config.js`), so this jump should be low-risk relative to a
   legacy-to-flat migration.
   Verify: `yarn typecheck`, `yarn lint`.

3. **Vite 8 + Vitest 4** — bump `vite`, `@vitejs/plugin-react`, `vitest`,
   `@vitest/ui`, `lucide-react` (the one library in this batch with real
   UI-visible surface: 38 call sites in `src/`). Check the custom
   `vite.authoritative-regions.ts` plugin and the two secondary configs
   (`vite.bakeoff.config.ts`, `vite.map-foundation.config.ts`) for Vite 8
   API compatibility.
   Verify: `yarn typecheck`, `yarn build`, `yarn test`, `yarn test:ci`.

## Final verification before opening the PR

- Full `yarn test:ci`, `yarn build`, `yarn e2e`.
- Per this repo's standing rule for frontend-affecting changes: run
  `yarn dev` and click through the app, specifically checking that
  lucide-react icons still render correctly across the 38 call sites (the
  only UI-visible dependency actually changing behavior in this batch).

## Rollback

Each of the three commits is independently revertible. If group 3 (Vite 8 /
Vitest 4) turns out to need more work than a quick fix, groups 1–2 can still
ship alone as a smaller, still-valuable PR while group 3 is investigated
separately.

## Out of scope

- Tailwind 3→4 migration (deferred, separate future effort).
- Removing the now-confirmed-dead `recharts` and `vite-plugin-pwa`
  dependencies outright — noted as a candidate for a future hygiene pass,
  not actioned here (out of scope for a dependency-version bump).
