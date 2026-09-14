"""Read-only downstream view of canonical execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from .canonical_execution_receipt import CanonicalExecutionReceipt


@dataclass(frozen=True)
class CanonicalLineageReadModel:
    receipt_digest: str
    planner_id: str
    domain_id: str
    logical_plan_digest: str
    executable_plan_digest: str
    execution_status: str
    execution_instance_reference: str
    result_reference: str
    evidence_reference: str
    assurance_reference: str = ""
    pre_enforcement_reference: str = ""
    post_enforcement_reference: str = ""

    @classmethod
    def from_receipt(cls, receipt: CanonicalExecutionReceipt) -> "CanonicalLineageReadModel":
        if type(receipt) is not CanonicalExecutionReceipt:
            raise TypeError("canonical_execution_receipt_required")
        return cls(
            receipt_digest=receipt.receipt_digest,
            planner_id=receipt.planner_id,
            domain_id=receipt.domain_id,
            logical_plan_digest=receipt.canonical_logical_plan_digest,
            executable_plan_digest=receipt.canonical_executable_plan_digest,
            execution_status=receipt.execution_status.value,
            execution_instance_reference=receipt.execution_instance_reference,
            result_reference=receipt.result_reference,
            evidence_reference=receipt.evidence_reference,
            assurance_reference=getattr(receipt.assurance, "decision_reference", "") if receipt.assurance else "",
            pre_enforcement_reference=getattr(receipt.pre_enforcement, "decision_reference", "") if receipt.pre_enforcement else "",
            post_enforcement_reference=getattr(receipt.post_enforcement, "decision_reference", "") if receipt.post_enforcement else "",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_digest": self.receipt_digest,
            "planner_id": self.planner_id,
            "domain_id": self.domain_id,
            "logical_plan_digest": self.logical_plan_digest,
            "executable_plan_digest": self.executable_plan_digest,
            "execution_status": self.execution_status,
            "execution_instance_reference": self.execution_instance_reference,
            "result_reference": self.result_reference,
            "evidence_reference": self.evidence_reference,
            "assurance_reference": self.assurance_reference,
            "pre_enforcement_reference": self.pre_enforcement_reference,
            "post_enforcement_reference": self.post_enforcement_reference,
        }


def lineage_metadata(receipt: CanonicalExecutionReceipt) -> Dict[str, Any]:
    """Return the sole canonical execution-lineage metadata payload."""

    model = CanonicalLineageReadModel.from_receipt(receipt)
    payload = model.to_dict()
    payload["receipt"] = receipt.to_dict()
    return payload


__all__ = ["CanonicalLineageReadModel", "lineage_metadata"]
