# Stage 2 Review

Stage 2 turned ED-Finder from a system scoring app into a deterministic colony
planning engine. This review captures what is strong, what remains inferred, and
what should not be overclaimed.

## What Is Solid

- Body economy rules are isolated in the Mega Guide rule layer.
- Mixed-economy inheritance no longer collapses to one economy.
- Topology graph models exact local bodies, main ports, weak links, strong
  links, pass-through, and converted ports.
- Economy stack scoring distinguishes target identity from raw percentages.
- CP timeline exposes sequence risk.
- Regional positioning is archetype-aware and does not use a generic "near is
  good" score.
- Recommended builds now expose score breakdown and decision explanation.
- Regional fit is included before recommendation sorting as a light adjustment,
  so it can break close ties without overriding clearly superior local builds.

## What Is Inferred

- Topology outcomes are inferred from selected local body ids, tiers, and build
  order.
- Economy stack stability is inferred from simulated composition and purity.
- Service unlocks are inferred from documented catalogue unlocks where present.
- Converted-port behaviour is modelled with caveats.
- Regional role thresholds are transparent heuristics pending broader observed
  validation.
- Service unlocks are exposed in simulation output, but service score is
  reserved for service-aware ranking v2 and does not currently move ranking.

## What Is Estimated

- Slot data is estimated unless observed colony slot data is present.
- Some facility catalogue values remain community-observed or provisional.
- CP escalation curves are community-derived.

## What Is Speculative

- Terraformable agriculture modifier is marked speculative/bugged and should not
  be presented as verified.

## Current Trust Layer

- `mechanics_version` identifies the rule set.
- `data_quality` gives compact source-quality badges.
- `confidence_signals` explain confidence movements.
- `mechanics_trace` gives structured debug events.
- `rank_breakdown` exposes recommendation ranking components.
- `decision_explanation` explains why a plan won and what assumptions matter.

## Near-Term Recommendations

- Keep adding tests around explainability before expanding mechanics.
- Prefer moving constants into `apps/api/src/mechanics/` rather than embedding
  numbers in simulation modules.
- Do not add an optimiser until recommendation ranking remains transparent.
- Treat unknown service mechanics as `unknown`, not locked or inactive.
- Use observed player outcomes to graduate inferred/speculative rules.
