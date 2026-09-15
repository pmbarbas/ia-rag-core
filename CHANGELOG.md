# Changelog

## 0.1.0 — 2026-09-15

First public release, promoted from the `0.1.0rc1` candidate without
semantic or runtime changes.

The release provides the canonical plans, deterministic lowering,
admission/enforcement, neutral assurance, bounded in-memory execution,
evidence/provenance, receipts/lineage, synthetic domains, and hermetic
reference runtime described below.

## 0.1.0rc1 — 2026-09-15

Initial IA-RAG Core release candidate.

- Canonical typed logical and executable plans with deterministic lowering.
- Planner registration, plan admission, and pre/post execution enforcement.
- Neutral, explicitly injected assurance protocol and deterministic reference
  assurance provider.
- Bounded in-memory graph execution with evidence and provenance.
- Claim and truth-state handling for open-world, closed-world, and required
  subgraph semantics.
- Execution receipts and lineage bound to the exact executable plan.
- Deterministic rendering of the reference response.
- Synthetic `research_network` and `equipment_network` reference domains.
- Hermetic public tests and an offline reference demo.

The base distribution has no runtime dependencies. External services,
credentials, application data, and deployment integrations are outside this
release candidate.
