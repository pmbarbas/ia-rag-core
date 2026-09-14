"""R5B hermetic public-core qualification tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ia_rag import (
    AssuranceConfigurationError,
    InMemoryGraphStore,
    PlannerRegistry,
    PublicCoreConfigurationError,
    ReferenceAssuranceProvider,
    build_canonical_runtime,
    closed_world_domain,
    load_reference_domain,
    load_reference_facts,
    register_public_canonical_planner,
)
from ia_rag.canonical_plan import execution_plan_digest


ROOT = Path(__file__).resolve().parents[2]


def _runtime(*, domain=None, facts=None, provider=None):
    domain = domain or load_reference_domain("research_network")
    facts = facts or load_reference_facts("research_network")
    registry = PlannerRegistry()
    register_public_canonical_planner(
        registry,
        planner_id=domain["query"]["router"]["planner"],
        supported_domains=(domain["domain_name"],),
    )
    return build_canonical_runtime(
        domain_pack=domain,
        planner_registry=registry,
        assurance_provider=provider or ReferenceAssuranceProvider(),
        graph_store=InMemoryGraphStore.from_facts(facts),
    )


def test_public_builder_requires_explicit_dependencies():
    domain = load_reference_domain("research_network")
    registry = PlannerRegistry()
    with pytest.raises(AssuranceConfigurationError):
        build_canonical_runtime(
            domain_pack=domain,
            planner_registry=registry,
            assurance_provider=None,
            graph_store=InMemoryGraphStore.from_facts(load_reference_facts("research_network")),
        )
    with pytest.raises(PublicCoreConfigurationError):
        build_canonical_runtime(
            domain_pack=domain,
            planner_registry=None,
            assurance_provider=ReferenceAssuranceProvider(),
            graph_store=InMemoryGraphStore.from_facts(load_reference_facts("research_network")),
        )


def test_one_registered_planner_is_selected_before_compilation():
    runtime = _runtime()
    order = []
    original_select = runtime.query_router.select_planner
    original_compile = runtime.compiler.compile

    def select(query=""):
        order.append("select")
        return original_select(query)

    def compile_query(query, **kwargs):
        order.append("compile")
        return original_compile(query, **kwargs)

    runtime.query_router.select_planner = select
    runtime.compiler.compile = compile_query
    compiled = runtime.compile("Which labs is Alice member of?")
    assert compiled.selection.planner_id == "reference.research_network.v1"
    assert order.index("select") < order.index("compile")
    assert order.count("select") >= 1
    assert order.count("compile") == 1


def test_receipt_binds_the_exact_executable_plan_given_to_adapter():
    runtime = _runtime()
    observed = {}
    original_execute = runtime.adapter.execute

    def execute(plan, **kwargs):
        observed["plan"] = plan
        return original_execute(plan, **kwargs)

    runtime.adapter.execute = execute
    result = runtime.execute("Which datasets were produced by projects contributed to by Alice?")
    assert observed["plan"] is result.compilation.executable_plan
    assert result.receipt.executable_plan_digest == execution_plan_digest(result.compilation.executable_plan)


def test_receipt_and_rendering_share_executed_plan_identity():
    runtime = _runtime()
    result = runtime.execute("Which labs is Alice member of?")
    digest = execution_plan_digest(result.compilation.executable_plan)
    assert result.receipt.executable_plan_digest == result.lineage["executable_plan_digest"]
    assert result.response["metadata"]["execution_receipt"]["canonical_executable_plan_digest"] == digest


def test_repeated_reference_execution_is_deterministic():
    runtime = _runtime()
    first = runtime.execute("Which datasets were produced by projects contributed to by Alice?")
    second = runtime.execute("Which datasets were produced by projects contributed to by Alice?")
    assert first.receipt.to_dict() == second.receipt.to_dict()
    assert dict(first.lineage) == dict(second.lineage)
    assert dict(first.response) == dict(second.response)


def test_composite_execution_preserves_child_receipt_lineage():
    runtime = _runtime()
    result = runtime.execute(
        "Which labs is Alice member of and Which datasets were produced by projects contributed to by Alice?"
    )
    assert result.status == "COMPLETE"
    assert result.receipt.child_receipts
    assert tuple(child.unit_id for child in result.receipt.child_receipts) == ("u1", "u2")
    assert all(child.is_complete for child in result.receipt.child_receipts)
    result.receipt.assert_matches_plans(
        result.compilation.logical_plan,
        result.compilation.executable_plan,
    )


def test_equipment_reference_domain_executes_without_application_domain_defaults():
    domain = load_reference_domain("equipment_network")
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
        graph_store=InMemoryGraphStore.from_facts(load_reference_facts("equipment_network")),
    )
    result = runtime.execute(
        "Which components are contained by facilities located at Device One?"
    )
    assert result.status == "COMPLETE"
    assert result.receipt.domain_id == "equipment_network"
    assert "Pump" in result.response["answer"]


def test_open_world_empty_result_is_unknown():
    result = _runtime().execute("Does Bob contribute?")
    assert result.receipt.is_complete
    assert result.claims.truth_state == "UNKNOWN"
    assert result.response["answer"] == "I don't know."


def test_closed_world_empty_result_is_false_with_completeness_witness():
    result = _runtime(domain=closed_world_domain(load_reference_domain("research_network"))).execute(
        "Does Bob contribute?"
    )
    assert result.receipt.is_complete
    assert result.claims.truth_state == "FALSE"
    assert result.response["answer"] == "No."
    assert result.execution.evidence.completeness_witnesses


def test_assurance_denial_cannot_execute_or_emit_executed_receipt():
    result = _runtime(provider=ReferenceAssuranceProvider(allow=False)).execute(
        "Which labs is Alice member of?"
    )
    assert result.execution is None
    assert result.receipt.execution_status.value == "REJECTED"
    assert result.receipt.assurance.decision_status == "DENIED"


def test_required_subgraph_failure_cannot_become_a_positive_claim():
    facts = load_reference_facts("research_network")
    facts["edges"] = [item for item in facts["edges"] if item["relation"] != "PRODUCED"]
    result = _runtime(facts=facts).execute(
        "Which datasets were produced by projects contributed to by Alice?"
    )
    assert not result.receipt.is_complete
    assert result.response["answer"] == "I don't know."
    assert result.post_enforcement is not None
    assert "required_subgraph" in " ".join(result.post_enforcement.reason_codes)


def test_package_import_does_not_require_optional_runtime_dependencies():
    code = (
        "import sys; import ia_rag; "
        "assert 'pydantic' not in sys.modules; "
        "assert 'ia_rag.hybrid_reasoning' not in sys.modules; "
        "assert 'private_' + 'runtime' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_public_candidate_modules_have_no_private_import_edge():
    paths = [
        ROOT / "src" / "ia_rag" / name
        for name in (
            "public_runtime.py",
            "public_rendering.py",
            "reference_assurance.py",
            "reference_domains.py",
        )
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    excluded_runtime_term = "private_" + "runtime"
    continuity_term = "principal_" + "_continuity"
    assert excluded_runtime_term not in source
    assert continuity_term not in source
