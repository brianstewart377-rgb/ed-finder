# Stage 19 Incident History

This archive is historical evidence only.
It is not operational authority.
For current state, use docs/colonisation-redesign/stage-19-state-authority.json and the latest merged docs checkpoint.

## Purpose

This file preserves retired Stage 19 and test-environment context so active prompts and the active state authority do not have to carry long stale-state explanations. Do not copy this archive into operational prompts. Operational prompts must run the resolver and use the active authority file, the latest merged docs checkpoint, and live git state.

## Retired Stage 19AR Baseline

The old Stage 19AR baseline was:

| Field | Retired value |
|---|---|
| `source_run_key` | `stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd` |
| `bridge_key` | `source_runs:stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd` |
| `artifact` | `418bc0db66978623c460aa8cc46a8ab14811098f39cb99a16274d9d181f19417` |
| `rows` | `25` |
| `status` | `retired_unrecoverable` |

It was valid-looking because it exercised the source run, enrichment bridge, staging rows, diagnostic isolation, provenance tracking, artifact verification, and operator visibility path. It is retired because the approved Stage 19AR canonical identity is now the replacement run `stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034` with artifact `b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e`. The retired source run key and artifact differ from the approved replacement values and must not be promoted back to canonical status.

## Invalid And Historical States

`45e2d58` is an invalid partial rebaseline. Historical notes recorded `password_missing`, `replacement_baseline_verified:false`, `ready_for_stage19as_au:false`, and missing `origin/main` provenance. It is never authority.

`f72812a` is a docs-only stopped checkpoint from `run/stage19as-au-100-row-expansion`. Historical notes recorded `password_missing`, no writes, and no successful 100-row Stage 19AS-AU expansion. It must not be reported as a completed expansion.

`0042471`, `d66a568`, and `09eee44` are unrecoverable historical test-environment stack references from earlier local context. They were replaced by the merged and recreated test-environment work in PR #198 and later state-authority hardening in PR #199. They are historical context only, not active invalid-state entries.

`8509171250b1449832a7fe3227d87acc02fb015e` was a wrong-branch state-authority attempt on `work`. The commit is unavailable in the current repository and was never authoritative. Do not require it, recover it, or treat it as a patch source.

## Prompt Bundle Evidence

Uploaded or pasted prompt bundles may be duplicated, truncated, stale, or mixed with old prompts and results. They are evidence only. They can explain why a request exists, but they never override the active state authority file, the latest merged docs checkpoint, or live git state.

Do not paste this archive or large stale prompt bundles into future operational prompts. Future prompts should reference the active authority path and require the resolver gate instead.

## Brief Chronology

| PR | Historical note |
|---|---|
| `#193` | Added the bounded 25-row Stage 19AR staging pilot script. |
| `#195` | Closed a Stage 19AR validation gap before the approved replacement baseline work. |
| `#196` | Approved the replacement Stage 19AR canonical baseline. |
| `#197` | Recorded the post-PR196 Stage 19 checkpoint. |
| `#198` | Recreated and validated the test-environment roadmap work, replacing the unrecoverable historical test-env stack. |
| `#199` | Added state-authority branch-gate hardening for Stage 19/test-environment work. |

## Current Authority Pointer

The current operational state is intentionally not repeated here. Use `docs/colonisation-redesign/stage-19-state-authority.json` for current Stage 19 status, the approved Stage 19AR baseline, the tiny invalid-state denylist, and durable prompt/state rules.

