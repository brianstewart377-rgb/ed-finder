# Black-Box LLM Colony Architect Musings

## Why this exists

Users want a mini ChatGPT-style planner assistant. The risk is letting opaque output bypass deterministic planner logic and producing brittle plans.

## Principles

- language model can suggest, not commit
- deterministic planner remains executable truth
- assistant outputs constraints, never direct placement writes
- every mutation path remains explicit and reversible
- Preview stays mandatory for decision confidence

## Failure Modes to avoid

- "assistant loaded a plan I did not approve"
- "assistant replaced my plan silently"
- "assistant claims body/slot facts we do not have"
- "assistant outputs looked plausible but were mechanically impossible"

## Practical guardrails

- require structured constraint output
- reject free-form facility/body writes without schema mapping
- keep technical rationale visible on proposal cards
- enforce explicit Load and explicit Preview
- cap mutation scope per assistant action

## Prompt-to-constraint examples

- "make it produce CMM" -> `must_produce: ["CMM"]`
- "move Dodec to A 5" -> `required_structures` + body constraint proposal
- "less tourism" -> `avoid: ["Tourism"]`
- "primary port only as outpost" -> `primary_port_policy: "outpost_only"`
- "full expansion plan" -> `scale: "full"`

## Decision

Proceed with schema-first assistant foundation before any live inference integration.

