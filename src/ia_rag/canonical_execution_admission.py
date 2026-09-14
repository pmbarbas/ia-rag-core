"""Native, non-executing admission for canonical executable plans.

This module is the R4F native execution-admission seam.  It deliberately does
not import historical compatibility implementations.  Admission validates and
records the already-lowered canonical executable plan without copying,
translating, executing, binding, or emitting an execution receipt.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

from .canonical_plan import (
    CANONICAL_EXECUTION_PLAN_PROTOCOL_ID,
    CANONICAL_PLAN_PROTOCOL_VERSION,
    CanonicalExecutionPlan,
    CanonicalLogicalPlan,
    CanonicalPlanType,
    execution_plan_digest,
    logical_plan_digest,
    validate_execution_plan,
    validate_logical_plan,
)


class CanonicalExecutionAdmissionError(ValueError):
    """Raised when a canonical executable plan cannot be admitted safely."""


class CanonicalAdmissionFieldClassification(str, Enum):
    """Boundary status; preservation is not the same as enforcement."""

    PRESENT_AND_PRESERVED = "PRESENT_AND_PRESERVED"
    REQUIRES_FUTURE_ENFORCEMENT = "REQUIRES_FUTURE_ENFORCEMENT"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class CanonicalExecutionChildAdmission:
    """Exact child identity retained under one admitted composite parent."""

    unit_id: str
    executable_plan: CanonicalExecutionPlan
    executable_plan_digest: str
    source_logical_plan_digest: str
    dependencies: Tuple[str, ...]
    required: bool
    parent_executable_plan_digest: str


@dataclass(frozen=True)
class CanonicalExecutionAdmission:
    """Preparation status for one exact canonical executable plan.

    ``executable_plan`` is the exact object supplied to admission.  The
    admission contract intentionally has no execution receipt and no result
    field.  A later wave may use this object to establish a receipt bridge,
    but admission itself cannot claim execution occurred.
    """

    executable_plan: CanonicalExecutionPlan
    executable_plan_digest: str
    source_logical_plan_digest: str
    planner_id: str
    domain_id: str
    domain_pack_fingerprint: str
    domain_pack_version: str
    field_classifications: Tuple[Tuple[str, CanonicalAdmissionFieldClassification], ...]
    child_admissions: Tuple[CanonicalExecutionChildAdmission, ...] = ()
    source_logical_plan_verified: bool = False
    admission_status: str = "ADMITTED"

    @property
    def plan(self) -> CanonicalExecutionPlan:
        """Compatibility spelling for the exact admitted plan reference."""

        return self.executable_plan

    @property
    def status(self) -> str:
        """Preparation status, deliberately distinct from execution status."""

        return self.admission_status

    @property
    def is_executed(self) -> bool:
        return False

    def classification(self, field_name: str) -> CanonicalAdmissionFieldClassification:
        for name, classification in self.field_classifications:
            if name == field_name:
                return classification
        return CanonicalAdmissionFieldClassification.UNSUPPORTED

    def field_values(self) -> Dict[str, Any]:
        """Expose the preserved values without reconstructing a plan.

        Values are read directly from the exact admitted object.  The mapping
        is a view-shaped convenience for diagnostics, not a replacement plan.
        """

        return canonical_execution_field_values(self.executable_plan)


_PLAN_FIELD_NAMES = frozenset(
    {
        "planner_id",
        "domain_id",
        "domain_pack_fingerprint",
        "domain_pack_version",
        "source_logical_plan_digest",
        "plan_type",
        "execution_operation",
        "anchors",
        "steps",
        "projection",
        "bounds",
        "world",
        "declared_capabilities",
        "capability_use",
        "normative_constraints",
        "aggregation",
        "composition_units",
        "composition_policy",
        "semantic_program",
        "protocol_id",
        "protocol_version",
    }
)


_PRESENT_FIELDS = frozenset(
    {
        "protocol_id",
        "protocol_version",
        "planner_id",
        "domain_id",
        "domain_pack_fingerprint",
        "domain_pack_version",
        "source_logical_plan_digest",
        "plan_type",
        "execution_operation",
        "anchors",
        "steps",
        "projection",
        "aggregation",
        "composition_policy",
        "composition_units",
        "semantic_program",
    }
)


_FUTURE_ENFORCEMENT_FIELDS = frozenset(
    {
        "bounds",
        "bounds.max_hops",
        "bounds.max_results",
        "bounds.cardinality_cap_per_hop",
        "world",
        "declared_capabilities",
        "capability_use",
        "normative_constraints",
    }
)


def canonical_admission_field_classification(
    field_name: str,
) -> CanonicalAdmissionFieldClassification:
    """Classify a field without confusing carriage with enforcement."""

    if field_name in _PRESENT_FIELDS:
        return CanonicalAdmissionFieldClassification.PRESENT_AND_PRESERVED
    if field_name in _FUTURE_ENFORCEMENT_FIELDS:
        return CanonicalAdmissionFieldClassification.REQUIRES_FUTURE_ENFORCEMENT
    return CanonicalAdmissionFieldClassification.UNSUPPORTED


def canonical_execution_field_values(plan: CanonicalExecutionPlan) -> Dict[str, Any]:
    """Return every execution-relevant canonical value from ``plan``.

    The function intentionally returns references to the plan's immutable
    values rather than constructing a historical or normalized plan.  A new
    canonical plan field causes admission to fail closed until explicitly
    classified here.
    """

    if type(plan) is not CanonicalExecutionPlan:
        raise CanonicalExecutionAdmissionError("canonical_execution_plan_type_required")
    actual_fields = {item.name for item in fields(CanonicalExecutionPlan)}
    unsupported_fields = sorted(actual_fields - _PLAN_FIELD_NAMES)
    if unsupported_fields:
        raise CanonicalExecutionAdmissionError(
            "canonical_execution_field_unsupported:" + ",".join(unsupported_fields)
        )
    return {
        "protocol_id": plan.protocol_id,
        "protocol_version": plan.protocol_version,
        "planner_id": plan.planner_id,
        "domain_id": plan.domain_id,
        "domain_pack_fingerprint": plan.domain_pack_fingerprint,
        "domain_pack_version": plan.domain_pack_version,
        "source_logical_plan_digest": plan.source_logical_plan_digest,
        "plan_type": plan.plan_type,
        "execution_operation": plan.execution_operation,
        "anchors": plan.anchors,
        "steps": plan.steps,
        "projection": plan.projection,
        "bounds": plan.bounds,
        "bounds.max_hops": plan.bounds.max_hops,
        "bounds.max_results": plan.bounds.max_results,
        "bounds.cardinality_cap_per_hop": plan.bounds.cardinality_cap_per_hop,
        "world": plan.world,
        "declared_capabilities": plan.declared_capabilities,
        "capability_use": plan.capability_use,
        "normative_constraints": plan.normative_constraints,
        "aggregation": plan.aggregation,
        "composition_policy": plan.composition_policy,
        "composition_units": plan.composition_units,
        "semantic_program": plan.semantic_program,
    }


def _compare_identity(label: str, actual: Any, expected: Any) -> None:
    if expected is not None and actual != expected:
        raise CanonicalExecutionAdmissionError(
            f"canonical_admission_{label}_mismatch:expected={expected!r}:actual={actual!r}"
        )


def _field_classifications() -> Tuple[Tuple[str, CanonicalAdmissionFieldClassification], ...]:
    names = (
        "protocol_id",
        "protocol_version",
        "planner_id",
        "domain_id",
        "domain_pack_fingerprint",
        "domain_pack_version",
        "source_logical_plan_digest",
        "plan_type",
        "execution_operation",
        "anchors",
        "steps",
        "projection",
        "bounds",
        "bounds.max_hops",
        "bounds.max_results",
        "bounds.cardinality_cap_per_hop",
        "world",
        "declared_capabilities",
        "capability_use",
        "normative_constraints",
        "aggregation",
        "composition_policy",
        "composition_units",
        "semantic_program",
    )
    return tuple((name, canonical_admission_field_classification(name)) for name in names)


def _admit_child(
    *,
    parent: CanonicalExecutionPlan,
    unit: Any,
    logical_unit: Any = None,
    expected_child_digest: Optional[str] = None,
) -> CanonicalExecutionChildAdmission:
    child = unit.execution_plan
    if type(child) is not CanonicalExecutionPlan:
        raise CanonicalExecutionAdmissionError("canonical_child_execution_plan_type_required")
    if child.planner_id != parent.planner_id:
        raise CanonicalExecutionAdmissionError("canonical_child_planner_identity_mismatch")
    if child.domain_id != parent.domain_id:
        raise CanonicalExecutionAdmissionError("canonical_child_domain_identity_mismatch")
    if child.domain_pack_fingerprint != parent.domain_pack_fingerprint:
        raise CanonicalExecutionAdmissionError("canonical_child_domain_pack_identity_mismatch")
    if child.domain_pack_version != parent.domain_pack_version:
        raise CanonicalExecutionAdmissionError("canonical_child_domain_pack_version_mismatch")

    validate_execution_plan(child)
    child_digest = execution_plan_digest(child)
    _compare_identity("child_executable_plan_digest", child_digest, expected_child_digest)
    if not unit.logical_plan_digest:
        raise CanonicalExecutionAdmissionError("canonical_child_logical_digest_missing")
    if child.source_logical_plan_digest != unit.logical_plan_digest:
        raise CanonicalExecutionAdmissionError("canonical_child_logical_digest_mismatch")
    if logical_unit is not None:
        expected_logical_digest = logical_plan_digest(logical_unit.logical_plan)
        if unit.logical_plan_digest != expected_logical_digest:
            raise CanonicalExecutionAdmissionError("canonical_child_source_logical_identity_mismatch")

    return CanonicalExecutionChildAdmission(
        unit_id=str(unit.unit_id),
        executable_plan=child,
        executable_plan_digest=child_digest,
        source_logical_plan_digest=child.source_logical_plan_digest,
        dependencies=tuple(unit.dependencies),
        required=bool(unit.required),
        parent_executable_plan_digest=execution_plan_digest(parent),
    )


def admit_canonical_execution(
    plan: CanonicalExecutionPlan,
    *,
    logical_plan: Optional[CanonicalLogicalPlan] = None,
    expected_executable_plan_digest: Optional[str] = None,
    expected_source_logical_plan_digest: Optional[str] = None,
    expected_planner_id: Optional[str] = None,
    expected_domain_id: Optional[str] = None,
    expected_domain_pack_fingerprint: Optional[str] = None,
    expected_domain_pack_version: Optional[str] = None,
    expected_child_executable_plan_digests: Optional[Mapping[str, str]] = None,
) -> CanonicalExecutionAdmission:
    """Admit one already validated canonical executable plan.

    This is an identity and field-visibility boundary only.  It never invokes
    a compiler, lowering function, resolver, graph store, assurance provider,
    historical plan constructor, execution operation, or receipt constructor.

    ``logical_plan`` is optional to support callers that already hold an
    externally verified source digest.  One of ``logical_plan`` or
    ``expected_source_logical_plan_digest`` is required, so a self-asserted
    executable source digest cannot be admitted without an identity anchor.
    When a logical plan is supplied, its canonical digest is recomputed and
    checked recursively against the executable lineage.
    """

    if type(plan) is not CanonicalExecutionPlan:
        raise CanonicalExecutionAdmissionError("canonical_execution_plan_type_required")

    try:
        validate_execution_plan(plan)
        values = canonical_execution_field_values(plan)
    except CanonicalExecutionAdmissionError:
        raise
    except Exception as exc:
        raise CanonicalExecutionAdmissionError(
            f"canonical_execution_plan_invalid:{exc}"
        ) from exc

    if plan.protocol_id != CANONICAL_EXECUTION_PLAN_PROTOCOL_ID:
        raise CanonicalExecutionAdmissionError("canonical_execution_protocol_id_mismatch")
    if int(plan.protocol_version) != CANONICAL_PLAN_PROTOCOL_VERSION:
        raise CanonicalExecutionAdmissionError("canonical_execution_protocol_version_mismatch")

    executable_digest = execution_plan_digest(plan)
    _compare_identity(
        "executable_plan_digest",
        executable_digest,
        expected_executable_plan_digest,
    )
    if not plan.source_logical_plan_digest:
        raise CanonicalExecutionAdmissionError("canonical_source_logical_digest_missing")
    _compare_identity(
        "source_logical_plan_digest",
        plan.source_logical_plan_digest,
        expected_source_logical_plan_digest,
    )

    if logical_plan is None and expected_source_logical_plan_digest is None:
        raise CanonicalExecutionAdmissionError(
            "canonical_source_logical_digest_context_required"
        )

    source_verified = False
    if logical_plan is not None:
        try:
            validate_logical_plan(logical_plan)
        except Exception as exc:
            raise CanonicalExecutionAdmissionError(
                f"canonical_source_logical_plan_invalid:{exc}"
            ) from exc
        source_digest = logical_plan_digest(logical_plan)
        _compare_identity(
            "source_logical_plan_digest",
            plan.source_logical_plan_digest,
            source_digest,
        )
        _compare_identity("planner_id", plan.planner_id, logical_plan.planner_id)
        _compare_identity("domain_id", plan.domain_id, logical_plan.domain_id)
        _compare_identity(
            "domain_pack_fingerprint",
            plan.domain_pack_fingerprint,
            logical_plan.domain_pack_fingerprint,
        )
        _compare_identity(
            "domain_pack_version",
            plan.domain_pack_version,
            logical_plan.domain_pack_version,
        )
        if plan.plan_type != logical_plan.plan_type:
            raise CanonicalExecutionAdmissionError("canonical_plan_type_lineage_mismatch")
        source_verified = True

    _compare_identity("planner_id", plan.planner_id, expected_planner_id)
    _compare_identity("domain_id", plan.domain_id, expected_domain_id)
    _compare_identity(
        "domain_pack_fingerprint",
        plan.domain_pack_fingerprint,
        expected_domain_pack_fingerprint,
    )
    _compare_identity(
        "domain_pack_version",
        plan.domain_pack_version,
        expected_domain_pack_version,
    )

    expected_children = dict(expected_child_executable_plan_digests or {})
    child_admissions = []
    if plan.plan_type == CanonicalPlanType.COMPOSITE:
        logical_units = tuple(logical_plan.composition_units) if logical_plan is not None else ()
        if logical_plan is not None and len(logical_units) != len(plan.composition_units):
            raise CanonicalExecutionAdmissionError("canonical_composite_logical_child_count_mismatch")
        actual_child_ids = []
        for index, unit in enumerate(plan.composition_units):
            actual_child_ids.append(str(unit.unit_id))
            logical_unit = logical_units[index] if logical_plan is not None else None
            child_admissions.append(
                _admit_child(
                    parent=plan,
                    unit=unit,
                    logical_unit=logical_unit,
                    expected_child_digest=expected_children.get(str(unit.unit_id)),
                )
            )
        if expected_children and set(expected_children) != set(actual_child_ids):
            raise CanonicalExecutionAdmissionError("canonical_child_digest_set_mismatch")
    elif expected_children:
        raise CanonicalExecutionAdmissionError("canonical_non_composite_has_child_digests")

    # Force materialization of the complete field contract before returning.
    # ``values`` is intentionally not serialized or normalized; it proves that
    # every field is visible at this native boundary.
    if set(values) != {
        "protocol_id",
        "protocol_version",
        "planner_id",
        "domain_id",
        "domain_pack_fingerprint",
        "domain_pack_version",
        "source_logical_plan_digest",
        "plan_type",
        "execution_operation",
        "anchors",
        "steps",
        "projection",
        "bounds",
        "bounds.max_hops",
        "bounds.max_results",
        "bounds.cardinality_cap_per_hop",
        "world",
        "declared_capabilities",
        "capability_use",
        "normative_constraints",
        "aggregation",
        "composition_policy",
        "composition_units",
        "semantic_program",
    }:
        raise CanonicalExecutionAdmissionError("canonical_execution_field_visibility_incomplete")

    return CanonicalExecutionAdmission(
        executable_plan=plan,
        executable_plan_digest=executable_digest,
        source_logical_plan_digest=plan.source_logical_plan_digest,
        planner_id=plan.planner_id,
        domain_id=plan.domain_id,
        domain_pack_fingerprint=plan.domain_pack_fingerprint,
        domain_pack_version=plan.domain_pack_version,
        field_classifications=_field_classifications(),
        child_admissions=tuple(child_admissions),
        source_logical_plan_verified=source_verified,
    )
