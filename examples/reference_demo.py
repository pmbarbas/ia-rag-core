"""Run the hermetic synthetic IA-RAG public-core demonstration."""

from __future__ import annotations

import json

from ia_rag import (
    InMemoryGraphStore,
    PlannerRegistry,
    ReferenceAssuranceProvider,
    build_canonical_runtime,
    load_reference_domain,
    load_reference_facts,
    register_public_canonical_planner,
)


def main() -> None:
    domain = load_reference_domain("research_network")
    facts = load_reference_facts("research_network")
    registry = PlannerRegistry()
    register_public_canonical_planner(
        registry,
        planner_id=domain["query"]["router"]["planner"],
        supported_domains=(domain["domain_name"],),
    )
    runtime = build_canonical_runtime(
        domain_pack=domain,
        planner_registry=registry,
        assurance_provider=ReferenceAssuranceProvider(),
        graph_store=InMemoryGraphStore.from_facts(facts),
    )
    query = "Which datasets were produced by projects contributed to by Alice?"
    compiled = runtime.compile(query)
    result = runtime.execute(query)
    print(json.dumps({
        "selected_planner": compiled.selection.planner_id,
        "logical_plan": {
            "digest": result.lineage["logical_plan_digest"],
            "plan": compiled.logical_plan,
        },
        "executable_plan_digest": result.lineage["executable_plan_digest"],
        "evidence": result.response["metadata"]["evidence"],
        "receipt": result.receipt.to_dict(),
        "response": result.response,
    }, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
