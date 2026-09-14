"""Typed, non-executing enforcement for canonical execution plans.

R4F-2 is deliberately a seam, not a runtime activation.  The enforcer
consumes the exact :class:`CanonicalExecutionPlan` admitted by R4F-1 and
typed result evidence supplied by a future canonical execution adapter.  It
does not import the historical ``QueryPlan``, execute a store operation, call
an assurance provider, create a receipt, or produce a claim.

The contract is intentionally domain-neutral.  A domain may register an
exact required-subgraph shape in the enforcement context, but the shape is
expressed only in typed nodes, edges and evidence references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .canonical_plan import (
    CanonicalCompositionPolicy,
    CanonicalExecutionPlan,
    CanonicalPlanType,
    CanonicalPlanValidationError,
    CanonicalWorldMode,
    execution_plan_digest,
    validate_execution_plan,
)


CANONICAL_ENFORCEMENT_PROTOCOL_ID = "ia-rag.canonical-execution-enforcement.v1"
CANONICAL_ENFORCEMENT_PROTOCOL_VERSION = 1
_UNAVAILABLE_PLAN_DIGEST = "<unavailable>"


class CanonicalEnforcementPhase(str, Enum):
    PRE_EXECUTION = "PRE_EXECUTION"
    POST_RESULT = "POST_RESULT"


class CanonicalEnforcementStatus(str, Enum):
    ALLOWED = "ALLOWED"
    ALLOWED_PARTIAL = "ALLOWED_PARTIAL"
    DENIED = "DENIED"
    UNSATISFIED = "UNSATISFIED"


class CanonicalTruthEligibility(str, Enum):
    UNKNOWN = "UNKNOWN"
    NEGATIVE_ELIGIBLE = "NEGATIVE_ELIGIBLE"
    POSITIVE_ELIGIBLE = "POSITIVE_ELIGIBLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CanonicalNormativeDisposition(str, Enum):
    PRE_EXECUTION = "PRE_EXECUTION"
    POST_RESULT = "POST_RESULT"
    BOTH = "BOTH"


# This table is part of the enforcement contract.  A constraint cannot be
# silently observational: each supported kind has a named phase and a
# handler in this module.
NORMATIVE_CONSTRAINT_DISPOSITIONS: Mapping[str, CanonicalNormativeDisposition] = {
    "TARGET_ID": CanonicalNormativeDisposition.POST_RESULT,
    "TARGET_TYPE": CanonicalNormativeDisposition.POST_RESULT,
    "SOURCE_TYPE": CanonicalNormativeDisposition.BOTH,
    "RELATION_TYPE": CanonicalNormativeDisposition.BOTH,
    "REQUIRED_SUBGRAPH": CanonicalNormativeDisposition.POST_RESULT,
    "GOVERNANCE_MAX_HOPS": CanonicalNormativeDisposition.PRE_EXECUTION,
    "DATE_KEY_REQUIRED": CanonicalNormativeDisposition.PRE_EXECUTION,
    "CLOSED_WORLD_SCOPE": CanonicalNormativeDisposition.BOTH,
    "PATH_SELECTION_KEY": CanonicalNormativeDisposition.PRE_EXECUTION,
    "CAPABILITY_REQUIRED": CanonicalNormativeDisposition.PRE_EXECUTION,
    "MAX_CARDINALITY": CanonicalNormativeDisposition.BOTH,
    "ORDERED_UNITS": CanonicalNormativeDisposition.PRE_EXECUTION,
}


@dataclass(frozen=True)
class CanonicalSubgraphNode:
    """A typed node required by a proof shape."""

    alias: str
    node_type: str
    node_id: Optional[str] = None


@dataclass(frozen=True)
class CanonicalSubgraphEdge:
    """A typed edge required by a proof shape.

    ``source_alias`` and ``target_alias`` describe the graph's semantic
    source/target.  For an ``IN`` traversal the evidence edge is therefore
    checked in the reverse traversal direction while retaining graph edge
    orientation.
    """

    source_alias: str
    target_alias: str
    relation: str
    direction: str = "OUT"
    edge_id: Optional[str] = None


@dataclass(frozen=True)
class CanonicalRequiredSubgraph:
    """Exact typed shape needed to satisfy a REQUIRED_SUBGRAPH constraint."""

    nodes: Tuple[CanonicalSubgraphNode, ...]
    edges: Tuple[CanonicalSubgraphEdge, ...]
    evidence_references: Tuple[str, ...] = ()
    allow_additional_evidence: bool = True


# Short names are useful at adapter boundaries while the Canonical prefix
# makes the public neutral contract unambiguous.
RequiredSubgraphNode = CanonicalSubgraphNode
RequiredSubgraphEdge = CanonicalSubgraphEdge


@dataclass(frozen=True)
class CanonicalEvidenceNode:
    node_id: str
    node_type: str


@dataclass(frozen=True)
class CanonicalEvidenceEdge:
    source_id: str
    target_id: str
    relation: str
    direction: str = "OUT"
    hop_index: int = 1
    edge_id: Optional[str] = None


@dataclass(frozen=True)
class CanonicalTypedFact:
    subject_id: str
    predicate: str
    object_value: Any
    provenance_references: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalCompletenessWitness:
    scope: str
    reference: str
    complete: bool = True
    plan_digest: Optional[str] = None


@dataclass(frozen=True)
class CanonicalAggregationEvidence:
    operation: str
    result_count: int
    group_count: Optional[int] = None
    result_reference: Optional[str] = None
    evidence_references: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalEvidenceEnvelope:
    """Neutral post-execution evidence; it is not a result or a receipt."""

    nodes: Tuple[CanonicalEvidenceNode, ...] = ()
    edges: Tuple[CanonicalEvidenceEdge, ...] = ()
    typed_facts: Tuple[CanonicalTypedFact, ...] = ()
    provenance_references: Tuple[str, ...] = ()
    completeness_witnesses: Tuple[CanonicalCompletenessWitness, ...] = ()
    aggregation_evidence: Tuple[CanonicalAggregationEvidence, ...] = ()
    returned_result_count: int = 0
    per_hop_cardinality: Mapping[int, int] = field(default_factory=dict)
    child_evidence: Mapping[str, "CanonicalEvidenceEnvelope"] = field(default_factory=dict)


# Alias for adapters that call the boundary an execution-evidence contract.
CanonicalExecutionEvidence = CanonicalEvidenceEnvelope


@dataclass(frozen=True)
class CanonicalEnforcementContext:
    """Explicit environment facts used by semantic enforcement.

    Empty capability and closed-world-scope sets mean no capability/scope was
    declared as supported.  No implementation availability is inspected and
    no historical limit is substituted.
    """

    supported_capabilities: Tuple[str, ...] = ()
    max_hops: Optional[int] = None
    max_results: Optional[int] = None
    cardinality_cap_per_hop: Optional[int] = None
    max_aggregate_top_n: Optional[int] = None
    max_aggregate_groups: Optional[int] = None
    supported_closed_world_scopes: Tuple[str, ...] = ()
    required_subgraphs: Mapping[str, CanonicalRequiredSubgraph] = field(default_factory=dict)


CanonicalExecutionEnforcementContext = CanonicalEnforcementContext


@dataclass(frozen=True)
class CanonicalEnforcementDecision:
    """A semantic decision, intentionally not an execution receipt."""

    executable_plan_digest: str
    phase: CanonicalEnforcementPhase
    status: CanonicalEnforcementStatus
    allowed: bool
    reason_codes: Tuple[str, ...] = ()
    evaluated_constraints: Tuple[str, ...] = ()
    evaluated_capabilities: Tuple[str, ...] = ()
    evidence_references: Tuple[str, ...] = ()
    child_decisions: Tuple["CanonicalEnforcementDecision", ...] = ()
    truth_eligibility: CanonicalTruthEligibility = CanonicalTruthEligibility.NOT_APPLICABLE
    proof_satisfied: Optional[bool] = None

    @property
    def plan_digest(self) -> str:
        """Compatibility-friendly spelling for the exact executable digest."""

        return self.executable_plan_digest

    @property
    def complete(self) -> bool:
        """Only a fully allowed decision is complete; partial is explicit."""

        return self.status == CanonicalEnforcementStatus.ALLOWED


class CanonicalExecutionEnforcementError(ValueError):
    """Raised only for malformed enforcer configuration, never for denial."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(getattr(value, "value", value)).upper()


