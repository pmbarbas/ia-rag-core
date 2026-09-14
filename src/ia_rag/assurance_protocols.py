"""Versioned, implementation-neutral assurance contracts for IA-RAG.

The runtime depends only on :data:`ASSURANCE_PROTOCOL_ID` and the opaque
``AssuranceProvider`` protocol.  An application composes a concrete provider
and injects it into the runtime graph.  This module deliberately
contains no provider registry, singleton, import-time initialization, or
enterprise assurance type.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Protocol, runtime_checkable


DEFAULT_ASSURANCE_AUDIENCE = "ia_rag.execution_engine"
ASSURANCE_PROTOCOL_ID = "ia-rag.assurance.v1"
ASSURANCE_PROTOCOL_VERSION = 1
REQUIRED_ASSURANCE_CAPABILITIES = (
    "ingress_context",
    "exact_plan_execution_evaluation",
    "execution_binding",
    "mutation_boundary",
    "response_integrity",
    "generic_receipts",
)
READ_ACTION_CLASS = "read"
READ_PROOF_MODE = "basic"
WRITE_ACTION_CLASS = "write"


class AssuranceMode(str, Enum):
    OFF = "off"
    OBSERVE = "observe"
    SHADOW = "shadow"
    ENFORCE = "enforce"


class AssuranceConfigurationError(RuntimeError):
    """Raised when a runtime boundary has no configured assurance provider."""


class AssuranceError(RuntimeError):
    """Neutral denial error for protocol implementations and test doubles."""

    def __init__(self, code: str, *, assurance_metadata: Optional[Mapping[str, Any]] = None):
        self.code = str(code or "assurance_error")
        self.assurance_metadata = dict(assurance_metadata or {})
        super().__init__(self.code)

@runtime_checkable
class AssuranceProvider(Protocol):
    """Opaque v1 ingress, execution-guard, mutation, and integrity seam.

    Implementations must expose the stable protocol identifier and capability
    set, and must treat plans supplied to ``evaluate``/``bind`` as opaque
    already-authoritative executable plans.  The provider may decide or deny;
    it may not compile, reinterpret, replace, or regenerate a plan.
    """

    protocol_id: str
    protocol_version: int
    capabilities: Mapping[str, bool]

    def with_configuration(self, **kwargs: Any) -> "AssuranceProvider": ...

    def normalize_mode(self, value: Any) -> Any: ...

    def is_enforce(self, value: Any) -> bool: ...

    def coerce_context(self, value: Any) -> Any: ...

    def build_ingress_context(self, **kwargs: Any) -> Any: ...

    def normalize_ingress(self, *, kind: str, **kwargs: Any) -> Any: ...

    def merge_metadata(self, records: Any) -> Dict[str, Any]: ...

    def derive_requirements(self, plan: Any, *, runtime_audience: str) -> Any: ...

    def coerce_requirements(self, value: Any) -> Any: ...

    def finalize_context(self, context: Any, *, requirements: Any, step_ordinal: int) -> Any: ...

    def evaluate(self, plan: Any, *, mode: Any, runtime_audience: str) -> Any: ...

    def metadata(self, decision: Any, receipt: Any, requirements: Any, *, mode: Any) -> Dict[str, Any]: ...

    def bind(self, plan: Any) -> AbstractContextManager[Any]: ...

    def current_plan(self) -> Any: ...

    def build_mutation_plan(self, **kwargs: Any) -> Any: ...

    def initialize_mutation_boundary(self, target: Any, *, mode: Any, audience: str) -> None: ...

    def evaluate_mutation_boundary(self, **kwargs: Any) -> Any: ...

    def record_mutation(self, target: Any, metadata: Mapping[str, Any]) -> Dict[str, Any]: ...

    def attach_integrity(self, response: Any, *, previous_record: Any = None) -> Any: ...

    def propagate(self, **kwargs: Any) -> Any: ...

    def export(self, **kwargs: Any) -> Any: ...

    def prepare_downstream_context(self, context: Any) -> Any: ...

    def make_requirements(self, **kwargs: Any) -> Any: ...

    def enforcement_error(self, outcome: Any, *, mode: Any) -> BaseException: ...

    def is_denial(self, error: BaseException) -> bool: ...

    def error_code(self, error: BaseException) -> str: ...

    def error_metadata(self, error: BaseException) -> Dict[str, Any]: ...


def resolve_assurance_provider(provider: Optional[AssuranceProvider] = None) -> AssuranceProvider:
    """Return the explicitly supplied provider, failing closed otherwise.

    There is intentionally no package-level default.  Composition roots must
    construct the concrete provider and pass the same instance (or its
    explicitly configured derivative) through the runtime graph.
    """
    if provider is None:
        raise AssuranceConfigurationError(
            "assurance_provider_unconfigured: inject an assurance provider at the private composition root"
        )
    if getattr(provider, "protocol_id", None) != ASSURANCE_PROTOCOL_ID:
        raise AssuranceConfigurationError(
            "assurance_provider_protocol_mismatch: expected ia-rag.assurance.v1"
        )
    if getattr(provider, "protocol_version", None) != ASSURANCE_PROTOCOL_VERSION:
        raise AssuranceConfigurationError(
            "assurance_provider_protocol_version_mismatch: expected version 1"
        )
    capabilities = getattr(provider, "capabilities", None)
    if not isinstance(capabilities, Mapping):
        raise AssuranceConfigurationError(
            "assurance_provider_capabilities_missing: provider must declare v1 capabilities"
        )
    missing = [
        name for name in REQUIRED_ASSURANCE_CAPABILITIES
        if capabilities.get(name) is not True
    ]
    if missing:
        raise AssuranceConfigurationError(
            "assurance_provider_capabilities_missing: " + ", ".join(missing)
        )
    return provider


def is_assurance_denial(provider: AssuranceProvider, error: BaseException) -> bool:
    """Ask the concrete provider whether an exception represents a denial."""
    try:
        return bool(provider.is_denial(error))
    except AssuranceConfigurationError:
        raise
    except Exception:
        return isinstance(error, AssuranceError)


def assurance_error_code(provider: AssuranceProvider, error: BaseException) -> str:
    try:
        return str(provider.error_code(error) or "assurance_error")
    except Exception:
        return str(getattr(error, "code", None) or "assurance_error")


def assurance_error_metadata(provider: AssuranceProvider, error: BaseException) -> Dict[str, Any]:
    try:
        return dict(provider.error_metadata(error) or {})
    except Exception:
        payload = getattr(error, "assurance_metadata", None)
        if payload is None:
            payload = getattr(error, "assurance_metadata", None)
        return dict(payload or {})
