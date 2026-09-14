"""Deterministic assurance provider for the hermetic reference runtime.

This provider exists for tests and examples.  It implements the neutral v1
assurance protocol without identity, transport, enterprise, or external
service concepts.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any, Dict, Mapping, Optional

from .assurance_protocols import (
    ASSURANCE_PROTOCOL_ID,
    ASSURANCE_PROTOCOL_VERSION,
    AssuranceError,
    AssuranceMode,
)
from .canonical_plan import execution_plan_digest
from .canonical_semantic_contract import semantic_fingerprint


@dataclass(frozen=True)
class ReferenceAssuranceDecision:
    """Stable allow/deny decision returned by the reference provider."""

    ok: bool
    code: str
    decision_reference: str
    metadata: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "code": self.code,
            "decision_reference": self.decision_reference,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class ReferenceAssuranceRecord:
    """Reference record paired with a decision."""

    record_id: str
    plan_digest: str


class ReferenceAssuranceProvider:
    """A deterministic, explicitly injected v1 assurance implementation."""

    protocol_id = ASSURANCE_PROTOCOL_ID
    protocol_version = ASSURANCE_PROTOCOL_VERSION
    capabilities = {
        "ingress_context": True,
        "exact_plan_execution_evaluation": True,
        "execution_binding": True,
        "mutation_boundary": True,
        "response_integrity": True,
        "generic_receipts": True,
    }

    def __init__(self, *, allow: bool = True, decision_code: str = "reference_allow") -> None:
        self.allow = bool(allow)
        self.decision_code = str(decision_code or "reference_allow").strip()
        self.default_audience = "ia-rag.reference-runtime"
        self._bound_plan: Any = None

    def with_configuration(self, **kwargs: Any) -> "ReferenceAssuranceProvider":
        del kwargs
        return replace(self) if hasattr(self, "__dataclass_fields__") else self.__class__(
            allow=self.allow,
            decision_code=self.decision_code,
        )

    @staticmethod
    def normalize_mode(value: Any) -> AssuranceMode:
        if isinstance(value, AssuranceMode):
            return value
        raw = str(value or AssuranceMode.ENFORCE.value).strip().lower()
        aliases = {"observe": AssuranceMode.OBSERVE, "shadow": AssuranceMode.SHADOW, "off": AssuranceMode.OFF, "enforce": AssuranceMode.ENFORCE}
        try:
            return aliases[raw]
        except KeyError as exc:
            raise ValueError(f"reference_assurance_mode_invalid:{raw}") from exc

    @staticmethod
    def is_enforce(value: Any) -> bool:
        return ReferenceAssuranceProvider.normalize_mode(value) == AssuranceMode.ENFORCE

    @staticmethod
    def coerce_context(value: Any) -> Any:
        return dict(value) if isinstance(value, Mapping) else value

    @staticmethod
    def build_ingress_context(**kwargs: Any) -> Dict[str, Any]:
        return {
            "origin": str(kwargs.get("origin") or kwargs.get("origin_principal") or "anonymous"),
            "query": str(kwargs.get("query") or kwargs.get("query_text") or ""),
            "entrypoint": str(kwargs.get("entrypoint") or "reference"),
        }

    def normalize_ingress(self, *, kind: str, **kwargs: Any) -> Any:
        del kind
        decision, record = self.evaluate(
            kwargs.get("plan") or {"ingress": kwargs.get("assertion")},
            mode=kwargs.get("mode", AssuranceMode.ENFORCE),
            runtime_audience=str(kwargs.get("runtime_audience") or self.default_audience),
        )
        return type(
            "ReferenceIngress",
            (),
            {"decision": decision, "record": record, "context": kwargs.get("assertion")},
        )()

    @staticmethod
    def merge_metadata(records: Any) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for record in records or ():
            if isinstance(record, Mapping):
                merged.update(dict(record))
        return merged

    def derive_requirements(self, plan: Any, *, runtime_audience: str) -> Dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "plan_digest": execution_plan_digest(plan) if hasattr(plan, "plan_type") else semantic_fingerprint(plan),
            "audience": str(runtime_audience or self.default_audience),
        }

    @staticmethod
    def coerce_requirements(value: Any) -> Dict[str, Any]:
        return dict(value or {}) if isinstance(value, Mapping) else {}

    @staticmethod
    def finalize_context(context: Any, *, requirements: Any, step_ordinal: int) -> Any:
        result = dict(context or {}) if isinstance(context, Mapping) else {"value": context}
        result["requirements"] = dict(requirements or {})
        result["step"] = int(step_ordinal)
        return result

    def evaluate(self, plan: Any, *, mode: Any, runtime_audience: str) -> Any:
        normalized_mode = self.normalize_mode(mode)
        digest = execution_plan_digest(plan) if hasattr(plan, "plan_type") else semantic_fingerprint(plan)
        allowed = self.allow or normalized_mode == AssuranceMode.OFF
        code = self.decision_code if allowed else "reference_denied"
        metadata = {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "mode": normalized_mode.value,
            "audience": str(runtime_audience or self.default_audience),
            "plan_digest": digest,
            "decision": "ALLOW" if allowed else "DENY",
        }
        reference = semantic_fingerprint(metadata)
        decision = ReferenceAssuranceDecision(allowed, code, reference, metadata)
        return decision, ReferenceAssuranceRecord(reference, digest)

    @staticmethod
    def metadata(decision: Any, receipt: Any, requirements: Any, *, mode: Any) -> Dict[str, Any]:
        return {
            "protocol_id": ASSURANCE_PROTOCOL_ID,
            "protocol_version": ASSURANCE_PROTOCOL_VERSION,
            "decision": "ALLOW" if bool(getattr(decision, "ok", False)) else "DENY",
            "decision_code": str(getattr(decision, "code", "") or ""),
            "decision_reference": str(getattr(decision, "decision_reference", "") or getattr(receipt, "record_id", "")),
            "mode": ReferenceAssuranceProvider.normalize_mode(mode).value,
            "requirements": dict(requirements or {}),
        }

    @contextmanager
    def bind(self, plan: Any):
        expected = execution_plan_digest(plan)
        previous = self._bound_plan
        self._bound_plan = plan
        try:
            yield plan
        finally:
            if self._bound_plan is not plan or execution_plan_digest(self._bound_plan) != expected:
                raise AssuranceError("reference_execution_binding_changed")
            self._bound_plan = previous

    def current_plan(self) -> Any:
        return self._bound_plan

    def build_mutation_plan(self, **kwargs: Any) -> Dict[str, Any]:
        return {"protocol_id": self.protocol_id, "operation": "mutation", **dict(kwargs)}

    def initialize_mutation_boundary(self, target: Any, *, mode: Any, audience: str) -> None:
        del target, mode, audience

    def evaluate_mutation_boundary(self, **kwargs: Any) -> ReferenceAssuranceDecision:
        plan = kwargs.get("plan") or kwargs
        return self.evaluate(plan, mode=kwargs.get("mode", AssuranceMode.ENFORCE), runtime_audience=str(kwargs.get("audience") or self.default_audience))[0]

    def record_mutation(self, target: Any, metadata: Mapping[str, Any]) -> Dict[str, Any]:
        return {"protocol_id": self.protocol_id, "target": type(target).__name__, "metadata": dict(metadata or {})}

    @staticmethod
    def attach_integrity(response: Any, *, previous_record: Any = None) -> Any:
        if not isinstance(response, Mapping):
            return response
        result = dict(response)
        base = dict(result)
        base.pop("response_integrity", None)
        result["response_integrity"] = {
            "protocol_id": ASSURANCE_PROTOCOL_ID,
            "digest": semantic_fingerprint(base),
            "previous": str(previous_record or ""),
        }
        return result

    def propagate(self, **kwargs: Any) -> Dict[str, Any]:
        return dict(kwargs)

    def export(self, **kwargs: Any) -> Dict[str, Any]:
        return dict(kwargs)

    @staticmethod
    def prepare_downstream_context(context: Any) -> Any:
        return dict(context or {}) if isinstance(context, Mapping) else context

    def make_requirements(self, **kwargs: Any) -> Dict[str, Any]:
        return dict(kwargs)

    def enforcement_error(self, outcome: Any, *, mode: Any) -> BaseException:
        del mode
        return AssuranceError(
            str(getattr(outcome, "code", None) or "reference_assurance_denied"),
            assurance_metadata=self.metadata(outcome, None, {}, mode=AssuranceMode.ENFORCE),
        )

    @staticmethod
    def is_denial(error: BaseException) -> bool:
        return isinstance(error, AssuranceError) or str(getattr(error, "code", "")).endswith("denied")

    @staticmethod
    def error_code(error: BaseException) -> str:
        return str(getattr(error, "code", None) or "reference_assurance_error")

    @staticmethod
    def error_metadata(error: BaseException) -> Dict[str, Any]:
        return dict(getattr(error, "assurance_metadata", None) or {})


__all__ = [
    "ReferenceAssuranceDecision",
    "ReferenceAssuranceProvider",
    "ReferenceAssuranceRecord",
]
