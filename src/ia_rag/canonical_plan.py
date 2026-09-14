"""Typed canonical logical/executable plan contracts for R4E-C.

This module is the canonical plan contract.  It contains one target plan family:

    CanonicalLogicalPlan -> CanonicalExecutionPlan

Alternate plan families are intentionally not adapted here; the public
package exposes one canonical plan family.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .canonical_semantic_contract import (
    CanonicalAggregation,
    CanonicalAnchor,
    CanonicalBounds,
    CanonicalProjection,
    CanonicalStep,
    NormativeSemanticConstraint,
    SemanticAnnotation,
    canonical_json,
    semantic_fingerprint,
)


CANONICAL_LOGICAL_PLAN_PROTOCOL_ID = "ia-rag.logical-plan.v1"
CANONICAL_EXECUTION_PLAN_PROTOCOL_ID = "ia-rag.execution-plan.v1"
CANONICAL_PLAN_PROTOCOL_VERSION = 1


class CanonicalPlanValidationError(ValueError):
    """The typed canonical plan is invalid or internally contradictory."""


class CanonicalLoweringError(ValueError):
    """A valid logical plan could not be lowered without semantic loss."""


class SourceSemanticIncompatibility(ValueError):
    """A migration source does not contain semantics required by the target."""


class CanonicalPlanType(str, Enum):
    TRAVERSE = "TRAVERSE"
    EXISTS = "EXISTS"
    BOOLEAN_CHECK = "BOOLEAN_CHECK"
    AGGREGATE = "AGGREGATE"
    COMPOSITE = "COMPOSITE"


class CanonicalWorldMode(str, Enum):
    OPEN_WORLD = "OPEN_WORLD"
    CLOSED_WORLD = "CLOSED_WORLD"


class CanonicalCompositionPolicy(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    ALLOW_PARTIAL = "ALLOW_PARTIAL"


class MigrationDisposition(str, Enum):
    CANONICALIZABLE = "CANONICALIZABLE"
    CANONICALIZABLE_WITH_CANONICAL_DEFAULT = "CANONICALIZABLE_WITH_CANONICAL_DEFAULT"
    SOURCE_SEMANTIC_DEFECT = "SOURCE_SEMANTIC_DEFECT"
    SOURCE_SEMANTIC_LOSS = "SOURCE_SEMANTIC_LOSS"
    COMPATIBILITY_ONLY = "COMPATIBILITY_ONLY"


_VALID_RELATION_DIRECTIONS = {"IN", "OUT"}
_VALID_PROJECTIONS = {"NODE_ONLY", "EDGES", "TYPED_FACTS", "AGGREGATION", "COMPOSITE"}
_VALID_AGGREGATIONS = {"COUNT", "TOP_N", "LATEST", "GROUP_BY_MAX"}
_VALID_NORMATIVE_CONSTRAINTS = {
    "TARGET_ID",
    "TARGET_TYPE",
    "SOURCE_TYPE",
    "RELATION_TYPE",
    "REQUIRED_SUBGRAPH",
    "GOVERNANCE_MAX_HOPS",
    "DATE_KEY_REQUIRED",
    "CLOSED_WORLD_SCOPE",
    "PATH_SELECTION_KEY",
    "CAPABILITY_REQUIRED",
    "MAX_CARDINALITY",
    "ORDERED_UNITS",
}
_VALID_CAPABILITIES = {
    "ENTITY_LOOKUP",
    "RELATION_LOOKUP",
    "BOOLEAN_CHECK",
    "EXISTENCE_CHECK",
    "AGGREGATION",
    "COMPOSITION",
}


@dataclass(frozen=True)
class CanonicalWorldSemantics:
    """Typed open/closed-world semantics; never a loose Boolean."""

    mode: CanonicalWorldMode = CanonicalWorldMode.OPEN_WORLD
    scope: Optional[str] = None
    completeness: Optional[str] = None


@dataclass(frozen=True)
class CanonicalCapabilityUse:
    capability_id: str
    declared_source: str


@dataclass(frozen=True)
class CanonicalSemanticProgramProvenance:
    source: str
    program_id: str


@dataclass(frozen=True)
class CanonicalLogicalUnit:
    unit_id: str
    logical_plan: "CanonicalLogicalPlan"
    dependencies: Tuple[str, ...] = field(default_factory=tuple)
    required: bool = True


@dataclass(frozen=True)
class CanonicalExecutionUnit:
    unit_id: str
    execution_plan: "CanonicalExecutionPlan"
    logical_plan_digest: str
    dependencies: Tuple[str, ...] = field(default_factory=tuple)
    required: bool = True


@dataclass(frozen=True)
class CanonicalLogicalPlan:
    """Single target logical-plan representation for R4E-C and later waves."""

    planner_id: str
    domain_id: str
    domain_pack_fingerprint: str
    domain_pack_version: str
    plan_type: CanonicalPlanType
    anchors: Tuple[CanonicalAnchor, ...]
    steps: Tuple[CanonicalStep, ...]
    projection: CanonicalProjection
    bounds: CanonicalBounds
    world: CanonicalWorldSemantics = field(default_factory=CanonicalWorldSemantics)
    declared_capabilities: Tuple[str, ...] = field(default_factory=tuple)
    capability_use: Tuple[CanonicalCapabilityUse, ...] = field(default_factory=tuple)
    normative_constraints: Tuple[NormativeSemanticConstraint, ...] = field(default_factory=tuple)
    annotations: Tuple[SemanticAnnotation, ...] = field(default_factory=tuple)
    semantic_program: Optional[CanonicalSemanticProgramProvenance] = None
    aggregation: Optional[CanonicalAggregation] = None
    composition_units: Tuple[CanonicalLogicalUnit, ...] = field(default_factory=tuple)
    composition_policy: CanonicalCompositionPolicy = CanonicalCompositionPolicy.FAIL_CLOSED
    protocol_id: str = CANONICAL_LOGICAL_PLAN_PROTOCOL_ID
    protocol_version: int = CANONICAL_PLAN_PROTOCOL_VERSION


@dataclass(frozen=True)
class CanonicalExecutionPlan:
    """Typed executable representation produced only by canonical lowering."""

    planner_id: str
    domain_id: str
    domain_pack_fingerprint: str
    domain_pack_version: str
    source_logical_plan_digest: str
    plan_type: CanonicalPlanType
    execution_operation: str
    anchors: Tuple[CanonicalAnchor, ...]
    steps: Tuple[CanonicalStep, ...]
    projection: CanonicalProjection
    bounds: CanonicalBounds
    world: CanonicalWorldSemantics
    declared_capabilities: Tuple[str, ...]
    capability_use: Tuple[CanonicalCapabilityUse, ...]
    normative_constraints: Tuple[NormativeSemanticConstraint, ...]
    aggregation: Optional[CanonicalAggregation]
    composition_units: Tuple[CanonicalExecutionUnit, ...] = field(default_factory=tuple)
    composition_policy: CanonicalCompositionPolicy = CanonicalCompositionPolicy.FAIL_CLOSED
    semantic_program: Optional[CanonicalSemanticProgramProvenance] = None
    protocol_id: str = CANONICAL_EXECUTION_PLAN_PROTOCOL_ID
    protocol_version: int = CANONICAL_PLAN_PROTOCOL_VERSION


@dataclass(frozen=True)
class MigrationAdapterResult:
    disposition: MigrationDisposition
    source: str
    plan: Optional[CanonicalLogicalPlan] = None
    reason: str = ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(getattr(value, "value", value)).upper()


def _stable_items(values: Iterable[Any]) -> List[Any]:
    return sorted(values, key=lambda item: canonical_json(item))


def _cycle_check(ids: Sequence[str], dependencies: Mapping[str, Sequence[str]], prefix: str) -> None:
    known = set(ids)
    for unit_id in ids:
        if not unit_id:
            raise CanonicalPlanValidationError(f"{prefix}_unit_id_required")
        if any(dep not in known for dep in dependencies.get(unit_id, ())):
            raise CanonicalPlanValidationError(f"{prefix}_unknown_dependency")
        if unit_id in dependencies.get(unit_id, ()):
            raise CanonicalPlanValidationError(f"{prefix}_self_dependency")

    visiting: Set[str] = set()
    visited: Set[str] = set()

    def visit(unit_id: str) -> None:
        if unit_id in visiting:
            raise CanonicalPlanValidationError(f"{prefix}_dependency_cycle")
        if unit_id in visited:
            return
        visiting.add(unit_id)
        for dependency in dependencies.get(unit_id, ()):
            visit(dependency)
        visiting.remove(unit_id)
        visited.add(unit_id)

    for unit_id in ids:
        visit(unit_id)


def _validate_world(world: CanonicalWorldSemantics) -> None:
    mode = _upper(world.mode)
    if mode not in {item.value for item in CanonicalWorldMode}:
        raise CanonicalPlanValidationError("world_mode_invalid")
    if mode == CanonicalWorldMode.CLOSED_WORLD.value:
        if not _text(world.scope):
            raise CanonicalPlanValidationError("closed_world_scope_required")
        if _upper(world.completeness) != "EXHAUSTIVE":
            raise CanonicalPlanValidationError("closed_world_exhaustiveness_required")
    elif world.scope is not None or world.completeness is not None:
        raise CanonicalPlanValidationError("open_world_cannot_have_closed_scope")


def _validate_constraints(constraints: Sequence[NormativeSemanticConstraint]) -> None:
    seen = set()
    for constraint in constraints:
        kind = _upper(constraint.kind)
        if kind not in _VALID_NORMATIVE_CONSTRAINTS:
            raise CanonicalPlanValidationError(f"unknown_normative_constraint:{kind}")
        if kind in seen:
            raise CanonicalPlanValidationError(f"duplicate_normative_constraint:{kind}")
        seen.add(kind)
        if constraint.value is None:
            raise CanonicalPlanValidationError(f"normative_constraint_value_required:{kind}")


def _validate_capabilities(
    declared: Sequence[str],
    uses: Sequence[CanonicalCapabilityUse],
) -> None:
    declared_ids = tuple(_upper(item) for item in declared)
    if len(set(declared_ids)) != len(declared_ids):
        raise CanonicalPlanValidationError("duplicate_declared_capability")
    unknown_declared = set(declared_ids) - _VALID_CAPABILITIES
    if unknown_declared:
        raise CanonicalPlanValidationError(f"unknown_declared_capability:{sorted(unknown_declared)[0]}")
    used_ids = set()
    for use in uses:
        capability = _upper(use.capability_id)
        if capability not in _VALID_CAPABILITIES:
            raise CanonicalPlanValidationError(f"unknown_capability_use:{capability}")
        if not _text(use.declared_source):
            raise CanonicalPlanValidationError(f"capability_source_required:{capability}")
        if capability not in declared_ids:
            raise CanonicalPlanValidationError(f"undeclared_capability:{capability}")
        if capability in used_ids:
            raise CanonicalPlanValidationError(f"duplicate_capability_use:{capability}")
        used_ids.add(capability)


def _validate_common_plan_fields(
    *,
    planner_id: str,
    domain_id: str,
    domain_pack_fingerprint: str,
    domain_pack_version: str,
    plan_type: Any,
    anchors: Sequence[CanonicalAnchor],
    steps: Sequence[CanonicalStep],
    projection: CanonicalProjection,
    bounds: CanonicalBounds,
    world: CanonicalWorldSemantics,
    declared_capabilities: Sequence[str],
    capability_use: Sequence[CanonicalCapabilityUse],
    normative_constraints: Sequence[NormativeSemanticConstraint],
    aggregation: Optional[CanonicalAggregation],
) -> None:
    if not _text(planner_id):
        raise CanonicalPlanValidationError("planner_id_required")
    if not _text(domain_id):
        raise CanonicalPlanValidationError("domain_id_required")
    if not _text(domain_pack_fingerprint):
        raise CanonicalPlanValidationError("domain_pack_fingerprint_required")
    if not _text(domain_pack_version):
        raise CanonicalPlanValidationError("domain_pack_version_required")
    plan_type_value = _upper(plan_type)
    if plan_type_value not in {item.value for item in CanonicalPlanType}:
        raise CanonicalPlanValidationError(f"plan_type_invalid:{plan_type_value}")
    if not anchors and plan_type_value != CanonicalPlanType.COMPOSITE.value:
        raise CanonicalPlanValidationError("anchor_required")
    if plan_type_value != CanonicalPlanType.COMPOSITE.value and len(anchors) != 1:
        raise CanonicalPlanValidationError("single_plan_requires_one_anchor")
    for anchor in anchors:
        if not _text(anchor.node_type):
            raise CanonicalPlanValidationError("anchor_type_required")
        if not _text(anchor.node_id):
            raise CanonicalPlanValidationError("anchor_id_required")

    for step in steps:
        if not _text(step.relation):
            raise CanonicalPlanValidationError("relation_required")
        direction = _upper(step.direction)
        if direction not in _VALID_RELATION_DIRECTIONS:
            raise CanonicalPlanValidationError(f"relation_direction_invalid:{direction}")
        if not _text(step.source_type) or not _text(step.target_type):
            raise CanonicalPlanValidationError("step_endpoint_types_required")

    projection_kind = _upper(projection.kind)
    if projection_kind not in _VALID_PROJECTIONS:
        raise CanonicalPlanValidationError(f"projection_invalid:{projection_kind}")
    if any(not _text(field_name) for field_name in projection.fields):
        raise CanonicalPlanValidationError("projection_field_invalid")

    if int(bounds.max_hops) < 0:
        raise CanonicalPlanValidationError("max_hops_invalid")
    if int(bounds.max_results) <= 0 or int(bounds.cardinality_cap_per_hop) <= 0:
        raise CanonicalPlanValidationError("plan_bounds_invalid")
    if len(steps) > int(bounds.max_hops):
        raise CanonicalPlanValidationError("path_exceeds_max_hops")

    _validate_world(world)
    _validate_capabilities(declared_capabilities, capability_use)
    _validate_constraints(normative_constraints)
    for constraint in normative_constraints:
        if _upper(constraint.kind) == "GOVERNANCE_MAX_HOPS":
            try:
                governance_max_hops = int(constraint.value)
            except (TypeError, ValueError):
                raise CanonicalPlanValidationError("governance_max_hops_invalid")
            if governance_max_hops < int(bounds.max_hops):
                raise CanonicalPlanValidationError("path_exceeds_governance_max_hops")

    if aggregation is not None:
        operation = _upper(aggregation.operation)
        if operation not in _VALID_AGGREGATIONS:
            raise CanonicalPlanValidationError(f"aggregation_operation_invalid:{operation}")
        if aggregation.top_n is not None and int(aggregation.top_n) <= 0:
            raise CanonicalPlanValidationError("aggregation_top_n_invalid")
        date_keys = tuple(_text(item) for item in aggregation.date_keys)
        if len(set(date_keys)) != len(date_keys):
            raise CanonicalPlanValidationError("aggregation_date_keys_duplicate")
        if operation == "LATEST" and not date_keys:
            raise CanonicalPlanValidationError("aggregation_date_keys_required")
    if plan_type_value == CanonicalPlanType.AGGREGATE.value and aggregation is None:
        raise CanonicalPlanValidationError("aggregate_plan_requires_aggregation")
    if plan_type_value != CanonicalPlanType.AGGREGATE.value and aggregation is not None:
        raise CanonicalPlanValidationError("non_aggregate_plan_has_aggregation")
    if plan_type_value == CanonicalPlanType.EXISTS.value and len(steps) == 0 and int(bounds.max_hops) != 0:
        raise CanonicalPlanValidationError("plain_existence_must_be_zero_hop")
    if plan_type_value == CanonicalPlanType.BOOLEAN_CHECK.value and not steps:
        raise CanonicalPlanValidationError("boolean_plan_requires_proof_path")


def _validate_type_chain(plan: CanonicalLogicalPlan) -> None:
    if plan.plan_type == CanonicalPlanType.COMPOSITE or not plan.steps:
        return
    current_type = _upper(plan.anchors[0].node_type)
    for step in plan.steps:
        source_type = _upper(step.source_type)
        target_type = _upper(step.target_type)
        direction = _upper(step.direction)
        if direction == "OUT":
            if source_type not in {"ENTITY", "ANY", current_type}:
                raise CanonicalPlanValidationError("relation_type_chain_inconsistent")
            current_type = target_type
        else:
            if target_type not in {"ENTITY", "ANY", current_type}:
                raise CanonicalPlanValidationError("relation_type_chain_inconsistent")
            current_type = source_type


def _validate_composition(logical: CanonicalLogicalPlan) -> None:
    policy = _upper(logical.composition_policy)
    if policy not in {item.value for item in CanonicalCompositionPolicy}:
        raise CanonicalPlanValidationError(f"composition_policy_invalid:{policy}")
    units = tuple(logical.composition_units or ())
    if logical.plan_type == CanonicalPlanType.COMPOSITE and len(units) < 2:
        raise CanonicalPlanValidationError("composite_requires_multiple_units")
    if logical.plan_type != CanonicalPlanType.COMPOSITE and units:
        raise CanonicalPlanValidationError("non_composite_plan_has_units")
    ids = [unit.unit_id for unit in units]
    if len(set(ids)) != len(ids):
        raise CanonicalPlanValidationError("composite_unit_ids_must_be_unique")
    dependencies = {unit.unit_id: tuple(unit.dependencies) for unit in units}
    _cycle_check(ids, dependencies, "logical_composite")
    for unit in units:
        if unit.logical_plan.domain_id != logical.domain_id:
            raise CanonicalPlanValidationError("cross_domain_composition_not_active")
        if unit.logical_plan.domain_pack_fingerprint != logical.domain_pack_fingerprint:
            raise CanonicalPlanValidationError("cross_pack_composition_not_active")
        if unit.logical_plan.planner_id != logical.planner_id:
            raise CanonicalPlanValidationError("composite_planner_mismatch")
        validate_logical_plan(unit.logical_plan)


def validate_logical_plan(plan: CanonicalLogicalPlan) -> None:
    if plan.protocol_id != CANONICAL_LOGICAL_PLAN_PROTOCOL_ID or int(plan.protocol_version) != CANONICAL_PLAN_PROTOCOL_VERSION:
        raise CanonicalPlanValidationError("logical_plan_protocol_invalid")
    _validate_common_plan_fields(
        planner_id=plan.planner_id,
        domain_id=plan.domain_id,
        domain_pack_fingerprint=plan.domain_pack_fingerprint,
        domain_pack_version=plan.domain_pack_version,
        plan_type=plan.plan_type,
        anchors=plan.anchors,
        steps=plan.steps,
        projection=plan.projection,
        bounds=plan.bounds,
        world=plan.world,
        declared_capabilities=plan.declared_capabilities,
        capability_use=plan.capability_use,
        normative_constraints=plan.normative_constraints,
        aggregation=plan.aggregation,
    )
    if not plan.steps and plan.plan_type == CanonicalPlanType.TRAVERSE:
        used = {_upper(item.capability_id) for item in plan.capability_use}
        if _upper(plan.projection.kind) == "NODE_ONLY" and "ENTITY_LOOKUP" not in used:
            raise CanonicalPlanValidationError("direct_lookup_capability_required")
        if int(plan.bounds.max_hops) != 0:
            raise CanonicalPlanValidationError("zero_hop_plan_requires_zero_max_hops")
    if plan.semantic_program is not None:
        if _text(plan.semantic_program.source) != "query.semantic_programs":
            raise CanonicalPlanValidationError("non_canonical_semantic_program_source")
        if not _text(plan.semantic_program.program_id):
            raise CanonicalPlanValidationError("semantic_program_id_required")
    _validate_type_chain(plan)
    _validate_composition(plan)


def _expected_operation(plan_type: CanonicalPlanType, composite: bool = False) -> str:
    if composite:
        return "COMPOSITE"
    return {
        CanonicalPlanType.TRAVERSE: "TRAVERSE",
        CanonicalPlanType.EXISTS: "EXISTS",
        CanonicalPlanType.BOOLEAN_CHECK: "BOOLEAN_CHECK",
        CanonicalPlanType.AGGREGATE: "AGGREGATE",
        CanonicalPlanType.COMPOSITE: "COMPOSITE",
    }[plan_type]


def _validate_execution_composition(plan: CanonicalExecutionPlan) -> None:
    units = tuple(plan.composition_units or ())
    if plan.plan_type == CanonicalPlanType.COMPOSITE and len(units) < 2:
        raise CanonicalPlanValidationError("executable_composite_requires_multiple_units")
    if plan.plan_type != CanonicalPlanType.COMPOSITE and units:
        raise CanonicalPlanValidationError("executable_non_composite_has_units")
    ids = [unit.unit_id for unit in units]
    if len(set(ids)) != len(ids):
        raise CanonicalPlanValidationError("executable_composite_unit_ids_must_be_unique")
    _cycle_check(
        ids,
        {unit.unit_id: tuple(unit.dependencies) for unit in units},
        "executable_composite",
    )
    for unit in units:
        if not _text(unit.logical_plan_digest):
            raise CanonicalPlanValidationError("executable_child_logical_digest_required")
        validate_execution_plan(unit.execution_plan)


def validate_execution_plan(plan: CanonicalExecutionPlan) -> None:
    if plan.protocol_id != CANONICAL_EXECUTION_PLAN_PROTOCOL_ID or int(plan.protocol_version) != CANONICAL_PLAN_PROTOCOL_VERSION:
        raise CanonicalPlanValidationError("execution_plan_protocol_invalid")
    if not _text(plan.source_logical_plan_digest):
        raise CanonicalPlanValidationError("source_logical_plan_digest_required")
    _validate_common_plan_fields(
        planner_id=plan.planner_id,
        domain_id=plan.domain_id,
        domain_pack_fingerprint=plan.domain_pack_fingerprint,
        domain_pack_version=plan.domain_pack_version,
        plan_type=plan.plan_type,
        anchors=plan.anchors,
        steps=plan.steps,
        projection=plan.projection,
        bounds=plan.bounds,
        world=plan.world,
        declared_capabilities=plan.declared_capabilities,
        capability_use=plan.capability_use,
        normative_constraints=plan.normative_constraints,
        aggregation=plan.aggregation,
    )
    expected = _expected_operation(plan.plan_type, bool(plan.composition_units))
    if _upper(plan.execution_operation) != expected:
        raise CanonicalPlanValidationError("execution_operation_mismatch")
    if plan.semantic_program is not None:
        if _text(plan.semantic_program.source) != "query.semantic_programs":
            raise CanonicalPlanValidationError("non_canonical_semantic_program_source")
    _validate_execution_composition(plan)


def _constraint_semantics(constraints: Sequence[NormativeSemanticConstraint]) -> List[Any]:
    return _stable_items(
        {"kind": _upper(item.kind), "value": item.value}
        for item in constraints
    )


def _capability_semantics(uses: Sequence[CanonicalCapabilityUse]) -> List[Any]:
    return _stable_items(
        {"capability_id": _upper(item.capability_id), "declared_source": item.declared_source}
        for item in uses
    )


def _aggregation_semantics(aggregation: Optional[CanonicalAggregation]) -> Optional[Dict[str, Any]]:
    if aggregation is None:
        return None
    return {
        "operation": _upper(aggregation.operation),
        "top_n": aggregation.top_n,
        "date_keys": list(aggregation.date_keys),
        "group_by_node_type": aggregation.group_by_node_type,
        "group_by_relation_type": aggregation.group_by_relation_type,
    }


def _logical_semantics(plan: CanonicalLogicalPlan) -> Dict[str, Any]:
    return {
        "plan_type": _upper(plan.plan_type),
        "anchors": [
            {"node_type": _upper(anchor.node_type), "node_id": anchor.node_id}
            for anchor in plan.anchors
        ],
        "steps": [
            {
                "relation": _upper(step.relation),
                "direction": _upper(step.direction),
                "source_type": _upper(step.source_type),
                "target_type": _upper(step.target_type),
            }
            for step in plan.steps
        ],
        "projection": {"kind": _upper(plan.projection.kind), "fields": list(plan.projection.fields)},
        "bounds": {
            "max_hops": int(plan.bounds.max_hops),
            "max_results": int(plan.bounds.max_results),
            "cardinality_cap_per_hop": int(plan.bounds.cardinality_cap_per_hop),
        },
        "world": {
            "mode": _upper(plan.world.mode),
            "scope": plan.world.scope,
            "completeness": _upper(plan.world.completeness),
        },
        "normative_constraints": _constraint_semantics(plan.normative_constraints),
        "capability_use": _capability_semantics(plan.capability_use),
        "aggregation": _aggregation_semantics(plan.aggregation),
        "semantic_program": (
            None
            if plan.semantic_program is None
            else {"source": plan.semantic_program.source, "program_id": plan.semantic_program.program_id}
        ),
        "composition": {
            "policy": _upper(plan.composition_policy),
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "dependencies": list(unit.dependencies),
                    "required": bool(unit.required),
                    "semantics": _logical_semantics(unit.logical_plan),
                }
                for unit in plan.composition_units
            ],
        },
    }


def _execution_semantics(plan: CanonicalExecutionPlan) -> Dict[str, Any]:
    return {
        "plan_type": _upper(plan.plan_type),
        "anchors": [
            {"node_type": _upper(anchor.node_type), "node_id": anchor.node_id}
            for anchor in plan.anchors
        ],
        "steps": [
            {
                "relation": _upper(step.relation),
                "direction": _upper(step.direction),
                "source_type": _upper(step.source_type),
                "target_type": _upper(step.target_type),
            }
            for step in plan.steps
        ],
        "projection": {"kind": _upper(plan.projection.kind), "fields": list(plan.projection.fields)},
        "bounds": {
            "max_hops": int(plan.bounds.max_hops),
            "max_results": int(plan.bounds.max_results),
            "cardinality_cap_per_hop": int(plan.bounds.cardinality_cap_per_hop),
        },
        "world": {
            "mode": _upper(plan.world.mode),
            "scope": plan.world.scope,
            "completeness": _upper(plan.world.completeness),
        },
        "normative_constraints": _constraint_semantics(plan.normative_constraints),
        "capability_use": _capability_semantics(plan.capability_use),
        "aggregation": _aggregation_semantics(plan.aggregation),
        "semantic_program": (
            None
            if plan.semantic_program is None
            else {"source": plan.semantic_program.source, "program_id": plan.semantic_program.program_id}
        ),
        "composition": {
            "policy": _upper(plan.composition_policy),
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "dependencies": list(unit.dependencies),
                    "required": bool(unit.required),
                    "semantics": _execution_semantics(unit.execution_plan),
                }
                for unit in plan.composition_units
            ],
        },
    }


def execution_semantics(plan: Any) -> Dict[str, Any]:
    """Return the shared field-level execution-semantic projection."""

    if isinstance(plan, CanonicalLogicalPlan):
        return _logical_semantics(plan)
    if isinstance(plan, CanonicalExecutionPlan):
        return _execution_semantics(plan)
    raise TypeError("execution_semantics_requires_canonical_plan")


def logical_plan_identity(plan: CanonicalLogicalPlan) -> Dict[str, Any]:
    """Return all canonical logical identity inputs, excluding annotations."""

    validate_logical_plan(plan)
    return {
        "protocol_id": plan.protocol_id,
        "protocol_version": plan.protocol_version,
        "planner_id": plan.planner_id,
        "domain_id": plan.domain_id,
        "domain_pack_fingerprint": plan.domain_pack_fingerprint,
        "domain_pack_version": plan.domain_pack_version,
        "semantic": execution_semantics(plan),
        "annotations_excluded": True,
    }


def logical_plan_digest(plan: CanonicalLogicalPlan) -> str:
    return semantic_fingerprint(logical_plan_identity(plan))


def execution_plan_identity(plan: CanonicalExecutionPlan) -> Dict[str, Any]:
    validate_execution_plan(plan)
    return {
        "protocol_id": plan.protocol_id,
        "protocol_version": plan.protocol_version,
        "source_logical_plan_digest": plan.source_logical_plan_digest,
        "planner_id": plan.planner_id,
        "domain_id": plan.domain_id,
        "domain_pack_fingerprint": plan.domain_pack_fingerprint,
        "domain_pack_version": plan.domain_pack_version,
        "semantic": execution_semantics(plan),
    }


def execution_plan_digest(plan: CanonicalExecutionPlan) -> str:
    return semantic_fingerprint(execution_plan_identity(plan))


def lower_logical_plan(plan: CanonicalLogicalPlan) -> CanonicalExecutionPlan:
    """Lower one validated logical plan without compiling or resolving anything."""

    validate_logical_plan(plan)
    child_units: List[CanonicalExecutionUnit] = []
    for unit in plan.composition_units:
        child_execution = lower_logical_plan(unit.logical_plan)
        child_units.append(
            CanonicalExecutionUnit(
                unit_id=unit.unit_id,
                execution_plan=child_execution,
                logical_plan_digest=logical_plan_digest(unit.logical_plan),
                dependencies=tuple(unit.dependencies),
                required=bool(unit.required),
            )
        )

    executable = CanonicalExecutionPlan(
        planner_id=plan.planner_id,
        domain_id=plan.domain_id,
        domain_pack_fingerprint=plan.domain_pack_fingerprint,
        domain_pack_version=plan.domain_pack_version,
        source_logical_plan_digest=logical_plan_digest(plan),
        plan_type=plan.plan_type,
        execution_operation=_expected_operation(plan.plan_type, bool(child_units)),
        anchors=tuple(plan.anchors),
        steps=tuple(plan.steps),
        projection=plan.projection,
        bounds=plan.bounds,
        world=plan.world,
        declared_capabilities=tuple(plan.declared_capabilities),
        capability_use=tuple(plan.capability_use),
        normative_constraints=tuple(plan.normative_constraints),
        aggregation=plan.aggregation,
        composition_units=tuple(child_units),
        composition_policy=plan.composition_policy,
        semantic_program=plan.semantic_program,
    )
    validate_execution_plan(executable)
    if execution_semantics(plan) != execution_semantics(executable):
        raise CanonicalLoweringError("logical_to_execution_semantic_loss")
    return executable


def canonical_receipt_binding(
    logical: CanonicalLogicalPlan,
    executable: CanonicalExecutionPlan,
) -> Dict[str, Any]:
    """Map canonical identities to the existing R4A/R4B receipt vocabulary."""

    validate_logical_plan(logical)
    validate_execution_plan(executable)
    if executable.source_logical_plan_digest != logical_plan_digest(logical):
        raise CanonicalLoweringError("receipt_binding_logical_digest_mismatch")

    child_bindings = []
    if logical.plan_type == CanonicalPlanType.COMPOSITE:
        if len(logical.composition_units) != len(executable.composition_units):
            raise CanonicalLoweringError("receipt_binding_child_count_mismatch")
        for logical_unit, executable_unit in zip(logical.composition_units, executable.composition_units):
            child_binding = canonical_receipt_binding(logical_unit.logical_plan, executable_unit.execution_plan)
            child_binding["unit_id"] = logical_unit.unit_id
            child_bindings.append(child_binding)

    return {
        "receipt_version": "iarag.execution_receipt.v1",
        "planner_id": logical.planner_id,
        "logical_plan_id": logical_plan_digest(logical),
        "executable_plan_id": execution_plan_digest(executable),
        "domain_name": logical.domain_id,
        "domain_pack_identity": logical.domain_pack_fingerprint,
        "execution_status": "planned",
        "composition_policy": _upper(logical.composition_policy),
        "child_receipts": child_bindings,
    }
