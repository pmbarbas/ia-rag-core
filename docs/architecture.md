# Public-core architecture

IA-RAG starts with information architecture rather than an opaque retrieval
call. A domain pack declares the node types, relation vocabulary, query
capabilities, bounds, and world semantics that a planner may use.

The canonical flow is:

1. The caller selects and registers a planner for the configured domain.
2. Semantic interpretation produces a canonical logical plan.
3. The logical plan is lowered once to a canonical executable plan.
4. Admission and the injected assurance provider evaluate that exact plan.
5. The bounded execution adapter returns graph facts and evidence.
6. Claims derive from the executed result and preserve open/closed-world truth.
7. The receipt, lineage metadata, and renderer identify the same executed plan.

The plan digests are deterministic hashes of the typed representations. A
receipt cannot be marked complete when admission, assurance, or required
subgraph enforcement fails.

## Extension boundary

The base package exposes neutral protocols for graph stores, entity
resolution, planning, assurance, and rendering. A deployment may implement
those protocols in a separate package. The public reference runtime uses only
in-memory synthetic components.

