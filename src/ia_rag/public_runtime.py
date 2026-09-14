"""Neutral, hermetic canonical runtime composition for the public core.

The builder accepts every runtime dependency explicitly.  It does not know
application-domain identities, load external services, discover providers, or
construct a planner implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .assurance_protocols import AssuranceMode, AssuranceProvider, resolve_assurance_provider
from .canonical_compiler import (
    CanonicalCompileResult,
    CanonicalCompiler,
    CanonicalDomainPack,
    CanonicalEntityCandidate,
)
from .canonical_execution_adapter import CanonicalProductionAdapter, CanonicalProductionExecutionResult
from .canonical_execution_admission import CanonicalExecutionAdmission, admit_canonical_execution
from .canonical_execution_enforcement import (
    CanonicalCompletenessWitness,
    CanonicalEnforcementContext,
    CanonicalEnforcementDecision,
    CanonicalEnforcementPhase,
    CanonicalEnforcementStatus,
    CanonicalExecutionEnforcer,
    CanonicalRequiredSubgraph,
    CanonicalSubgraphEdge,
    CanonicalSubgraphNode,
)
from .canonical_execution_receipt import (
    CanonicalAssuranceReference,
    CanonicalExecutionChildOutcome,
    CanonicalExecutionOutcome,
    CanonicalExecutionOutcomeStatus,
    CanonicalExecutionReceipt,
)
from .canonical_plan import (
    CanonicalExecutionPlan,
    CanonicalLogicalPlan,
    CanonicalPlanType,
    execution_plan_digest,
    lower_logical_plan,
    logical_plan_digest,
)
from .canonical_semantic_contract import semantic_fingerprint
from .claims import Claim, ClaimBundle, ClaimPolarity, ClaimStatus
from .claims_from_graph_result import build_claim_bundle_from_graph_result
from .domain import GraphEdge, GraphNode, GraphResult
from .planner_registry import PlannerContext, PlannerRegistration, PlannerRegistry, PlannerSelection, RouteResult
from .public_rendering import PublicResponseRenderer
from .query_router import QueryRouter


PUBLIC_RUNTIME_PROTOCOL_ID = "ia-rag.public-runtime.v1"
PUBLIC_RUNTIME_PROTOCOL_VERSION = 1
PUBLIC_CANONICAL_PLANNER_TYPE = "public_canonical"


class PublicCoreConfigurationError(ValueError):
    """Raised when the neutral public composition is incomplete."""


class PublicExecutionError(RuntimeError):
    """Raised when a public request cannot produce a bounded execution."""


@dataclass(frozen=True)
class PublicCompilation:
    query: str
    selection: PlannerSelection
    route: RouteResult
    compile_result: CanonicalCompileResult

    @property
    def logical_plan(self) -> Optional[CanonicalLogicalPlan]:
        return self.route.logical_plan

    @property
    def executable_plan(self) -> Optional[CanonicalExecutionPlan]:
        plan = self.route.plan
        return plan if isinstance(plan, CanonicalExecutionPlan) else None

    @property
    def accepted(self) -> bool:
        return bool(self.compile_result.ok and self.logical_plan and self.executable_plan)


@dataclass(frozen=True)
class PublicExecutionResult:
    compilation: PublicCompilation
    admission: Optional[CanonicalExecutionAdmission]
    assurance: Optional[CanonicalAssuranceReference]
    pre_enforcement: Optional[CanonicalEnforcementDecision]
    post_enforcement: Optional[CanonicalEnforcementDecision]
    execution: Optional[CanonicalProductionExecutionResult]
    receipt: Optional[CanonicalExecutionReceipt]
    claims: Optional[ClaimBundle]
    lineage: Mapping[str, Any]
    response: Mapping[str, Any]
    status: str


class InMemoryGraphStore:
    """Deterministic graph fact provider used by the reference runtime."""

    def __init__(self, nodes: Iterable[Any] = (), edges: Iterable[Any] = ()) -> None:
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self.upsert_nodes(nodes)
        self.upsert_edges(edges)

    @classmethod
    def from_facts(cls, facts: Mapping[str, Any]) -> "InMemoryGraphStore":
        return cls(facts.get("nodes", ()) or (), facts.get("edges", ()) or ())

    def upsert_nodes(self, nodes: Iterable[Any]) -> None:
        for value in nodes or ():
            node = _coerce_node(value)
            if node is not None:
                self.nodes[node.node_id] = node

    def upsert_edges(self, edges: Iterable[Any]) -> None:
        by_id = {edge.edge_id: edge for edge in self.edges}
        for value in edges or ():
            edge = _coerce_edge(value)
            if edge is not None:
                by_id[edge.edge_id] = edge
        self.edges = [by_id[key] for key in sorted(by_id)]

    def query(self, query_spec: Mapping[str, Any]) -> GraphResult:
        del query_spec
        return GraphResult(
            nodes=[self.nodes[key] for key in sorted(self.nodes)],
            edges=list(self.edges),
        )


class InMemoryEntityResolver:
    """Exact deterministic resolver over the graph-store node snapshot."""

    def __init__(self, graph_store: InMemoryGraphStore) -> None:
        self.graph_store = graph_store

    def resolve(self, mention: str, expected_type: Optional[str] = None) -> Sequence[CanonicalEntityCandidate]:
        target = _normalize(mention)
        expected = str(expected_type or "").strip().upper()
        candidates = []
        for node in self.graph_store.nodes.values():
            if expected and node.node_type.upper() != expected:
                continue
            props = node.properties or {}
            labels = [node.node_id, props.get("name"), props.get("display_name"), props.get("label")]
            normalized = {_normalize(item) for item in labels if str(item or "").strip()}
            if target not in normalized:
                continue
            exact = _normalize(node.node_id) == target or _normalize(props.get("name")) == target
            candidates.append(
                CanonicalEntityCandidate(
                    node.node_id,
                    node.node_type.upper(),
                    str(props.get("name") or node.node_id),
                    1.0 if exact else 0.9,
                )
            )
        return tuple(sorted(candidates, key=lambda item: (-item.score, item.node_type, item.node_id)))


@dataclass(frozen=True)
class PublicRuntimeComponents:
    domain_pack: CanonicalDomainPack
    compiler: CanonicalCompiler
    planner_registry: PlannerRegistry
    assurance_provider: AssuranceProvider
    graph_store: Any
    adapter: CanonicalProductionAdapter
    enforcer: CanonicalExecutionEnforcer
    renderer: PublicResponseRenderer


def register_public_canonical_planner(
    registry: PlannerRegistry,
    *,
    planner_id: str,
    supported_domains: Sequence[str],
    priority: int = 100,
) -> PlannerRegistration:
    """Register one caller-selected generic canonical compiler route."""

    if registry is None:
        raise PublicCoreConfigurationError("planner_registry_required")
    planner_name = str(planner_id or "").strip()
    domains = tuple(str(item or "").strip() for item in supported_domains if str(item or "").strip())
    if not planner_name or not domains:
        raise PublicCoreConfigurationError("public_planner_identity_required")

    def route(context: PlannerContext, query: str, **kwargs: Any) -> RouteResult:
        if kwargs.get("compile_result") is not None:
            raise PublicCoreConfigurationError("public_route_compilation_must_be_authoritative")
        compiler = context.compiler
        if not isinstance(compiler, CanonicalCompiler):
            raise PublicCoreConfigurationError("canonical_compiler_required")
        result = compiler.compile(
            query,
            declared_capabilities=tuple(getattr(compiler.domain_pack, "capabilities", ()) or ()),
        )
        if not result.ok or result.plan is None:
            return RouteResult(
                domain_name=context.domain_name,
                planner_name=context.planner_id,
                plan=None,
                compile_result=result,
                metadata={"compile_reason": result.reason_code},
                logical_plan=None,
            )
        logical = result.plan
        executable = lower_logical_plan(logical)
        return RouteResult(
            domain_name=context.domain_name,
            planner_name=context.planner_id,
            plan=executable,
            compile_result=result,
            metadata={
                "logical_plan_digest": logical_plan_digest(logical),
                "executable_plan_digest": execution_plan_digest(executable),
            },
            logical_plan=logical,
        )

    return registry.register(
        PlannerRegistration(
            planner_id=planner_name,
            route_fn=route,
            supported_domains=domains,
            planner_type=PUBLIC_CANONICAL_PLANNER_TYPE,
            capabilities=("canonical_compile", "canonical_execute"),
            priority=priority,
            execution_path=("canonical_compiler", "canonical_execution_adapter"),
        )
    )


def build_canonical_runtime(
    *,
    domain_pack: CanonicalDomainPack | Mapping[str, Any],
    planner_registry: PlannerRegistry,
    assurance_provider: AssuranceProvider,
    graph_store: Any,
    renderer: Optional[PublicResponseRenderer] = None,
    planner_id: Optional[str] = None,
) -> "PublicCanonicalRuntime":
    """Build a neutral runtime with explicit domain, planner, assurance, and store."""

    if domain_pack is None:
        raise PublicCoreConfigurationError("domain_pack_required")
    if planner_registry is None:
        raise PublicCoreConfigurationError("planner_registry_required")
    if graph_store is None:
        raise PublicCoreConfigurationError("graph_store_required")
    provider = resolve_assurance_provider(assurance_provider)
    return PublicCanonicalRuntime(
        domain_pack=domain_pack,
        planner_registry=planner_registry,
        assurance_provider=provider,
        graph_store=graph_store,
        renderer=renderer,
        planner_id=planner_id,
    )


class PublicCanonicalRuntime:
    """Compile and execute one selected planner lineage over bounded facts."""

    protocol_id = PUBLIC_RUNTIME_PROTOCOL_ID
    protocol_version = PUBLIC_RUNTIME_PROTOCOL_VERSION

    def __init__(
        self,
        *,
        domain_pack: CanonicalDomainPack | Mapping[str, Any],
        planner_registry: PlannerRegistry,
        assurance_provider: AssuranceProvider,
        graph_store: Any,
        renderer: Optional[PublicResponseRenderer] = None,
        planner_id: Optional[str] = None,
    ) -> None:
        self.domain_pack = domain_pack if isinstance(domain_pack, CanonicalDomainPack) else CanonicalDomainPack.from_mapping(domain_pack)
        self._domain_source = _domain_source(self.domain_pack, domain_pack, planner_id)
        self.planner_registry = planner_registry
        self.assurance = resolve_assurance_provider(assurance_provider)
        self.graph_store = graph_store
        configured_planner = _configured_planner_id(self._domain_source)
        if not configured_planner:
            raise PublicCoreConfigurationError("domain_pack_planner_required")
        self.compiler = CanonicalCompiler(
            self.domain_pack,
            entity_resolver=InMemoryEntityResolver(graph_store),
            compiler_id=configured_planner,
        )
        self.adapter = CanonicalProductionAdapter(
            graph_store,
            supported_capabilities=self.domain_pack.capabilities,
        )
        self.enforcer = CanonicalExecutionEnforcer()
        self.renderer = renderer or PublicResponseRenderer()
        self.query_router = QueryRouter(
            self._domain_source,
            compiler=self.compiler,
            assurance_provider=self.assurance,
            planner_registry=self.planner_registry,
        )
        # Resolve the configured registration at construction time, without
        # compiling a request or silently selecting a fallback.
        self.query_router.select_planner("")

    @property
    def components(self) -> PublicRuntimeComponents:
        return PublicRuntimeComponents(
            domain_pack=self.domain_pack,
            compiler=self.compiler,
            planner_registry=self.planner_registry,
            assurance_provider=self.assurance,
            graph_store=self.graph_store,
            adapter=self.adapter,
            enforcer=self.enforcer,
            renderer=self.renderer,
        )

    def compile(self, query: str) -> PublicCompilation:
        selection = self.query_router.select_planner(query)
        route = self.query_router.route(query, selection=selection)
        result = route.compile_result
        if not isinstance(result, CanonicalCompileResult):
            raise PublicCoreConfigurationError("public_planner_did_not_return_compile_result")
        return PublicCompilation(query=str(query or ""), selection=selection, route=route, compile_result=result)

    def execute(self, query: str, *, execution_instance_reference: Optional[str] = None) -> PublicExecutionResult:
        compilation = self.compile(query)
        if not compilation.accepted:
            raise PublicExecutionError(f"canonical_compile_rejected:{compilation.compile_result.reason_code}")
        logical = compilation.logical_plan
        executable = compilation.executable_plan
        if logical is None or executable is None:
            raise PublicExecutionError("canonical_plan_lineage_missing")

        admission = admit_canonical_execution(executable, logical_plan=logical)
        digest = execution_plan_digest(executable)
        assurance_decision, assurance_record = self.assurance.evaluate(
            executable,
            mode=AssuranceMode.ENFORCE,
            runtime_audience="ia-rag.public-core",
        )
        assurance = _assurance_reference(self.assurance, executable, assurance_decision, assurance_record)
        if not bool(getattr(assurance_decision, "ok", False)):
            pre = _denied_pre(executable, "assurance_denied")
            receipt = CanonicalExecutionReceipt.prepare(
                logical_plan=logical,
                executable_plan=executable,
                pre_enforcement=pre,
                assurance=assurance,
            )
            return self._finalize(
                compilation, admission, assurance, pre, None, None, receipt, "DENIED"
            )

        context = _enforcement_context(executable, self.domain_pack)
        pre = self.enforcer.evaluate_pre_execution(executable, context)
        receipt = CanonicalExecutionReceipt.prepare(
            logical_plan=logical,
            executable_plan=executable,
            pre_enforcement=pre,
            assurance=assurance,
        )
        if not pre.allowed:
            return self._finalize(
                compilation, admission, assurance, pre, None, None, receipt, "REJECTED"
            )

        execution_reference = str(execution_instance_reference or f"exec:{digest}").strip()
        try:
            with self.assurance.bind(executable):
                execution = self.adapter.execute(
                    executable,
                    pre_execution_allowed=True,
                    execution_instance_reference=execution_reference,
                )
        except Exception as exc:
            failed = CanonicalExecutionOutcome(
                executable_plan_digest=digest,
                status=CanonicalExecutionOutcomeStatus.FAILED,
                execution_instance_reference=execution_reference,
            )
            failed_receipt = receipt.with_execution_outcome(failed)
            return self._finalize(
                compilation, admission, assurance, pre, None, None, failed_receipt, "EXECUTION_FAILED"
            )

        execution = _attach_reference_completeness(execution, executable)
        outcome = CanonicalExecutionOutcome(
            executable_plan_digest=digest,
            status=CanonicalExecutionOutcomeStatus.SUCCEEDED,
            execution_instance_reference=execution_reference,
            result_reference=execution.result_reference,
            evidence_reference=execution.evidence_reference,
            child_outcomes=_child_outcomes(executable, execution, execution_reference),
        )
        executed_receipt = receipt.with_execution_outcome(outcome)
        post = self.enforcer.evaluate_post_result(
            executable,
            _postcheck_evidence(execution.evidence, executable),
            context,
        )
        final_receipt = executed_receipt.with_post_enforcement(post)
        return self._finalize(
            compilation, admission, assurance, pre, post, execution, final_receipt,
            "COMPLETE" if final_receipt.is_complete else final_receipt.execution_status.value,
        )

    def _finalize(
        self,
        compilation: PublicCompilation,
        admission: CanonicalExecutionAdmission,
        assurance: Optional[CanonicalAssuranceReference],
        pre: Optional[CanonicalEnforcementDecision],
        post: Optional[CanonicalEnforcementDecision],
        execution: Optional[CanonicalProductionExecutionResult],
        receipt: CanonicalExecutionReceipt,
        status: str,
    ) -> PublicExecutionResult:
        receipt.assert_matches_plans(compilation.logical_plan, compilation.executable_plan)
        lineage = {
            "receipt_digest": receipt.receipt_digest,
            "planner_id": receipt.planner_id,
            "domain_id": receipt.domain_id,
            "logical_plan_digest": receipt.canonical_logical_plan_digest,
            "executable_plan_digest": receipt.canonical_executable_plan_digest,
            "execution_status": receipt.execution_status.value,
        }
        claims = None
        response: Mapping[str, Any]
        if execution is not None:
            if post is not None and not post.allowed:
                claims = _indeterminate_claims(compilation.executable_plan, receipt)
            else:
                claims = _claims_for_execution(compilation.executable_plan, execution, receipt)
            response = self.renderer.render(
                claims,
                receipt=receipt.to_dict(),
                lineage=lineage,
                evidence=_evidence_payload(execution.evidence),
            )
        else:
            response = {
                "answer": "I don't know.",
                "claims": [],
                "metadata": {"execution_receipt": receipt.to_dict(), "lineage": lineage},
            }
        return PublicExecutionResult(
            compilation=compilation,
            admission=admission,
            assurance=assurance,
            pre_enforcement=pre,
            post_enforcement=post,
            execution=execution,
            receipt=receipt,
            claims=claims,
            lineage=lineage,
            response=response,
            status=status,
        )


def _coerce_node(value: Any) -> Optional[GraphNode]:
    if isinstance(value, GraphNode):
        return value
    if isinstance(value, Mapping):
        node_id = str(value.get("node_id") or value.get("id") or "").strip()
        node_type = str(value.get("node_type") or value.get("type") or "").strip()
        props = dict(value.get("properties") or {})
    else:
        node_id = str(getattr(value, "node_id", None) or getattr(value, "id", None) or "").strip()
        node_type = str(getattr(value, "node_type", None) or getattr(value, "type", None) or "").strip()
        props = dict(getattr(value, "properties", None) or {})
    return GraphNode(node_id, node_type, props) if node_id and node_type else None


def _coerce_edge(value: Any) -> Optional[GraphEdge]:
    if isinstance(value, GraphEdge):
        return value
    if isinstance(value, Mapping):
        edge_id = str(value.get("edge_id") or value.get("id") or "").strip()
        source = str(value.get("src_id") or value.get("source_id") or value.get("source") or "").strip()
        target = str(value.get("dst_id") or value.get("target_id") or value.get("target") or "").strip()
        relation = str(value.get("relation") or value.get("relation_type") or "").strip()
        props = dict(value.get("properties") or {})
    else:
        edge_id = str(getattr(value, "edge_id", None) or getattr(value, "id", None) or "").strip()
        source = str(getattr(value, "src_id", None) or getattr(value, "source_id", None) or "").strip()
        target = str(getattr(value, "dst_id", None) or getattr(value, "target_id", None) or "").strip()
        relation = str(getattr(value, "relation", None) or getattr(value, "relation_type", None) or "").strip()
        props = dict(getattr(value, "properties", None) or {})
    if not edge_id:
        edge_id = semantic_fingerprint({"source": source, "target": target, "relation": relation})
    return GraphEdge(edge_id, source, target, relation, props) if source and target and relation else None


def _normalize(value: Any) -> str:
    return "".join(char for char in str(value or "").casefold() if char.isalnum())


def _domain_source(pack: CanonicalDomainPack, original: Any, planner_id: Optional[str] = None) -> Dict[str, Any]:
    if isinstance(original, Mapping):
        source = dict(original)
        if planner_id:
            query = dict(source.get("query") or {})
            router = dict(query.get("router") or {})
            router["planner"] = str(planner_id).strip()
            query["router"] = router
            source["query"] = query
        return source
    relations = [
        {"type": item.relation_type, "source": item.source_type, "target": item.target_type, "aliases": list(item.aliases)}
        for item in pack.relations
    ]
    return {
        "domain_name": pack.domain_id,
        "pack_version": pack.pack_version,
        "relations": relations,
        "entities": list(pack.entity_types),
        "capabilities": list(pack.capabilities),
        "world_model": {"mode": pack.world.mode.value, "scope": pack.world.scope, "completeness": pack.world.completeness},
        "governance": {"max_hops": pack.max_hops, "max_results": pack.max_results, "cardinality_cap_per_hop": pack.cardinality_cap_per_hop},
        "query": {"router": {"planner": str(planner_id or "").strip()}},
    }


def _configured_planner_id(source: Mapping[str, Any]) -> str:
    query = source.get("query") if isinstance(source.get("query"), Mapping) else {}
    router = query.get("router") if isinstance(query.get("router"), Mapping) else {}
    return str(router.get("planner") or "").strip()


def _required_subgraphs(plan: CanonicalExecutionPlan) -> Dict[str, CanonicalRequiredSubgraph]:
    required: Dict[str, CanonicalRequiredSubgraph] = {}
    for unit in tuple(plan.composition_units or ()):
        required.update(_required_subgraphs(unit.execution_plan))
    for constraint in tuple(plan.normative_constraints or ()):
        if str(constraint.kind or "").upper() != "REQUIRED_SUBGRAPH" or not plan.anchors:
            continue
        nodes = [CanonicalSubgraphNode("anchor", plan.anchors[0].node_type, plan.anchors[0].node_id)]
        edges = []
        current_alias = "anchor"
        for index, step in enumerate(plan.steps, start=1):
            alias = f"hop{index}"
            reached_type = step.source_type if str(step.direction).upper() == "IN" else step.target_type
            nodes.append(CanonicalSubgraphNode(alias, reached_type))
            edges.append(CanonicalSubgraphEdge(current_alias, alias, step.relation, step.direction))
            current_alias = alias
        required[str(constraint.value)] = CanonicalRequiredSubgraph(tuple(nodes), tuple(edges), allow_additional_evidence=True)
    return required


def _enforcement_context(plan: CanonicalExecutionPlan, pack: CanonicalDomainPack) -> CanonicalEnforcementContext:
    mode = str(getattr(plan.world.mode, "value", plan.world.mode)).upper()
    scopes = (str(plan.world.scope),) if mode == "CLOSED_WORLD" and plan.world.scope else ()
    return CanonicalEnforcementContext(
        supported_capabilities=tuple(pack.capabilities),
        max_hops=pack.max_hops,
        max_results=pack.max_results,
        cardinality_cap_per_hop=pack.cardinality_cap_per_hop,
        max_aggregate_top_n=pack.max_results,
        max_aggregate_groups=pack.max_results,
        supported_closed_world_scopes=scopes,
        required_subgraphs=_required_subgraphs(plan),
    )


def _assurance_reference(provider: Any, plan: CanonicalExecutionPlan, decision: Any, record: Any) -> CanonicalAssuranceReference:
    reference = str(getattr(decision, "decision_reference", "") or getattr(record, "record_id", "")).strip()
    if not reference:
        reference = semantic_fingerprint({"plan": execution_plan_digest(plan), "decision": bool(getattr(decision, "ok", False))})
    return CanonicalAssuranceReference(
        protocol_id=str(getattr(provider, "protocol_id", "")),
        protocol_version=int(getattr(provider, "protocol_version", 0)),
        executable_plan_digest=execution_plan_digest(plan),
        decision_status="ALLOWED" if bool(getattr(decision, "ok", False)) else "DENIED",
        decision_reference=reference,
    )


def _denied_pre(plan: CanonicalExecutionPlan, reason: str) -> CanonicalEnforcementDecision:
    return CanonicalEnforcementDecision(
        executable_plan_digest=execution_plan_digest(plan),
        phase=CanonicalEnforcementPhase.PRE_EXECUTION,
        status=CanonicalEnforcementStatus.DENIED,
        allowed=False,
        reason_codes=(str(reason),),
        evaluated_constraints=tuple(str(item.kind) for item in tuple(plan.normative_constraints or ())),
        evaluated_capabilities=tuple(str(item.capability_id) for item in tuple(plan.capability_use or ())),
    )


def _attach_reference_completeness(
    execution: CanonicalProductionExecutionResult,
    plan: CanonicalExecutionPlan,
) -> CanonicalProductionExecutionResult:
    mode = str(getattr(plan.world.mode, "value", plan.world.mode)).upper()
    if mode != "CLOSED_WORLD" or not plan.world.scope:
        return execution
    witness = CanonicalCompletenessWitness(
        scope=str(plan.world.scope),
        reference=f"memory:{plan.domain_id}:{plan.world.scope}",
        complete=True,
        plan_digest=execution_plan_digest(plan),
    )
    evidence = replace(execution.evidence, completeness_witnesses=(witness,))
    evidence_reference = semantic_fingerprint({"plan": execution_plan_digest(plan), "evidence": evidence})
    return replace(execution, evidence=evidence, evidence_reference=evidence_reference)


def _postcheck_evidence(
    evidence: Any,
    plan: CanonicalExecutionPlan,
) -> Any:
    """Keep composite child evidence authoritative at the child boundary.

    A composite plan has no parent traversal steps.  Its aggregate evidence
    intentionally retains child envelopes for recursive enforcement, while
    parent-level path bounds must not interpret child edges as parent hops.
    """

    if plan.plan_type != CanonicalPlanType.COMPOSITE:
        return evidence
    return replace(
        evidence,
        edges=(),
        aggregation_evidence=(),
        per_hop_cardinality={},
    )


def _child_outcomes(
    plan: CanonicalExecutionPlan,
    execution: CanonicalProductionExecutionResult,
    execution_reference: str,
) -> Tuple[CanonicalExecutionOutcome, ...]:
    if not plan.composition_units:
        return ()
    outcomes = []
    for unit in plan.composition_units:
        child = execution.child_results.get(unit.unit_id)
        if child is None:
            continue
        outcomes.append(
            CanonicalExecutionChildOutcome(
                unit_id=unit.unit_id,
                logical_plan_digest=unit.logical_plan_digest,
                executable_plan_digest=execution_plan_digest(unit.execution_plan),
                status=CanonicalExecutionOutcomeStatus.SUCCEEDED,
                execution_instance_reference=f"{execution_reference}:{unit.unit_id}",
                result_reference=child.result_reference,
                evidence_reference=child.evidence_reference,
                dependencies=tuple(unit.dependencies),
                required=bool(unit.required),
            )
        )
    return tuple(outcomes)


def _evidence_payload(evidence: Any) -> Dict[str, Any]:
    return {
        "nodes": [{"node_id": item.node_id, "node_type": item.node_type} for item in evidence.nodes],
        "edges": [
            {"source_id": item.source_id, "target_id": item.target_id, "relation": item.relation, "edge_id": item.edge_id}
            for item in evidence.edges
        ],
        "provenance_references": list(evidence.provenance_references),
        "completeness_witnesses": [
            {"scope": item.scope, "reference": item.reference, "complete": item.complete, "plan_digest": item.plan_digest}
            for item in evidence.completeness_witnesses
        ],
    }


def _claims_for_execution(
    plan: CanonicalExecutionPlan,
    execution: CanonicalProductionExecutionResult,
    receipt: CanonicalExecutionReceipt,
) -> ClaimBundle:
    mode = str(getattr(plan.world.mode, "value", plan.world.mode)).upper()
    bundle = build_claim_bundle_from_graph_result(
        graph_result=execution.graph_result,
        domain_name=plan.domain_id,
        projection_kind=plan.projection.kind,
        is_existence_question=plan.plan_type == CanonicalPlanType.EXISTS,
        closed_world=mode == "CLOSED_WORLD",
        exists_node_id=plan.anchors[0].node_id if plan.plan_type == CanonicalPlanType.EXISTS and plan.anchors else None,
    )
    bundle.is_boolean_question = plan.plan_type == CanonicalPlanType.BOOLEAN_CHECK
    bundle.execution_receipt = receipt.to_dict()
    bundle.truth_state = "UNKNOWN"
    if execution.evidence.returned_result_count and plan.plan_type in {CanonicalPlanType.BOOLEAN_CHECK, CanonicalPlanType.EXISTS}:
        bundle.truth_state = "TRUE"
    elif mode == "CLOSED_WORLD" and not execution.evidence.returned_result_count:
        bundle.truth_state = "FALSE"
    if not bundle.claims:
        anchor = plan.anchors[0].node_id if plan.anchors else "RESULT"
        target = next(
            (str(item.value) for item in plan.normative_constraints if str(item.kind).upper() == "TARGET_ID"),
            "NO_MATCH",
        )
        if bundle.is_boolean_question or bundle.is_existence_question:
            bundle.claims.append(
                Claim(
                    subject=anchor or "RESULT",
                    predicate=plan.steps[-1].relation if plan.steps else "EXISTS",
                    object=target,
                    polarity=ClaimPolarity.DENY if bundle.truth_state == "FALSE" else ClaimPolarity.AFFIRM,
                    status=ClaimStatus.KNOWN if bundle.truth_state == "FALSE" else ClaimStatus.UNKNOWN,
                    provenance={"receipt_digest": receipt.receipt_digest, "evidence_references": list(execution.evidence.provenance_references)},
                )
            )
        elif execution.evidence.returned_result_count == 0:
            bundle.claims.append(
                Claim(
                    subject=anchor or "RESULT",
                    predicate="RESULT",
                    object="UNKNOWN",
                    status=ClaimStatus.UNKNOWN,
                    provenance={"receipt_digest": receipt.receipt_digest},
                )
            )
    return bundle


def _indeterminate_claims(
    plan: CanonicalExecutionPlan,
    receipt: CanonicalExecutionReceipt,
) -> ClaimBundle:
    """Prevent an unsatisfied postcondition from becoming a positive claim."""

    bundle = ClaimBundle(
        claims=[
            Claim(
                subject=plan.anchors[0].node_id if plan.anchors else "RESULT",
                predicate="RESULT",
                object="INDETERMINATE",
                status=ClaimStatus.UNKNOWN,
                provenance={"receipt_digest": receipt.receipt_digest},
            )
        ],
        projection_kind=plan.projection.kind,
        domain_name=plan.domain_id,
        is_boolean_question=plan.plan_type == CanonicalPlanType.BOOLEAN_CHECK,
        is_existence_question=plan.plan_type == CanonicalPlanType.EXISTS,
        execution_receipt=receipt.to_dict(),
        truth_state="UNKNOWN",
    )
    return bundle


__all__ = [
    "InMemoryEntityResolver",
    "InMemoryGraphStore",
    "PUBLIC_CANONICAL_PLANNER_TYPE",
    "PUBLIC_RUNTIME_PROTOCOL_ID",
    "PUBLIC_RUNTIME_PROTOCOL_VERSION",
    "PublicCanonicalRuntime",
    "PublicCompilation",
    "PublicCoreConfigurationError",
    "PublicExecutionError",
    "PublicExecutionResult",
    "PublicRuntimeComponents",
    "build_canonical_runtime",
    "register_public_canonical_planner",
]