def _unique(values: Iterable[str]) -> Tuple[str, ...]:
    seen = set()
    result = []
    for value in values:
        text = _text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)


def _constraint_kind(value: Any) -> str:
    return _upper(getattr(value, "kind", ""))


def _constraint_value(value: Any) -> Any:
    return getattr(value, "value", None)


def _required_capabilities(plan: CanonicalExecutionPlan) -> Tuple[str, ...]:
    """Derive required *semantic* capability IDs from the canonical shape."""

    plan_type = CanonicalPlanType(_upper(plan.plan_type))
    required = []
    if plan_type == CanonicalPlanType.COMPOSITE:
        required.append("COMPOSITION")
    elif plan_type == CanonicalPlanType.EXISTS:
        required.append("EXISTENCE_CHECK")
    elif plan_type == CanonicalPlanType.BOOLEAN_CHECK:
        required.append("BOOLEAN_CHECK")
    elif plan_type == CanonicalPlanType.AGGREGATE:
        required.append("AGGREGATION")
    elif not plan.steps:
        required.append("ENTITY_LOOKUP")
    if plan_type == CanonicalPlanType.AGGREGATE:
        required.append("RELATION_LOOKUP")
    elif plan.steps and plan_type not in {CanonicalPlanType.BOOLEAN_CHECK}:
        required.append("RELATION_LOOKUP")
    return _unique(required)


