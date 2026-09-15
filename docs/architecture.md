# IA-RAG Core architecture

IA-RAG Core treats information architecture as an executable constraint
rather than as background context for a similarity search. A `DomainPack`
declares node types, relation vocabulary, query programs, capabilities,
execution bounds, evidence requirements, and world semantics. A registered
planner interprets a question against that declaration.

## Canonical flow

```text
DomainPack
  -> PlannerRegistry
  -> CanonicalCompiler
  -> CanonicalLogicalPlan
  -> deterministic lowering
  -> CanonicalExecutionPlan
  -> Admission
  -> injected assurance
  -> PRE enforcement
  -> bounded execution
  -> POST enforcement
  -> Evidence / provenance
  -> Claims / truth state
  -> Receipt / lineage
  -> deterministic rendering
```

Planner selection happens before planner-specific compilation. The selected
planner produces the logical plan and its executable lowering. Admission,
assurance, enforcement, execution, claims, provenance, receipt, and rendering
all consume that same lineage. No downstream stage reparses the question or
creates a replacement plan.

## Plans and deterministic lowering

The compiler creates a typed logical plan containing the semantic operation,
anchors, relation steps, projection, aggregation, constraints, bounds,
capability uses, and world semantics. Lowering copies the execution-relevant
fields into a typed executable plan and preserves the logical-plan digest as
its source identity.

Plan digests are hashes of canonicalized typed values. With the same domain
configuration, query, and resolver inputs, planning and lowering are
repeatable and inspectable. The executable plan is the only plan admitted and
given to the bounded execution adapter.

## Admission, assurance, and enforcement

Admission checks planner, domain, plan-type, capability, bound, composition,
and digest identity. The injected assurance provider evaluates the already
compiled executable plan; it does not interpret or replace it. PRE enforcement
checks whether execution may begin. POST enforcement checks the execution
result and evidence before claims and rendering are produced.

An assurance denial or plan-validation failure cannot produce an executed
receipt. A required-subgraph failure produces an incomplete outcome and does
not become a positive claim through a partial result.

## World semantics

The synthetic `research_network` and `equipment_network` domains exercise the
following explicit modes:

- `OPEN_WORLD`: an empty result is insufficient to prove that a fact is false;
  the reference runtime returns `UNKNOWN` for that case.
- `CLOSED_WORLD`: an empty result may support `FALSE` when the declared domain
  and evidence boundary are complete.
- `REQUIRED_SUBGRAPH`: a required relation or traversal must be established
  before a positive claim is allowed. Missing required evidence leaves the
  execution incomplete.

World semantics are properties of the declared evidence boundary. They do not
assert truth beyond the supplied domain and facts.

## Evidence, provenance, and receipt binding

The execution adapter returns rows, traversed nodes and edges, provenance
references, and completeness information. Claims are derived from that
executed evidence. The response includes evidence and semantic metadata rather
than treating retrieval relevance as proof.

The receipt records the planner, domain identity, logical-plan digest,
executable-plan digest, admission and enforcement decisions, execution status,
and result metadata. Lineage metadata and the renderer use the receipt's
executed-plan identity. This makes it possible to inspect exactly which plan
was admitted and run.

## Extension seams

The package defines neutral protocols for graph and document stores, lexical
and vector indexes, embedding and language-model providers, entity services,
telemetry, and domain semantic extensions. These are integration seams only;
the base distribution supplies a deterministic in-memory graph store and
synthetic reference components. External services and deployment-specific
implementations are outside this release candidate.
