"""Neutral v2 receipts for the future canonical execution boundary.

R4F-3 closes the identity bridge without activating canonical execution.  The
receipt contract binds exact canonical logical/executable plan digests,
typed R4F-2 enforcement references, optional neutral assurance references,
and synthetic execution outcomes.  It does not import or extend the
historical receipt, execute a plan, interpret
truth, render a result, or construct a concrete assurance object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .canonical_execution_enforcement import (
    CANONICAL_ENFORCEMENT_PROTOCOL_ID,
    CANONICAL_ENFORCEMENT_PROTOCOL_VERSION,
    CanonicalEnforcementDecision,
    CanonicalEnforcementPhase,
    CanonicalEnforcementStatus,
)
from .canonical_plan import (
    CanonicalExecutionPlan,
    CanonicalLogicalPlan,
    CanonicalPlanType,
    CanonicalPlanValidationError,
    execution_plan_digest,
    logical_plan_digest,
    validate_execution_plan,
    validate_logical_plan,
)
from .canonical_semantic_contract import semantic_fingerprint


CANONICAL_EXECUTION_RECEIPT_PROTOCOL_ID = "ia-rag.execution-receipt.v2"
CANONICAL_EXECUTION_RECEIPT_PROTOCOL_VERSION = 2


class CanonicalReceiptBindingError(ValueError):
    """Raised when receipt state or identity cannot be bound fail-closed."""


class CanonicalReceiptStatus(str, Enum):
    PREPARED = "PREPARED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    POSTCHECK_FAILED = "POSTCHECK_FAILED"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"


class CanonicalExecutionOutcomeStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(getattr(value, "value", value)).upper()


def _receipt_digest(value: Any) -> str:
    return semantic_fingerprint(value)


def _normalise_receipt_status(value: Any) -> CanonicalReceiptStatus:
    try:
        return value if isinstance(value, CanonicalReceiptStatus) else CanonicalReceiptStatus(_upper(value))
    except ValueError as exc:
        raise CanonicalReceiptBindingError(f"receipt_status_invalid:{value}") from exc


def _normalise_outcome_status(value: Any) -> CanonicalExecutionOutcomeStatus:
    try:
        return value if isinstance(value, CanonicalExecutionOutcomeStatus) else CanonicalExecutionOutcomeStatus(_upper(value))
    except ValueError as exc:
        raise CanonicalReceiptBindingError(f"execution_outcome_status_invalid:{value}") from exc


@dataclass(frozen=True)
class CanonicalEnforcementBinding:
    """Opaque reference to one R4F-2 decision; no reason logic is duplicated."""

    protocol_id: str
    protocol_version: int
    phase: CanonicalEnforcementPhase
    executable_plan_digest: str
    decision_status: CanonicalEnforcementStatus
    decision_reference: str

    def __post_init__(self) -> None:
        if self.protocol_id != CANONICAL_ENFORCEMENT_PROTOCOL_ID:
            raise CanonicalReceiptBindingError("enforcement_protocol_mismatch")
        if int(self.protocol_version) != CANONICAL_ENFORCEMENT_PROTOCOL_VERSION:
            raise CanonicalReceiptBindingError("enforcement_protocol_version_mismatch")
        try:
            phase = self.phase if isinstance(self.phase, CanonicalEnforcementPhase) else CanonicalEnforcementPhase(_upper(self.phase))
            status = self.decision_status if isinstance(self.decision_status, CanonicalEnforcementStatus) else CanonicalEnforcementStatus(_upper(self.decision_status))
        except ValueError as exc:
            raise CanonicalReceiptBindingError("enforcement_binding_state_invalid") from exc
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "decision_status", status)
        if not _text(self.executable_plan_digest):
            raise CanonicalReceiptBindingError("enforcement_binding_plan_digest_required")
        if not _text(self.decision_reference):
            raise CanonicalReceiptBindingError("enforcement_decision_reference_required")

    @classmethod
    def from_decision(
        cls,
        decision: CanonicalEnforcementDecision,
        *,
        decision_reference: Optional[str] = None,
    ) -> "CanonicalEnforcementBinding":
        if type(decision) is not CanonicalEnforcementDecision:
            raise CanonicalReceiptBindingError("canonical_enforcement_decision_required")
        reference = decision_reference or _receipt_digest(
            {
                "protocol_id": CANONICAL_ENFORCEMENT_PROTOCOL_ID,
                "protocol_version": CANONICAL_ENFORCEMENT_PROTOCOL_VERSION,
                "phase": decision.phase.value,
                "plan_digest": decision.executable_plan_digest,
                "status": decision.status.value,
                "allowed": decision.allowed,
                "constraints": list(decision.evaluated_constraints),
                "capabilities": list(decision.evaluated_capabilities),
                "evidence": list(decision.evidence_references),
                "children": [child.plan_digest for child in decision.child_decisions],
            }
        )
        return cls(
            protocol_id=CANONICAL_ENFORCEMENT_PROTOCOL_ID,
            protocol_version=CANONICAL_ENFORCEMENT_PROTOCOL_VERSION,
            phase=decision.phase,
            executable_plan_digest=decision.executable_plan_digest,
            decision_status=decision.status,
            decision_reference=reference,
        )


@dataclass(frozen=True)
class CanonicalAssuranceReference:
    """Neutral reference to an assurance decision, never the decision object."""

    protocol_id: str
    protocol_version: int
    executable_plan_digest: str
    decision_status: str
    decision_reference: str

    def __post_init__(self) -> None:
        if not _text(self.protocol_id) or int(self.protocol_version) <= 0:
            raise CanonicalReceiptBindingError("assurance_reference_protocol_invalid")
        if not _text(self.executable_plan_digest):
            raise CanonicalReceiptBindingError("assurance_reference_plan_digest_required")
        if not _text(self.decision_status) or not _text(self.decision_reference):
            raise CanonicalReceiptBindingError("assurance_reference_decision_required")


# Alias for composition roots that use binding terminology.
CanonicalAssuranceBinding = CanonicalAssuranceReference


@dataclass(frozen=True)
class CanonicalExecutionChildOutcome:
    """Synthetic execution outcome for one exact composite child."""

    unit_id: str
    logical_plan_digest: str
    executable_plan_digest: str
    status: CanonicalExecutionOutcomeStatus
    execution_instance_reference: str
    result_reference: str = ""
    evidence_reference: str = ""
    dependencies: Tuple[str, ...] = ()
    required: bool = True
    outcome_reference: str = ""

    def __post_init__(self) -> None:
        status = _normalise_outcome_status(self.status)
        object.__setattr__(self, "status", status)
        if not _text(self.unit_id) or not _text(self.logical_plan_digest) or not _text(self.executable_plan_digest):
            raise CanonicalReceiptBindingError("child_execution_outcome_identity_required")
        if not _text(self.execution_instance_reference):
            raise CanonicalReceiptBindingError("child_execution_instance_reference_required")
        if status == CanonicalExecutionOutcomeStatus.SUCCEEDED and (
            not _text(self.result_reference) or not _text(self.evidence_reference)
        ):
            raise CanonicalReceiptBindingError("child_success_result_evidence_reference_required")
        if not self.outcome_reference:
            object.__setattr__(self, "outcome_reference", _receipt_digest(self.identity_payload()))

    def identity_payload(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "logical_plan_digest": self.logical_plan_digest,
            "executable_plan_digest": self.executable_plan_digest,
            "status": self.status.value,
            "execution_instance_reference": self.execution_instance_reference,
            "result_reference": self.result_reference,
            "evidence_reference": self.evidence_reference,
            "dependencies": list(self.dependencies),
            "required": bool(self.required),
        }


@dataclass(frozen=True)
class CanonicalExecutionOutcome:
    """Minimum neutral outcome needed to cross the future execution boundary."""

    executable_plan_digest: str
    status: CanonicalExecutionOutcomeStatus
    execution_instance_reference: str
    result_reference: str = ""
    evidence_reference: str = ""
    child_outcomes: Tuple[CanonicalExecutionChildOutcome, ...] = ()
    outcome_reference: str = ""

    def __post_init__(self) -> None:
        status = _normalise_outcome_status(self.status)
        object.__setattr__(self, "status", status)
        if not _text(self.executable_plan_digest):
            raise CanonicalReceiptBindingError("execution_outcome_plan_digest_required")
        if not _text(self.execution_instance_reference):
            raise CanonicalReceiptBindingError("execution_instance_reference_required")
        if status == CanonicalExecutionOutcomeStatus.SUCCEEDED and (
            not _text(self.result_reference) or not _text(self.evidence_reference)
        ):
            raise CanonicalReceiptBindingError("success_result_evidence_reference_required")
        if not self.outcome_reference:
            object.__setattr__(self, "outcome_reference", _receipt_digest(self.identity_payload()))

    @property
    def succeeded(self) -> bool:
        return self.status == CanonicalExecutionOutcomeStatus.SUCCEEDED

    def identity_payload(self) -> Dict[str, Any]:
        return {
            "executable_plan_digest": self.executable_plan_digest,
            "status": self.status.value,
            "execution_instance_reference": self.execution_instance_reference,
            "result_reference": self.result_reference,
            "evidence_reference": self.evidence_reference,
            "children": [item.identity_payload() for item in self.child_outcomes],
        }


def _enforcement_payload(binding: Optional[CanonicalEnforcementBinding]) -> Optional[Dict[str, Any]]:
    if binding is None:
        return None
    return {
        "protocol_id": binding.protocol_id,
        "protocol_version": binding.protocol_version,
        "phase": binding.phase.value,
        "executable_plan_digest": binding.executable_plan_digest,
        "decision_status": binding.decision_status.value,
        "decision_reference": binding.decision_reference,
    }


def _assurance_payload(binding: Optional[CanonicalAssuranceReference]) -> Optional[Dict[str, Any]]:
    if binding is None:
        return None
    return {
        "protocol_id": binding.protocol_id,
        "protocol_version": binding.protocol_version,
        "executable_plan_digest": binding.executable_plan_digest,
        "decision_status": binding.decision_status,
        "decision_reference": binding.decision_reference,
    }


def _receipt_identity_payload(receipt: "CanonicalExecutionReceipt") -> Dict[str, Any]:
    """Return only immutable execution-authoritative receipt identity fields."""

    return {
        "protocol_id": receipt.protocol_id,
        "protocol_version": receipt.protocol_version,
        "planner_id": receipt.planner_id,
        "domain_id": receipt.domain_id,
        "domain_pack_fingerprint": receipt.domain_pack_fingerprint,
        "domain_pack_version": receipt.domain_pack_version,
        "logical_plan_digest": receipt.canonical_logical_plan_digest,
        "executable_plan_digest": receipt.canonical_executable_plan_digest,
        "execution_status": receipt.execution_status.value,
        "result_reference": receipt.result_reference,
        "evidence_reference": receipt.evidence_reference,
        "evidence_references": list(receipt.evidence_references),
        "execution_instance_reference": receipt.execution_instance_reference,
        "execution_outcome_reference": receipt.execution_outcome_reference,
        "pre_enforcement": _enforcement_payload(receipt.pre_enforcement),
        "post_enforcement": _enforcement_payload(receipt.post_enforcement),
        "assurance": _assurance_payload(receipt.assurance),
        "composition_policy": receipt.composition_policy,
        "unit_id": receipt.unit_id,
        "parent_executable_plan_digest": receipt.parent_executable_plan_digest,
        "dependencies": list(receipt.dependencies),
        "required": bool(receipt.required),
        "children": [child.receipt_digest for child in receipt.child_receipts],
    }


@dataclass(frozen=True)
class CanonicalExecutionReceipt:
    """Immutable v2 receipt binding the future canonical execution chain."""

    protocol_id: str
    protocol_version: int
    planner_id: str
    domain_id: str
    domain_pack_fingerprint: str
    domain_pack_version: str
    canonical_logical_plan_digest: str
    canonical_executable_plan_digest: str
    execution_status: CanonicalReceiptStatus
    result_reference: str = ""
    evidence_reference: str = ""
    evidence_references: Tuple[str, ...] = ()
    execution_instance_reference: str = ""
    execution_outcome_reference: str = ""
    pre_enforcement: Optional[CanonicalEnforcementBinding] = None
    post_enforcement: Optional[CanonicalEnforcementBinding] = None
    assurance: Optional[CanonicalAssuranceReference] = None
    composition_policy: str = ""
    unit_id: str = ""
    parent_executable_plan_digest: str = ""
    dependencies: Tuple[str, ...] = ()
    required: bool = True
    child_receipts: Tuple["CanonicalExecutionReceipt", ...] = ()
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        if self.protocol_id != CANONICAL_EXECUTION_RECEIPT_PROTOCOL_ID:
            raise CanonicalReceiptBindingError("receipt_protocol_mismatch")
        if int(self.protocol_version) != CANONICAL_EXECUTION_RECEIPT_PROTOCOL_VERSION:
            raise CanonicalReceiptBindingError("receipt_protocol_version_mismatch")
        status = _normalise_receipt_status(self.execution_status)
        object.__setattr__(self, "execution_status", status)
        for value, code in (
            (self.planner_id, "planner_id_required"),
            (self.domain_id, "domain_id_required"),
            (self.domain_pack_fingerprint, "domain_pack_fingerprint_required"),
            (self.domain_pack_version, "domain_pack_version_required"),
            (self.canonical_logical_plan_digest, "canonical_logical_plan_digest_required"),
            (self.canonical_executable_plan_digest, "canonical_executable_plan_digest_required"),
        ):
            if not _text(value):
                raise CanonicalReceiptBindingError(code)
        if self.pre_enforcement is not None and self.pre_enforcement.executable_plan_digest != self.canonical_executable_plan_digest:
            raise CanonicalReceiptBindingError("pre_enforcement_plan_digest_mismatch")
        if self.post_enforcement is not None and self.post_enforcement.executable_plan_digest != self.canonical_executable_plan_digest:
            raise CanonicalReceiptBindingError("post_enforcement_plan_digest_mismatch")
        if self.assurance is not None and self.assurance.executable_plan_digest != self.canonical_executable_plan_digest:
            raise CanonicalReceiptBindingError("assurance_plan_digest_mismatch")
        expected = _receipt_digest(_receipt_identity_payload(self))
        if self.receipt_digest:
            if self.receipt_digest != expected:
                raise CanonicalReceiptBindingError("receipt_digest_mismatch")
        else:
            object.__setattr__(self, "receipt_digest", expected)

    @property
    def logical_plan_digest(self) -> str:
        """Short neutral spelling; remains canonical, never historical."""

        return self.canonical_logical_plan_digest

    @property
    def executable_plan_digest(self) -> str:
        return self.canonical_executable_plan_digest

    @property
    def is_executed(self) -> bool:
        return self.execution_status in {
            CanonicalReceiptStatus.EXECUTED,
            CanonicalReceiptStatus.PARTIAL,
            CanonicalReceiptStatus.COMPLETE,
            CanonicalReceiptStatus.POSTCHECK_FAILED,
            CanonicalReceiptStatus.EXECUTION_FAILED,
        }

    @property
    def is_complete(self) -> bool:
        return self.execution_status == CanonicalReceiptStatus.COMPLETE

    @property
    def status(self) -> CanonicalReceiptStatus:
        """Short spelling for callers that model lifecycle state as status."""

        return self.execution_status

    @property
    def receipt_id(self) -> str:
        """Stable receipt identity; equivalent to ``receipt_digest``."""

        return self.receipt_digest

    @property
    def child_unit_ids(self) -> Tuple[str, ...]:
        return tuple(child.unit_id for child in self.child_receipts)

    @classmethod
    def prepare(
        cls,
        *,
        logical_plan: CanonicalLogicalPlan,
        executable_plan: CanonicalExecutionPlan,
        pre_enforcement: Optional[CanonicalEnforcementDecision] = None,
        assurance: Optional[CanonicalAssuranceReference] = None,
        planner_id: Optional[str] = None,
        domain_id: Optional[str] = None,
        domain_pack_fingerprint: Optional[str] = None,
        domain_pack_version: Optional[str] = None,
        expected_logical_plan_digest: Optional[str] = None,
        expected_executable_plan_digest: Optional[str] = None,
        composition_policy: Optional[str] = None,
        unit_id: str = "",
        parent_executable_plan_digest: str = "",
        dependencies: Sequence[str] = (),
        required: bool = True,
    ) -> "CanonicalExecutionReceipt":
        identities = _validate_plan_pair(logical_plan, executable_plan)
        expected = {
            "planner_id": planner_id,
            "domain_id": domain_id,
            "domain_pack_fingerprint": domain_pack_fingerprint,
            "domain_pack_version": domain_pack_version,
        }
        for name, supplied in expected.items():
            if supplied is not None and supplied != identities[name]:
                raise CanonicalReceiptBindingError(f"{name}_mismatch")
        if expected_logical_plan_digest is not None and expected_logical_plan_digest != identities["logical_digest"]:
            raise CanonicalReceiptBindingError("logical_plan_digest_mismatch")
        if expected_executable_plan_digest is not None and expected_executable_plan_digest != identities["executable_digest"]:
            raise CanonicalReceiptBindingError("executable_plan_digest_mismatch")
        pre_binding = _binding_for_decision(pre_enforcement, CanonicalEnforcementPhase.PRE_EXECUTION, identities["executable_digest"])
        if assurance is not None and assurance.executable_plan_digest != identities["executable_digest"]:
            raise CanonicalReceiptBindingError("assurance_plan_digest_mismatch")

        child_receipts = []
        if executable_plan.plan_type == CanonicalPlanType.COMPOSITE:
            pre_children = tuple(pre_enforcement.child_decisions) if pre_enforcement is not None else ()
            if pre_enforcement is not None and len(pre_children) != len(executable_plan.composition_units):
                raise CanonicalReceiptBindingError("composite_pre_enforcement_child_count_mismatch")
            for index, (logical_unit, executable_unit) in enumerate(
                zip(logical_plan.composition_units, executable_plan.composition_units)
            ):
                child_receipts.append(
                    cls.prepare(
                        logical_plan=logical_unit.logical_plan,
                        executable_plan=executable_unit.execution_plan,
                        pre_enforcement=pre_children[index] if pre_children else None,
                        planner_id=identities["planner_id"],
                        domain_id=identities["domain_id"],
                        domain_pack_fingerprint=identities["domain_pack_fingerprint"],
                        domain_pack_version=identities["domain_pack_version"],
                        composition_policy=executable_plan.composition_policy.value,
                        unit_id=executable_unit.unit_id,
                        parent_executable_plan_digest=identities["executable_digest"],
                        dependencies=executable_unit.dependencies,
                        required=executable_unit.required,
                    )
                )

        status = CanonicalReceiptStatus.PREPARED
        if pre_binding is not None and pre_binding.decision_status not in {
            CanonicalEnforcementStatus.ALLOWED,
            CanonicalEnforcementStatus.ALLOWED_PARTIAL,
        }:
            status = CanonicalReceiptStatus.REJECTED
        return cls(
            protocol_id=CANONICAL_EXECUTION_RECEIPT_PROTOCOL_ID,
            protocol_version=CANONICAL_EXECUTION_RECEIPT_PROTOCOL_VERSION,
            planner_id=identities["planner_id"],
            domain_id=identities["domain_id"],
            domain_pack_fingerprint=identities["domain_pack_fingerprint"],
            domain_pack_version=identities["domain_pack_version"],
            canonical_logical_plan_digest=identities["logical_digest"],
            canonical_executable_plan_digest=identities["executable_digest"],
            execution_status=status,
            pre_enforcement=pre_binding,
            assurance=assurance,
            composition_policy=composition_policy or executable_plan.composition_policy.value,
            unit_id=unit_id,
            parent_executable_plan_digest=parent_executable_plan_digest,
            dependencies=tuple(dependencies),
            required=bool(required),
            child_receipts=tuple(child_receipts),
        )

    @classmethod
    def from_admission(
        cls,
        admission: Any,
        *,
        logical_plan: CanonicalLogicalPlan,
        pre_enforcement: Optional[CanonicalEnforcementDecision] = None,
        assurance: Optional[CanonicalAssuranceReference] = None,
    ) -> "CanonicalExecutionReceipt":
        executable_plan = getattr(admission, "executable_plan", None)
        if type(executable_plan) is not CanonicalExecutionPlan:
            raise CanonicalReceiptBindingError("canonical_admission_required")
        if getattr(admission, "status", None) != "ADMITTED":
            raise CanonicalReceiptBindingError("canonical_admission_not_admitted")
        if getattr(admission, "executable_plan_digest", None) != execution_plan_digest(executable_plan):
            raise CanonicalReceiptBindingError("admission_executable_digest_mismatch")
        if getattr(admission, "source_logical_plan_digest", None) != logical_plan_digest(logical_plan):
            raise CanonicalReceiptBindingError("admission_logical_digest_mismatch")
        return cls.prepare(
            logical_plan=logical_plan,
            executable_plan=executable_plan,
            pre_enforcement=pre_enforcement,
            assurance=assurance,
        )

    def with_assurance_reference(self, assurance: CanonicalAssuranceReference) -> "CanonicalExecutionReceipt":
        if self.execution_status not in {CanonicalReceiptStatus.PREPARED, CanonicalReceiptStatus.REJECTED}:
            raise CanonicalReceiptBindingError("assurance_must_bind_before_execution")
        if assurance.executable_plan_digest != self.canonical_executable_plan_digest:
            raise CanonicalReceiptBindingError("assurance_plan_digest_mismatch")
        return self._replace(assurance=assurance)

    def with_execution_outcome(
        self,
        outcome: CanonicalExecutionOutcome,
    ) -> "CanonicalExecutionReceipt":
        if self.execution_status != CanonicalReceiptStatus.PREPARED:
            raise CanonicalReceiptBindingError("receipt_not_prepared_for_execution")
        if self.pre_enforcement is None or self.pre_enforcement.decision_status not in {
            CanonicalEnforcementStatus.ALLOWED,
            CanonicalEnforcementStatus.ALLOWED_PARTIAL,
        }:
            raise CanonicalReceiptBindingError("pre_enforcement_not_satisfied")
        self._validate_outcome_against_receipt(outcome)
        children = list(self.child_receipts)
        if children:
            for index, (child, child_outcome) in enumerate(zip(children, outcome.child_outcomes)):
                if child.execution_status == CanonicalReceiptStatus.PREPARED:
                    child = child.with_execution_outcome(
                        CanonicalExecutionOutcome(
                            executable_plan_digest=child_outcome.executable_plan_digest,
                            status=child_outcome.status,
                            execution_instance_reference=child_outcome.execution_instance_reference,
                            result_reference=child_outcome.result_reference,
                            evidence_reference=child_outcome.evidence_reference,
                            outcome_reference=child_outcome.outcome_reference,
                        )
                    )
                children[index] = child

        if outcome.status == CanonicalExecutionOutcomeStatus.FAILED:
            status = CanonicalReceiptStatus.EXECUTION_FAILED
        elif any(
            receipt.required and receipt.execution_status in {
                CanonicalReceiptStatus.REJECTED,
                CanonicalReceiptStatus.EXECUTION_FAILED,
            }
            for receipt in children
        ):
            status = CanonicalReceiptStatus.EXECUTION_FAILED
        elif self.pre_enforcement.decision_status == CanonicalEnforcementStatus.ALLOWED_PARTIAL or any(
            not receipt.required and receipt.execution_status != CanonicalReceiptStatus.EXECUTED
            for receipt in children
        ):
            status = CanonicalReceiptStatus.PARTIAL
        else:
            status = CanonicalReceiptStatus.EXECUTED
        return self._replace(
            execution_status=status,
            result_reference=outcome.result_reference,
            evidence_reference=outcome.evidence_reference,
            execution_instance_reference=outcome.execution_instance_reference,
            execution_outcome_reference=outcome.outcome_reference,
            child_receipts=tuple(children),
        )

    def with_post_enforcement(
        self,
        decision: CanonicalEnforcementDecision,
    ) -> "CanonicalExecutionReceipt":
        if self.execution_status not in {CanonicalReceiptStatus.EXECUTED, CanonicalReceiptStatus.PARTIAL}:
            raise CanonicalReceiptBindingError("receipt_not_executed_for_postcheck")
        binding = _binding_for_decision(decision, CanonicalEnforcementPhase.POST_RESULT, self.canonical_executable_plan_digest)
        children = list(self.child_receipts)
        if children:
            if len(decision.child_decisions) != len(children):
                raise CanonicalReceiptBindingError("composite_post_enforcement_child_count_mismatch")
            for index, child_decision in enumerate(decision.child_decisions):
                child = children[index]
                if child.execution_status in {CanonicalReceiptStatus.EXECUTED, CanonicalReceiptStatus.PARTIAL}:
                    children[index] = child.with_post_enforcement(child_decision)

        required_children_complete = all(
            not child.required or child.execution_status == CanonicalReceiptStatus.COMPLETE
            for child in children
        )
        if binding.decision_status == CanonicalEnforcementStatus.ALLOWED and self.execution_status == CanonicalReceiptStatus.EXECUTED and required_children_complete:
            status = CanonicalReceiptStatus.COMPLETE
        elif binding.decision_status == CanonicalEnforcementStatus.ALLOWED_PARTIAL or self.execution_status == CanonicalReceiptStatus.PARTIAL:
            status = CanonicalReceiptStatus.PARTIAL
        else:
            status = CanonicalReceiptStatus.POSTCHECK_FAILED
        return self._replace(
            execution_status=status,
            post_enforcement=binding,
            evidence_references=tuple(decision.evidence_references),
            child_receipts=tuple(children),
        )

    def assert_identity(self) -> None:
        """Verify the deterministic receipt digest and binding references."""

        expected = _receipt_digest(_receipt_identity_payload(self))
        if expected != self.receipt_digest:
            raise CanonicalReceiptBindingError("receipt_digest_mismatch")
        for child in self.child_receipts:
            child.assert_identity()
            if child.parent_executable_plan_digest != self.canonical_executable_plan_digest:
                raise CanonicalReceiptBindingError("child_receipt_parent_digest_mismatch")

    validate = assert_identity

    def assert_matches_plans(
        self,
        logical_plan: CanonicalLogicalPlan,
        executable_plan: CanonicalExecutionPlan,
    ) -> None:
        identities = _validate_plan_pair(logical_plan, executable_plan)
        if self.canonical_logical_plan_digest != identities["logical_digest"]:
            raise CanonicalReceiptBindingError("receipt_logical_plan_digest_mismatch")
        if self.canonical_executable_plan_digest != identities["executable_digest"]:
            raise CanonicalReceiptBindingError("receipt_executable_plan_digest_mismatch")
        self.assert_identity()
        if executable_plan.plan_type == CanonicalPlanType.COMPOSITE:
            if len(self.child_receipts) != len(executable_plan.composition_units):
                raise CanonicalReceiptBindingError("receipt_child_count_mismatch")
            for receipt, logical_unit, executable_unit in zip(
                self.child_receipts,
                logical_plan.composition_units,
                executable_plan.composition_units,
            ):
                if receipt.unit_id != executable_unit.unit_id:
                    raise CanonicalReceiptBindingError("receipt_child_unit_id_mismatch")
                receipt.assert_matches_plans(logical_unit.logical_plan, executable_unit.execution_plan)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "receipt_digest": self.receipt_digest,
            "planner_id": self.planner_id,
            "domain_id": self.domain_id,
            "domain_pack_fingerprint": self.domain_pack_fingerprint,
            "domain_pack_version": self.domain_pack_version,
            "canonical_logical_plan_digest": self.canonical_logical_plan_digest,
            "canonical_executable_plan_digest": self.canonical_executable_plan_digest,
            "execution_status": self.execution_status.value,
            "result_reference": self.result_reference,
            "evidence_reference": self.evidence_reference,
            "evidence_references": list(self.evidence_references),
            "execution_instance_reference": self.execution_instance_reference,
            "execution_outcome_reference": self.execution_outcome_reference,
            "pre_enforcement": _enforcement_payload(self.pre_enforcement),
            "post_enforcement": _enforcement_payload(self.post_enforcement),
            "assurance": _assurance_payload(self.assurance),
            "composition_policy": self.composition_policy,
            "unit_id": self.unit_id,
            "parent_executable_plan_digest": self.parent_executable_plan_digest,
            "dependencies": list(self.dependencies),
            "required": bool(self.required),
            "child_receipts": [child.to_dict() for child in self.child_receipts],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CanonicalExecutionReceipt":
        raw = dict(payload or {})
        return cls(
            protocol_id=str(raw.get("protocol_id") or ""),
            protocol_version=int(raw.get("protocol_version") or 0),
            receipt_digest=str(raw.get("receipt_digest") or ""),
            planner_id=str(raw.get("planner_id") or ""),
            domain_id=str(raw.get("domain_id") or ""),
            domain_pack_fingerprint=str(raw.get("domain_pack_fingerprint") or ""),
            domain_pack_version=str(raw.get("domain_pack_version") or ""),
            canonical_logical_plan_digest=str(raw.get("canonical_logical_plan_digest") or ""),
            canonical_executable_plan_digest=str(raw.get("canonical_executable_plan_digest") or ""),
            execution_status=raw.get("execution_status") or "",
            result_reference=str(raw.get("result_reference") or ""),
            evidence_reference=str(raw.get("evidence_reference") or ""),
            evidence_references=tuple(raw.get("evidence_references") or ()),
            execution_instance_reference=str(raw.get("execution_instance_reference") or ""),
            execution_outcome_reference=str(raw.get("execution_outcome_reference") or ""),
            pre_enforcement=_binding_from_dict(raw.get("pre_enforcement")),
            post_enforcement=_binding_from_dict(raw.get("post_enforcement")),
            assurance=_assurance_from_dict(raw.get("assurance")),
            composition_policy=str(raw.get("composition_policy") or ""),
            unit_id=str(raw.get("unit_id") or ""),
            parent_executable_plan_digest=str(raw.get("parent_executable_plan_digest") or ""),
            dependencies=tuple(raw.get("dependencies") or ()),
            required=bool(raw.get("required", True)),
            child_receipts=tuple(cls.from_dict(item) for item in (raw.get("child_receipts") or ()) if isinstance(item, Mapping)),
        )

    def _replace(self, **changes: Any) -> "CanonicalExecutionReceipt":
        values = {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "planner_id": self.planner_id,
            "domain_id": self.domain_id,
            "domain_pack_fingerprint": self.domain_pack_fingerprint,
            "domain_pack_version": self.domain_pack_version,
            "canonical_logical_plan_digest": self.canonical_logical_plan_digest,
            "canonical_executable_plan_digest": self.canonical_executable_plan_digest,
            "execution_status": self.execution_status,
            "result_reference": self.result_reference,
            "evidence_reference": self.evidence_reference,
            "evidence_references": self.evidence_references,
            "execution_instance_reference": self.execution_instance_reference,
            "execution_outcome_reference": self.execution_outcome_reference,
            "pre_enforcement": self.pre_enforcement,
            "post_enforcement": self.post_enforcement,
            "assurance": self.assurance,
            "composition_policy": self.composition_policy,
            "unit_id": self.unit_id,
            "parent_executable_plan_digest": self.parent_executable_plan_digest,
            "dependencies": self.dependencies,
            "required": self.required,
            "child_receipts": self.child_receipts,
        }
        values.update(changes)
        return CanonicalExecutionReceipt(**values)

    def _validate_outcome_against_receipt(self, outcome: CanonicalExecutionOutcome) -> None:
        if type(outcome) is not CanonicalExecutionOutcome:
            raise CanonicalReceiptBindingError("canonical_execution_outcome_required")
        if outcome.executable_plan_digest != self.canonical_executable_plan_digest:
            raise CanonicalReceiptBindingError("execution_outcome_plan_digest_mismatch")
        if self.child_receipts:
            if len(outcome.child_outcomes) != len(self.child_receipts):
                raise CanonicalReceiptBindingError("execution_outcome_child_count_mismatch")
            for receipt, child_outcome in zip(self.child_receipts, outcome.child_outcomes):
                if child_outcome.unit_id != receipt.unit_id:
                    raise CanonicalReceiptBindingError("execution_outcome_child_unit_id_mismatch")
                if child_outcome.logical_plan_digest != receipt.canonical_logical_plan_digest:
                    raise CanonicalReceiptBindingError("execution_outcome_child_logical_digest_mismatch")
                if child_outcome.executable_plan_digest != receipt.canonical_executable_plan_digest:
                    raise CanonicalReceiptBindingError("execution_outcome_child_executable_digest_mismatch")
                if tuple(child_outcome.dependencies) != tuple(receipt.dependencies) or bool(child_outcome.required) != bool(receipt.required):
                    raise CanonicalReceiptBindingError("execution_outcome_child_lineage_mismatch")


def _binding_for_decision(
    decision: Optional[CanonicalEnforcementDecision],
    phase: CanonicalEnforcementPhase,
    executable_digest: str,
) -> Optional[CanonicalEnforcementBinding]:
    if decision is None:
        return None
    binding = CanonicalEnforcementBinding.from_decision(decision)
    if binding.phase != phase:
        raise CanonicalReceiptBindingError("enforcement_phase_mismatch")
    if binding.executable_plan_digest != executable_digest:
        raise CanonicalReceiptBindingError("enforcement_plan_digest_mismatch")
    return binding


def _binding_from_dict(value: Any) -> Optional[CanonicalEnforcementBinding]:
    if not isinstance(value, Mapping):
        return None
    return CanonicalEnforcementBinding(
        protocol_id=str(value.get("protocol_id") or ""),
        protocol_version=int(value.get("protocol_version") or 0),
        phase=value.get("phase") or "",
        executable_plan_digest=str(value.get("executable_plan_digest") or ""),
        decision_status=value.get("decision_status") or "",
        decision_reference=str(value.get("decision_reference") or ""),
    )


def _assurance_from_dict(value: Any) -> Optional[CanonicalAssuranceReference]:
    if not isinstance(value, Mapping):
        return None
    return CanonicalAssuranceReference(
        protocol_id=str(value.get("protocol_id") or ""),
        protocol_version=int(value.get("protocol_version") or 0),
        executable_plan_digest=str(value.get("executable_plan_digest") or ""),
        decision_status=str(value.get("decision_status") or ""),
        decision_reference=str(value.get("decision_reference") or ""),
    )


def _validate_plan_pair(
    logical_plan: CanonicalLogicalPlan,
    executable_plan: CanonicalExecutionPlan,
) -> Dict[str, str]:
    if type(logical_plan) is not CanonicalLogicalPlan or type(executable_plan) is not CanonicalExecutionPlan:
        raise CanonicalReceiptBindingError("canonical_logical_and_executable_plans_required")
    try:
        validate_logical_plan(logical_plan)
        validate_execution_plan(executable_plan)
    except (CanonicalPlanValidationError, TypeError, ValueError) as exc:
        raise CanonicalReceiptBindingError(f"canonical_plan_invalid:{exc}") from exc
    logical_digest = logical_plan_digest(logical_plan)
    executable_digest = execution_plan_digest(executable_plan)
    if executable_plan.source_logical_plan_digest != logical_digest:
        raise CanonicalReceiptBindingError("logical_executable_digest_mismatch")
    identity_pairs = (
        ("planner_id", logical_plan.planner_id, executable_plan.planner_id),
        ("domain_id", logical_plan.domain_id, executable_plan.domain_id),
        ("domain_pack_fingerprint", logical_plan.domain_pack_fingerprint, executable_plan.domain_pack_fingerprint),
        ("domain_pack_version", logical_plan.domain_pack_version, executable_plan.domain_pack_version),
    )
    for name, logical_value, executable_value in identity_pairs:
        if logical_value != executable_value:
            raise CanonicalReceiptBindingError(f"{name}_mismatch")
    if logical_plan.plan_type != executable_plan.plan_type:
        raise CanonicalReceiptBindingError("plan_type_mismatch")
    if logical_plan.composition_policy != executable_plan.composition_policy:
        raise CanonicalReceiptBindingError("composition_policy_mismatch")
    if logical_plan.plan_type == CanonicalPlanType.COMPOSITE:
        if len(logical_plan.composition_units) != len(executable_plan.composition_units):
            raise CanonicalReceiptBindingError("composite_child_count_mismatch")
        for logical_unit, executable_unit in zip(logical_plan.composition_units, executable_plan.composition_units):
            if logical_unit.unit_id != executable_unit.unit_id:
                raise CanonicalReceiptBindingError("composite_child_unit_id_mismatch")
            if tuple(logical_unit.dependencies) != tuple(executable_unit.dependencies):
                raise CanonicalReceiptBindingError("composite_child_dependencies_mismatch")
            if bool(logical_unit.required) != bool(executable_unit.required):
                raise CanonicalReceiptBindingError("composite_child_required_mismatch")
            child_identity = _validate_plan_pair(logical_unit.logical_plan, executable_unit.execution_plan)
            if executable_unit.logical_plan_digest != child_identity["logical_digest"]:
                raise CanonicalReceiptBindingError("composite_child_logical_digest_mismatch")
    elif logical_plan.composition_units or executable_plan.composition_units:
        raise CanonicalReceiptBindingError("non_composite_child_lineage_present")
    return {
        "planner_id": logical_plan.planner_id,
        "domain_id": logical_plan.domain_id,
        "domain_pack_fingerprint": logical_plan.domain_pack_fingerprint,
        "domain_pack_version": logical_plan.domain_pack_version,
        "logical_digest": logical_digest,
        "executable_digest": executable_digest,
    }


__all__ = [
    "CANONICAL_EXECUTION_RECEIPT_PROTOCOL_ID",
    "CANONICAL_EXECUTION_RECEIPT_PROTOCOL_VERSION",
    "CanonicalAssuranceBinding",
    "CanonicalAssuranceReference",
    "CanonicalEnforcementBinding",
    "CanonicalExecutionChildOutcome",
    "CanonicalExecutionOutcome",
    "CanonicalExecutionOutcomeStatus",
    "CanonicalExecutionReceipt",
    "CanonicalReceiptBindingError",
    "CanonicalReceiptStatus",
]