def _decision(
    *,
    plan_digest: str,
    phase: CanonicalEnforcementPhase,
    status: CanonicalEnforcementStatus,
    reasons: Iterable[str] = (),
    constraints: Iterable[str] = (),
    capabilities: Iterable[str] = (),
    evidence: Iterable[str] = (),
    children: Iterable[CanonicalEnforcementDecision] = (),
    truth: CanonicalTruthEligibility = CanonicalTruthEligibility.NOT_APPLICABLE,
    proof: Optional[bool] = None,
) -> CanonicalEnforcementDecision:
    return CanonicalEnforcementDecision(
        executable_plan_digest=plan_digest,
        phase=phase,
        status=status,
        allowed=status in {CanonicalEnforcementStatus.ALLOWED, CanonicalEnforcementStatus.ALLOWED_PARTIAL},
        reason_codes=_unique(reasons),
        evaluated_constraints=_unique(constraints),
        evaluated_capabilities=_unique(capabilities),
        evidence_references=_unique(evidence),
        child_decisions=tuple(children),
        truth_eligibility=truth,
        proof_satisfied=proof,
    )


class CanonicalExecutionEnforcer:
    """Evaluate canonical semantic eligibility before and after execution.

    The object is stateless.  Every method receives the plan and explicit
    context, so it cannot obtain a hidden provider or become a second planner.
    """

    protocol_id = CANONICAL_ENFORCEMENT_PROTOCOL_ID
    protocol_version = CANONICAL_ENFORCEMENT_PROTOCOL_VERSION

    def evaluate_pre_execution(
        self,
        plan: CanonicalExecutionPlan,
        context: CanonicalEnforcementContext,
    ) -> CanonicalEnforcementDecision:
        plan_digest, validation_reasons = self._validate_input(plan, context)
        if validation_reasons:
            return _decision(
                plan_digest=plan_digest,
                phase=CanonicalEnforcementPhase.PRE_EXECUTION,
                status=CanonicalEnforcementStatus.DENIED,
                reasons=validation_reasons,
                constraints=self._constraint_names(plan),
            )

        constraints = self._constraint_names(plan)
        capabilities = self._capability_names(plan)
        reasons = []
        self._check_environment_bounds(plan, context, reasons)
        self._check_capabilities(plan, context, reasons)
        self._check_world_pre(plan, context, reasons)
        self._check_pre_constraints(plan, context, reasons)

        children = []
        if plan.plan_type == CanonicalPlanType.COMPOSITE:
            for unit in plan.composition_units:
                child = self.evaluate_pre_execution(unit.execution_plan, context)
                children.append(child)
                if child.status == CanonicalEnforcementStatus.DENIED and unit.required:
                    reasons.append("required_child_precondition_failed")

        required_failures = [
            child
            for unit, child in zip(plan.composition_units, children)
            if unit.required and child.status != CanonicalEnforcementStatus.ALLOWED
        ]
        optional_failures = [
            child
            for unit, child in zip(plan.composition_units, children)
            if not unit.required and child.status != CanonicalEnforcementStatus.ALLOWED
        ]
        if reasons or required_failures:
            status = CanonicalEnforcementStatus.DENIED
        elif optional_failures:
            reasons.append("optional_child_not_admitted")
            status = (
                CanonicalEnforcementStatus.ALLOWED_PARTIAL
                if _upper(plan.composition_policy) == CanonicalCompositionPolicy.ALLOW_PARTIAL.value
                else CanonicalEnforcementStatus.DENIED
            )
        else:
            status = CanonicalEnforcementStatus.ALLOWED
        return _decision(
            plan_digest=plan_digest,
            phase=CanonicalEnforcementPhase.PRE_EXECUTION,
            status=status,
            reasons=reasons,
            constraints=constraints,
            capabilities=capabilities,
            children=children,
        )

    def evaluate_post_result(
        self,
        plan: CanonicalExecutionPlan,
        result_evidence: CanonicalEvidenceEnvelope,
        context: CanonicalEnforcementContext,
    ) -> CanonicalEnforcementDecision:
        plan_digest, validation_reasons = self._validate_input(plan, context)
        if validation_reasons:
            return _decision(
                plan_digest=plan_digest,
                phase=CanonicalEnforcementPhase.POST_RESULT,
                status=CanonicalEnforcementStatus.DENIED,
                reasons=validation_reasons,
                constraints=self._constraint_names(plan),
            )
        if type(result_evidence) is not CanonicalEvidenceEnvelope:
            return _decision(
                plan_digest=plan_digest,
                phase=CanonicalEnforcementPhase.POST_RESULT,
                status=CanonicalEnforcementStatus.UNSATISFIED,
                reasons=("typed_evidence_envelope_required",),
                constraints=self._constraint_names(plan),
            )

        constraints = self._constraint_names(plan)
        capabilities = self._capability_names(plan)
        reasons = []
        evidence = []
        self._check_result_bounds(plan, result_evidence, context, reasons, evidence)
        self._check_post_constraints(plan, result_evidence, context, reasons, evidence)
        truth = self._world_truth_eligibility(plan, result_evidence, reasons, evidence)
        child_decisions = []
        if plan.plan_type == CanonicalPlanType.COMPOSITE:
            child_map = result_evidence.child_evidence
            for unit in plan.composition_units:
                child_evidence = child_map.get(unit.unit_id) if isinstance(child_map, Mapping) else None
                if child_evidence is None:
                    child = _decision(
                        plan_digest=execution_plan_digest(unit.execution_plan),
                        phase=CanonicalEnforcementPhase.POST_RESULT,
                        status=CanonicalEnforcementStatus.UNSATISFIED,
                        reasons=("child_evidence_missing",),
                        constraints=self._constraint_names(unit.execution_plan),
                    )
                else:
                    child = self.evaluate_post_result(unit.execution_plan, child_evidence, context)
                child_decisions.append(child)
                if child.status != CanonicalEnforcementStatus.ALLOWED and unit.required:
                    reasons.append("required_child_postcondition_unsatisfied")

        required_failures = [
            child
            for unit, child in zip(plan.composition_units, child_decisions)
            if unit.required and child.status != CanonicalEnforcementStatus.ALLOWED
        ]
        optional_failures = [
            child
            for unit, child in zip(plan.composition_units, child_decisions)
            if not unit.required and child.status != CanonicalEnforcementStatus.ALLOWED
        ]
        # An empty OPEN_WORLD result is deliberately informative rather than
        # blocking: it is UNKNOWN, not FALSE.  Every other reason remains a
        # post-result unsatisfaction.
        blocking_reasons = [reason for reason in reasons if reason != "open_world_empty_result"]
        if required_failures or blocking_reasons:
            status = CanonicalEnforcementStatus.UNSATISFIED
        elif optional_failures:
            reasons.append("optional_child_postcondition_unsatisfied")
            status = (
                CanonicalEnforcementStatus.ALLOWED_PARTIAL
                if _upper(plan.composition_policy) == CanonicalCompositionPolicy.ALLOW_PARTIAL.value
                else CanonicalEnforcementStatus.UNSATISFIED
            )
        else:
            status = CanonicalEnforcementStatus.ALLOWED
        has_required_subgraph = any(
            _constraint_kind(item) == "REQUIRED_SUBGRAPH"
            for item in plan.normative_constraints
        )
        return _decision(
            plan_digest=plan_digest,
            phase=CanonicalEnforcementPhase.POST_RESULT,
            status=status,
            reasons=reasons,
            constraints=constraints,
            capabilities=capabilities,
            evidence=evidence,
            children=child_decisions,
            truth=truth,
            proof=(status == CanonicalEnforcementStatus.ALLOWED if has_required_subgraph else None),
        )

    def _validate_input(
        self,
        plan: CanonicalExecutionPlan,
        context: CanonicalEnforcementContext,
    ) -> Tuple[str, Tuple[str, ...]]:
        if type(plan) is not CanonicalExecutionPlan:
            return _UNAVAILABLE_PLAN_DIGEST, ("canonical_execution_plan_required",)
        if type(context) is not CanonicalEnforcementContext:
            raise CanonicalExecutionEnforcementError("canonical_enforcement_context_required")
        try:
            validate_execution_plan(plan)
            self._validate_lineage(plan)
            return execution_plan_digest(plan), ()
        except (CanonicalPlanValidationError, TypeError, ValueError) as exc:
            raw = _text(exc) or "canonical_execution_plan_invalid"
            return _UNAVAILABLE_PLAN_DIGEST, (raw,)

    def _validate_lineage(self, plan: CanonicalExecutionPlan) -> None:
        units = tuple(plan.composition_units or ())
        for unit in units:
            child = unit.execution_plan
            if type(child) is not CanonicalExecutionPlan:
                raise CanonicalPlanValidationError("child_execution_plan_type_invalid")
            if child.planner_id != plan.planner_id:
                raise CanonicalPlanValidationError("composite_planner_mismatch")
            if child.domain_id != plan.domain_id:
                raise CanonicalPlanValidationError("cross_domain_composition_not_active")
            if child.domain_pack_fingerprint != plan.domain_pack_fingerprint:
                raise CanonicalPlanValidationError("cross_pack_composition_not_active")
            if child.domain_pack_version != plan.domain_pack_version:
                raise CanonicalPlanValidationError("composite_pack_version_mismatch")
            if unit.logical_plan_digest != child.source_logical_plan_digest:
                raise CanonicalPlanValidationError("child_source_logical_plan_mismatch")
            validate_execution_plan(child)
            self._validate_lineage(child)

    @staticmethod
    def _constraint_names(plan: Any) -> Tuple[str, ...]:
        return _unique(_constraint_kind(item) for item in (getattr(plan, "normative_constraints", ()) or ()))

    @staticmethod
    def _capability_names(plan: Any) -> Tuple[str, ...]:
        return _unique(
            _upper(getattr(item, "capability_id", ""))
            for item in (getattr(plan, "capability_use", ()) or ())
        )

    @staticmethod
    def _check_environment_bounds(
        plan: CanonicalExecutionPlan,
        context: CanonicalEnforcementContext,
        reasons: list[str],
    ) -> None:
        bounds = plan.bounds
        if int(bounds.max_hops) < len(plan.steps):
            reasons.append("path_exceeds_max_hops")
        if context.max_hops is not None and int(bounds.max_hops) > int(context.max_hops):
            reasons.append("max_hops_exceeds_environment")
        if context.max_results is not None and int(bounds.max_results) > int(context.max_results):
            reasons.append("max_results_exceeds_environment")
        if (
            context.cardinality_cap_per_hop is not None
            and int(bounds.cardinality_cap_per_hop) > int(context.cardinality_cap_per_hop)
        ):
            reasons.append("cardinality_cap_exceeds_environment")
        if plan.aggregation is not None:
            top_n = plan.aggregation.top_n
            if top_n is not None and int(top_n) > int(bounds.max_results):
                reasons.append("aggregate_top_n_exceeds_plan_results")
            if context.max_aggregate_top_n is not None and top_n is not None and int(top_n) > int(context.max_aggregate_top_n):
                reasons.append("aggregate_top_n_exceeds_environment")

    @staticmethod
    def _check_capabilities(
        plan: CanonicalExecutionPlan,
        context: CanonicalEnforcementContext,
        reasons: list[str],
    ) -> None:
        declared = {_upper(item) for item in plan.declared_capabilities}
        uses = {_upper(getattr(item, "capability_id", "")) for item in plan.capability_use}
        supported = {_upper(item) for item in context.supported_capabilities}
        required = set(_required_capabilities(plan))
        for capability in sorted(required):
            if capability not in declared:
                reasons.append(f"capability_undeclared:{capability}")
            if capability not in uses:
                reasons.append(f"capability_use_missing:{capability}")
            if capability not in supported:
                reasons.append(f"capability_unsupported:{capability}")
        for capability in sorted(uses):
            if capability not in supported:
                reasons.append(f"capability_unsupported:{capability}")

    @staticmethod
    def _check_world_pre(
        plan: CanonicalExecutionPlan,
        context: CanonicalEnforcementContext,
        reasons: list[str],
    ) -> None:
        mode = _upper(plan.world.mode)
        if mode == CanonicalWorldMode.CLOSED_WORLD.value:
            scope = _text(plan.world.scope)
            if not scope:
                reasons.append("closed_world_scope_missing")
            if _upper(plan.world.completeness) != "EXHAUSTIVE":
                reasons.append("closed_world_completeness_missing")
            if scope and scope not in {_text(item) for item in context.supported_closed_world_scopes}:
                reasons.append("closed_world_scope_unsupported")
        elif mode == CanonicalWorldMode.OPEN_WORLD.value:
            if plan.world.scope is not None or plan.world.completeness is not None:
                reasons.append("open_world_scope_contradiction")

    def _check_pre_constraints(
        self,
        plan: CanonicalExecutionPlan,
        context: CanonicalEnforcementContext,
        reasons: list[str],
    ) -> None:
        for constraint in plan.normative_constraints:
            kind = _constraint_kind(constraint)
            value = _constraint_value(constraint)
            disposition = NORMATIVE_CONSTRAINT_DISPOSITIONS.get(kind)
            if disposition is None:
                reasons.append(f"unknown_normative_constraint:{kind or 'UNKNOWN'}")
                continue
            if disposition not in {
                CanonicalNormativeDisposition.PRE_EXECUTION,
                CanonicalNormativeDisposition.BOTH,
            }:
                continue
            if kind == "GOVERNANCE_MAX_HOPS":
                try:
                    if int(plan.bounds.max_hops) > int(value):
                        reasons.append("governance_max_hops_exceeded")
                except (TypeError, ValueError):
                    reasons.append("governance_max_hops_invalid")
            elif kind == "DATE_KEY_REQUIRED":
                keys = {_text(item) for item in (plan.aggregation.date_keys if plan.aggregation else ())}
                requested = {_text(item) for item in (value if isinstance(value, (list, tuple, set)) else (value,))}
                if plan.aggregation is None or not requested or not requested.issubset(keys):
                    reasons.append("required_date_key_missing")
            elif kind == "CLOSED_WORLD_SCOPE":
                if _upper(plan.world.mode) != CanonicalWorldMode.CLOSED_WORLD.value or _text(plan.world.scope) != _text(value):
                    reasons.append("closed_world_scope_constraint_mismatch")
            elif kind == "PATH_SELECTION_KEY":
                if not _text(value):
                    reasons.append("path_selection_key_missing")
            elif kind == "CAPABILITY_REQUIRED":
                required = value if isinstance(value, (list, tuple, set)) else (value,)
                declared = {_upper(item) for item in plan.declared_capabilities}
                supported = {_upper(item) for item in context.supported_capabilities}
                for item in required:
                    capability = _upper(item)
                    if capability not in declared or capability not in supported:
                        reasons.append(f"required_capability_unavailable:{capability}")
            elif kind == "ORDERED_UNITS":
                expected = tuple(_text(item) for item in value) if isinstance(value, (list, tuple)) else ()
                actual = tuple(unit.unit_id for unit in plan.composition_units)
                if not expected or actual != expected:
                    reasons.append("composition_order_mismatch")
            elif kind == "SOURCE_TYPE":
                expected = _upper(value)
                if not any(_upper(step.source_type) == expected for step in plan.steps):
                    reasons.append("source_type_constraint_mismatch")
            elif kind == "RELATION_TYPE":
                expected = _upper(value)
                if not any(_upper(step.relation) == expected for step in plan.steps):
                    reasons.append("relation_type_constraint_mismatch")
            elif kind == "MAX_CARDINALITY":
                try:
                    if int(plan.bounds.cardinality_cap_per_hop) > int(value):
                        reasons.append("max_cardinality_exceeded")
                except (TypeError, ValueError):
                    reasons.append("max_cardinality_invalid")
            elif kind in {"TARGET_ID", "TARGET_TYPE", "REQUIRED_SUBGRAPH"}:
                # These are post-result proof constraints; their disposition is
                # explicit above and they are not accepted merely as metadata.
                continue

    @staticmethod
    def _check_result_bounds(
        plan: CanonicalExecutionPlan,
        evidence: CanonicalEvidenceEnvelope,
        context: CanonicalEnforcementContext,
        reasons: list[str],
        evidence_references: list[str],
    ) -> None:
        try:
            result_count = int(evidence.returned_result_count)
        except (TypeError, ValueError):
            reasons.append("result_count_invalid")
            return
        if result_count < 0:
            reasons.append("result_count_invalid")
        if result_count > int(plan.bounds.max_results):
            reasons.append("result_count_exceeds_max_results")

        actual_by_hop: Dict[int, int] = {}
        for edge in evidence.edges:
            try:
                hop = int(edge.hop_index)
            except (TypeError, ValueError):
                reasons.append("hop_index_invalid")
                continue
            if hop < 1 or hop > len(plan.steps):
                reasons.append("result_path_hop_out_of_range")
            actual_by_hop[hop] = actual_by_hop.get(hop, 0) + 1
        supplied = dict(evidence.per_hop_cardinality or {})
        for raw_hop, raw_count in supplied.items():
            try:
                hop = int(raw_hop)
                count = int(raw_count)
            except (TypeError, ValueError):
                reasons.append("per_hop_cardinality_invalid")
                continue
            if count < 0:
                reasons.append("per_hop_cardinality_invalid")
            if count > int(plan.bounds.cardinality_cap_per_hop):
                reasons.append("per_hop_cardinality_exceeded")
            if hop in actual_by_hop and actual_by_hop[hop] != count:
                reasons.append("per_hop_cardinality_evidence_mismatch")
        for hop, count in actual_by_hop.items():
            if count > int(plan.bounds.cardinality_cap_per_hop):
                reasons.append("per_hop_cardinality_exceeded")

        if plan.aggregation is not None:
            operation = _upper(plan.aggregation.operation)
            matching = [item for item in evidence.aggregation_evidence if _upper(item.operation) == operation]
            if not matching:
                reasons.append("aggregation_evidence_missing")
            else:
                item = matching[0]
                try:
                    aggregate_result_count = int(item.result_count)
                except (TypeError, ValueError):
                    reasons.append("aggregation_result_count_invalid")
                    aggregate_result_count = None
                if aggregate_result_count is not None and aggregate_result_count != result_count:
                    reasons.append("aggregation_result_count_mismatch")
                if aggregate_result_count is not None and plan.aggregation.top_n is not None and aggregate_result_count > int(plan.aggregation.top_n):
                    reasons.append("aggregate_top_n_exceeded")
                if context.max_aggregate_groups is not None:
                    if item.group_count is None:
                        reasons.append("aggregation_group_evidence_missing")
                    else:
                        try:
                            if int(item.group_count) > int(context.max_aggregate_groups):
                                reasons.append("aggregate_groups_exceeded")
                        except (TypeError, ValueError):
                            reasons.append("aggregation_group_count_invalid")
                if item.result_reference:
                    evidence_references.append(item.result_reference)
                evidence_references.extend(item.evidence_references)

    def _check_post_constraints(
        self,
        plan: CanonicalExecutionPlan,
        evidence: CanonicalEvidenceEnvelope,
        context: CanonicalEnforcementContext,
        reasons: list[str],
        evidence_references: list[str],
    ) -> None:
        node_by_id = {str(item.node_id): item for item in evidence.nodes}
        for constraint in plan.normative_constraints:
            kind = _constraint_kind(constraint)
            value = _constraint_value(constraint)
            disposition = NORMATIVE_CONSTRAINT_DISPOSITIONS.get(kind)
            if disposition is None:
                reasons.append(f"unknown_normative_constraint:{kind or 'UNKNOWN'}")
                continue
            if disposition not in {
                CanonicalNormativeDisposition.POST_RESULT,
                CanonicalNormativeDisposition.BOTH,
            }:
                continue
            if kind == "TARGET_ID":
                if _text(value) not in node_by_id:
                    reasons.append("target_id_not_proven")
                else:
                    evidence_references.append(_text(value))
            elif kind == "TARGET_TYPE":
                expected = _upper(value)
                if not any(_upper(item.node_type) == expected for item in evidence.nodes):
                    reasons.append("target_type_not_proven")
            elif kind == "SOURCE_TYPE":
                expected = _upper(value)
                if not any(_upper(item.node_type) == expected for item in evidence.nodes):
                    reasons.append("source_type_not_proven")
            elif kind == "RELATION_TYPE":
                expected = _upper(value)
                if not any(_upper(item.relation) == expected for item in evidence.edges):
                    reasons.append("relation_type_not_proven")
            elif kind == "CLOSED_WORLD_SCOPE":
                if _upper(plan.world.mode) != CanonicalWorldMode.CLOSED_WORLD.value or _text(plan.world.scope) != _text(value):
                    reasons.append("closed_world_scope_constraint_mismatch")
            elif kind == "MAX_CARDINALITY":
                try:
                    maximum = int(value)
                    actual_counts: Dict[int, int] = {}
                    for edge in evidence.edges:
                        actual_counts[int(edge.hop_index)] = actual_counts.get(int(edge.hop_index), 0) + 1
                    supplied_counts = {
                        int(hop): int(count)
                        for hop, count in (evidence.per_hop_cardinality or {}).items()
                    }
                    counts = {**actual_counts, **supplied_counts}
                    if any(count > maximum for count in counts.values()):
                        reasons.append("max_cardinality_exceeded")
                except (TypeError, ValueError):
                    reasons.append("max_cardinality_invalid")
            elif kind == "REQUIRED_SUBGRAPH":
                self._check_required_subgraph(plan, value, evidence, context, reasons, evidence_references)

    def _check_required_subgraph(
        self,
        plan: CanonicalExecutionPlan,
        constraint_value: Any,
        evidence: CanonicalEvidenceEnvelope,
        context: CanonicalEnforcementContext,
        reasons: list[str],
        evidence_references: list[str],
    ) -> None:
        key = _text(constraint_value)
        required = context.required_subgraphs.get(key) if isinstance(context.required_subgraphs, Mapping) else None
        if isinstance(constraint_value, CanonicalRequiredSubgraph):
            required = constraint_value
        if type(required) is not CanonicalRequiredSubgraph:
            reasons.append("required_subgraph_shape_missing")
            return
        if not required.nodes and not required.edges:
            reasons.append("required_subgraph_shape_empty")
            return
        aliases = {node.alias for node in required.nodes}
        if len(aliases) != len(required.nodes) or any(not _text(alias) for alias in aliases):
            reasons.append("required_subgraph_node_alias_invalid")
            return
        if any(edge.source_alias not in aliases or edge.target_alias not in aliases for edge in required.edges):
            reasons.append("required_subgraph_edge_alias_invalid")
            return
        node_bindings = self._bind_required_nodes(required.nodes, evidence.nodes)
        if node_bindings is None:
            reasons.append("required_subgraph_node_missing_or_type_mismatch")
            return
        for edge_pattern in required.edges:
            match = self._find_required_edge(edge_pattern, node_bindings, evidence.edges)
            if match is None:
                reasons.append("required_subgraph_edge_missing_or_direction_mismatch")
                return
            if match.edge_id:
                evidence_references.append(match.edge_id)
        refs = {_text(item) for item in evidence.provenance_references}
        missing_refs = [item for item in required.evidence_references if _text(item) not in refs]
        if missing_refs:
            reasons.append("required_subgraph_evidence_reference_missing")
            return
        if not required.allow_additional_evidence:
            expected_node_ids = set(node_bindings.values())
            actual_node_ids = {str(item.node_id) for item in evidence.nodes}
            expected_edge_ids = {
                str(item.edge_id)
                for item in required.edges
                if item.edge_id is not None
            }
            actual_edge_ids = {
                str(item.edge_id)
                for item in evidence.edges
                if item.edge_id is not None
            }
            if actual_node_ids != expected_node_ids or actual_edge_ids != expected_edge_ids:
                reasons.append("required_subgraph_extra_evidence")
                return
        evidence_references.extend(required.evidence_references)

    @staticmethod
    def _bind_required_nodes(
        patterns: Sequence[CanonicalSubgraphNode],
        nodes: Sequence[CanonicalEvidenceNode],
    ) -> Optional[Dict[str, str]]:
        candidates = []
        for pattern in patterns:
            matching = [
                node
                for node in nodes
                if _upper(node.node_type) == _upper(pattern.node_type)
                and (pattern.node_id is None or str(node.node_id) == str(pattern.node_id))
            ]
            if not matching:
                return None
            candidates.append((pattern, sorted(matching, key=lambda item: str(item.node_id))))
        bindings: Dict[str, str] = {}

        def visit(index: int) -> bool:
            if index == len(candidates):
                return True
            pattern, matching = candidates[index]
            for node in matching:
                if node.node_id in bindings.values():
                    continue
                bindings[pattern.alias] = str(node.node_id)
                if visit(index + 1):
                    return True
                bindings.pop(pattern.alias, None)
            return False

        return bindings if visit(0) else None

    @staticmethod
    def _find_required_edge(
        pattern: CanonicalSubgraphEdge,
        bindings: Mapping[str, str],
        edges: Sequence[CanonicalEvidenceEdge],
    ) -> Optional[CanonicalEvidenceEdge]:
        direction = _upper(pattern.direction)
        for edge in edges:
            if _upper(edge.relation) != _upper(pattern.relation) or _upper(edge.direction) != direction:
                continue
            if pattern.edge_id is not None and str(edge.edge_id) != str(pattern.edge_id):
                continue
            if direction == "OUT":
                source_id, target_id = bindings[pattern.source_alias], bindings[pattern.target_alias]
            else:
                source_id, target_id = bindings[pattern.target_alias], bindings[pattern.source_alias]
            if str(edge.source_id) == source_id and str(edge.target_id) == target_id:
                return edge
        return None

    @staticmethod
    def _world_truth_eligibility(
        plan: CanonicalExecutionPlan,
        evidence: CanonicalEvidenceEnvelope,
        reasons: list[str],
        references: list[str],
    ) -> CanonicalTruthEligibility:
        try:
            result_count = int(evidence.returned_result_count)
        except (TypeError, ValueError):
            if "result_count_invalid" not in reasons:
                reasons.append("result_count_invalid")
            return CanonicalTruthEligibility.UNKNOWN
        if _upper(plan.world.mode) == CanonicalWorldMode.OPEN_WORLD.value:
            if result_count == 0:
                reasons.append("open_world_empty_result")
                return CanonicalTruthEligibility.UNKNOWN
            return CanonicalTruthEligibility.POSITIVE_ELIGIBLE
        if result_count != 0:
            return CanonicalTruthEligibility.POSITIVE_ELIGIBLE
        scope = _text(plan.world.scope)
        digest = execution_plan_digest(plan)
        witnesses = [
            witness
            for witness in evidence.completeness_witnesses
            if _text(witness.scope) == scope
            and bool(witness.complete)
            and (witness.plan_digest is None or _text(witness.plan_digest) == digest)
        ]
        if not witnesses:
            reasons.append("closed_world_completeness_witness_missing")
            return CanonicalTruthEligibility.UNKNOWN
        references.extend(witness.reference for witness in witnesses if _text(witness.reference))
        return CanonicalTruthEligibility.NEGATIVE_ELIGIBLE


__all__ = [
    "CANONICAL_ENFORCEMENT_PROTOCOL_ID",
    "CANONICAL_ENFORCEMENT_PROTOCOL_VERSION",
    "NORMATIVE_CONSTRAINT_DISPOSITIONS",
    "CanonicalAggregationEvidence",
    "CanonicalCompletenessWitness",
    "CanonicalEnforcementContext",
    "CanonicalEnforcementDecision",
    "CanonicalNormativeDisposition",
    "CanonicalEnforcementPhase",
    "CanonicalEnforcementStatus",
    "CanonicalExecutionEnforcementContext",
    "CanonicalExecutionEnforcementError",
    "CanonicalExecutionEnforcer",
    "CanonicalExecutionEvidence",
    "CanonicalEvidenceEdge",
    "CanonicalEvidenceEnvelope",
    "CanonicalEvidenceNode",
    "CanonicalRequiredSubgraph",
    "CanonicalSubgraphEdge",
    "CanonicalSubgraphNode",
    "CanonicalTruthEligibility",
    "CanonicalTypedFact",
    "RequiredSubgraphEdge",
    "RequiredSubgraphNode",
]
