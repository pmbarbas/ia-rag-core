# Public-core boundary

Included in this candidate:

- canonical typed logical and executable plans;
- deterministic planner selection and query routing;
- explicit assurance protocol contracts;
- hermetic in-memory execution;
- evidence, provenance, claims, truth state, receipt, and rendering models;
- two synthetic reference domains;
- public tests and a local reference demo.

Excluded from this candidate:

- application-specific domain packs and data;
- external model, graph, vector, and lexical services;
- deployment credentials and private identity systems;
- observatories, dashboards, migration artifacts, and compatibility layers.

The public runtime does not discover providers through global state. All
runtime dependencies are supplied at construction time, and the assurance
provider sees an already-authoritative executable plan.

