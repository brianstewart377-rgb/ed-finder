# Scoring Vocabulary Decision (2026-07-10)

This note fixes the naming split called out in the 2026-07-10 adversarial
audit.

## Canonical Terms By Layer

- UI / player-facing copy: `Development Score`
- Finder rerank helper surface: `Development Tuning`
- API rerank endpoint family: `archetypes`
- Database / operational implementation: `ratings` / `rating_version`

## Rules

- Do not reintroduce `frontend/public/development.html` or any other parallel
  static explainer surface for scoring language.
- `Development Tuning` is an advanced helper, not a first-class player
  workspace in primary navigation.
- When docs need to mention implementation detail, be explicit that
  `ratings` is the storage/runtime layer behind the current scoring stack
  rather than a competing product term.

## Immediate Outcomes

- The static `development.html` surface was removed.
- Finder no longer links to a standalone scoring explainer page.
- The shell no longer promotes Development Tuning as a peer of Finder and Map.
- Finder now exposes one explicit in-product link into Development Tuning
  without restoring it to the primary navigation hierarchy.
