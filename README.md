# IA-RAG Core

[![PyPI version](https://img.shields.io/pypi/v/ia-rag-core.svg)](https://pypi.org/project/ia-rag-core/)
[![Python >=3.11](https://img.shields.io/badge/python-%E2%89%A53.11-3776AB.svg)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/pmbarbas/ia-rag-core/actions/workflows/ci.yml/badge.svg)](https://github.com/pmbarbas/ia-rag-core/actions/workflows/ci.yml)

Governed, structure-aware retrieval and execution planning for agentic
systems.

IA-RAG Core makes the information architecture of a question explicit before
execution. A domain describes entities, relations, capabilities, bounds, and
world semantics. The runtime then turns a question into an inspectable
semantic program, a typed logical plan, and one bounded executable plan before
producing evidence, claims, a receipt, and a deterministic response.

## Why information architecture comes first

Ordinary vector RAG is useful for ranking relevant text, but relevance is not
the same as authoritative execution semantics. A similarity result does not
by itself say which entities and relations are allowed, whether a traversal
is complete, or what an empty result means.

IA-RAG Core puts those decisions in an explicit domain and plan. Retrieval
strategies can supply candidates through neutral protocols; the canonical
runtime still validates the structure, applies bounds, records evidence, and
binds the result to the exact plan that ran.

## Canonical pipeline

```text
DomainPack
  -> PlannerRegistry
  -> Semantic interpretation
  -> CanonicalCompiler
  -> LogicalPlan
  -> deterministic lowering
  -> ExecutablePlan
  -> Admission and assurance
  -> PRE enforcement
  -> bounded execution
  -> POST enforcement
  -> Evidence and provenance
  -> Claims and truth state
  -> Receipt and lineage
  -> deterministic rendering
```

There is one selected planner, one logical-plan lineage, one executable plan,
and one receipt bound to that executed plan. Plan and receipt digests are
deterministic for the same query, domain configuration, and input facts.

## Install and run

[PyPI package](https://pypi.org/project/ia-rag-core/)

```bash
python -m pip install ia-rag-core
```

The offline reference demo is available from a repository checkout. From the
checkout, install the development tools and run the tests and demo with the
same Python interpreter:

```bash
python -m pip install '.[dev]'
python -m pytest -q
python examples/reference_demo.py
```

Using `python -m pytest` ensures the tests run with the same Python
interpreter and virtual environment into which IA-RAG Core was installed.

The quick-start demo is offline, uses no external credentials, and runs on a
small synthetic research-network domain. Its output includes the selected
planner, plan digests, evidence, receipt, and response.

## Truth and bounded execution

The reference domains demonstrate three explicit semantics:

- `OPEN_WORLD`: an empty search does not prove that a fact is false, so the
  result may be `UNKNOWN`.
- `CLOSED_WORLD`: within the declared domain and complete evidence boundary,
  an empty search can support a `FALSE` result.
- `REQUIRED_SUBGRAPH`: when a declared required relation or traversal cannot
  be established, execution remains incomplete and the runtime does not emit a
  positive claim from the partial result.

These semantics describe the evidence boundary and execution state. They do
not guarantee truth about the real world beyond the supplied domain and
evidence.

## Feature claim ledger

| Status | Claims supported by this candidate |
| --- | --- |
| `DEMONSTRATED` | Typed canonical plans; deterministic planning and lowering; explicit assurance allow/deny; bounded in-memory graph execution; evidence/provenance; open- and closed-world truth behavior; required-subgraph enforcement; plan-bound receipts and lineage; deterministic rendering; synthetic reference domains. |
| `ARCHITECTURALLY_SUPPORTED` | Neutral protocols for graph, document, lexical, vector, embedding, entity, language-model, and telemetry integrations; domain semantic extensions; injected assurance providers. |
| `FUTURE` | Production retrieval adapters, persistent stores, model-backed interpretation, deployment integrations, and production identity or high-assurance services. |
| `NOT A CLAIM` | Elimination of probabilistic retrieval, a guarantee of real-world truth, or production qualification of external services. |

## Deliberate scope

The base distribution has zero runtime dependencies and contains only the
canonical runtime, neutral contracts, deterministic reference assurance,
in-memory execution, and synthetic reference domains. External services,
credentials, application data, and deployment-specific integrations are not
part of this candidate.

IA-RAG Core is licensed under the Apache License 2.0; see [LICENSE](LICENSE).

See [the public architecture](docs/architecture.md) and [the package
boundary](docs/public-core-boundary.md) for the supported scope.

## Feedback and use cases

We welcome real use cases, DomainPack experiments, architecture feedback,
integration ideas, and bug reports.

- Report bugs through [Issues](https://github.com/pmbarbas/ia-rag-core/issues).
- Discuss questions, ideas, and use cases in
  [Discussions](https://github.com/pmbarbas/ia-rag-core/discussions).
- Report suspected vulnerabilities through
  [private vulnerability reporting](https://github.com/pmbarbas/ia-rag-core/security/advisories/new).
