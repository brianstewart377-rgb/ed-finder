# Stage 18 Colony Architect Assistant Plan

## Objective

Add a mini-assistant foundation for colony planning guidance without introducing black-box plan mutation.

The assistant must help users express intent such as:

- "I like this plan but make it produce CMM."
- "Move the Dodec to A 5."
- "Make it more industrial and less tourism."
- "Use primary port only as an outpost."
- "I need more large pads."
- "Generate a full expansion plan, not a starter."

## Non-Negotiable Constraints

- deterministic planner remains source of truth
- Preview remains explicit and authoritative validation
- assistant never silently mutates active Build Plan
- assistant actions are previewable and user-confirmed
- no live model/provider keys in foundation phase

## Proposed Architecture

### 1) Advisor Orchestration Layer

- Input: user phrase + current workspace context + current plan snapshot
- Output: structured constraints + confidence + clarification prompts (if needed)
- Responsibility: interpretation only, not direct mutation

### 2) Constraint Schema Layer

Foundation schema fields:

- `must_produce`
- `prefer`
- `avoid`
- `main_station_body`
- `primary_port_policy`
- `scale`
- `required_structures`
- `forbidden_structures`
- `preserve_existing`
- `max_warnings`

### 3) Deterministic Planner Adapter

- consumes structured constraints
- requests bounded candidate generation or targeted placement edits
- emits proposal(s) only

### 4) Proposal Review Surface

- shows differences vs current Build Plan
- shows expected tradeoffs/warnings
- requires explicit user accept/reject

### 5) Validation Gate

- accepted proposal remains untrusted until Preview is run
- Preview outcome becomes the only decision-quality output

## Memory and Knowledge Bank

### Short-term session memory

- keeps user’s current preferences in-session
- examples: preferred scale, avoid tourism, keep existing primary port

### User correction memory

- stores accepted/rejected assistant interpretations
- used to improve future constraint parsing consistency

### Retrieval corpus (RAG candidates)

- planner docs
- facility catalogue descriptions
- topology/body metadata summaries
- historical accepted plan deltas (if later approved)

## Implementation Phasing

### Stage 18A - Foundation (no live model)

- constraint schema + normalization utilities
- docs and test coverage
- no chat UI required

### Stage 18B - Disabled advisor shell

- optional non-production UI shell or API contract
- no external inference calls in production path

### Stage 18C - Controlled inference trial

- provider integration behind explicit feature flag
- full audit logging and explicit user approvals

## Success Criteria

- user can express intent in plain language
- system converts intent into explicit structured constraints
- no silent plan mutation occurs
- user can compare and approve/reject proposals
- Preview remains explicit and central to final decisions

