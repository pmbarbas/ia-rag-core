"""Neutral explicit seam for semantic extensions.

Extensions are optional compiler inputs.  They may contribute bounded,
inspectable semantic metadata, but they are deliberately unable to select a
planner, compile or replace a plan, execute a plan, render, or bypass
governance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence

DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_ID = "ia-rag.domain-semantics.v1"
DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_VERSION = 1


class SemanticExtensionConfigurationError(ValueError):
    """Raised when an explicitly required extension is unavailable or invalid."""


class DomainSemanticExtension(Protocol):
    """Implementation-neutral extension contract.

    ``resolve`` may return bounded semantic data and plan fragments.  The
    compiler records that data in the selected plan's feature lineage; it does
    not permit the extension to return or replace a plan.
    """

    extension_id: str
    protocol_id: str
    protocol_version: int

    def resolve(
        self,
        query: str,
        *,
        domain_pack: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Optional[Mapping[str, Any]]:
        ...


@dataclass(frozen=True)
class SemanticExtensionResult:
    extension_id: str
    protocol_id: str
    protocol_version: int
    payload: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "extension_id": self.extension_id,
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "payload": dict(self.payload or {}),
        }


class DomainSemanticExtensionRegistry:
    """Explicit in-memory registry; it performs no scanning or discovery."""

    def __init__(self, extensions: Optional[Sequence[DomainSemanticExtension]] = None):
        self._extensions: Dict[str, DomainSemanticExtension] = {}
        for extension in list(extensions or ()):
            self.register(extension)

    def register(self, extension: DomainSemanticExtension) -> None:
        extension_id = str(getattr(extension, "extension_id", "") or "").strip()
        protocol_id = str(getattr(extension, "protocol_id", "") or "").strip()
        try:
            protocol_version = int(getattr(extension, "protocol_version"))
        except Exception as exc:
            raise SemanticExtensionConfigurationError("semantic_extension_missing_protocol_version") from exc
        if not extension_id:
            raise SemanticExtensionConfigurationError("semantic_extension_missing_id")
        if protocol_id != DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_ID or protocol_version != DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_VERSION:
            raise SemanticExtensionConfigurationError(
                f"semantic_extension_incompatible_protocol:{extension_id}"
            )
        if extension_id in self._extensions:
            raise SemanticExtensionConfigurationError(
                f"semantic_extension_duplicate_id:{extension_id}"
            )
        resolver = getattr(extension, "resolve", None)
        if not callable(resolver):
            raise SemanticExtensionConfigurationError(
                f"semantic_extension_missing_resolve:{extension_id}"
            )
        self._extensions[extension_id] = extension

    def resolve(self, extension_id: str) -> Optional[DomainSemanticExtension]:
        return self._extensions.get(str(extension_id or "").strip())

    def identifiers(self) -> tuple[str, ...]:
        return tuple(sorted(self._extensions))


def _declaration(domain_config: Any) -> Optional[Mapping[str, Any]]:
    raw = dict(getattr(domain_config, "raw", {}) or {}) if hasattr(domain_config, "raw") else dict(domain_config or {})
    query = raw.get("query") if isinstance(raw.get("query"), Mapping) else {}
    value = query.get("semantic_extension")
    if value is None:
        value = raw.get("semantic_extension")
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return {"extension_id": value.strip(), "required": True}
    if isinstance(value, Mapping):
        return value
    raise SemanticExtensionConfigurationError("semantic_extension_declaration_must_be_mapping_or_id")


def resolve_semantic_extension(
    *,
    registry: Optional[DomainSemanticExtensionRegistry],
    domain_config: Any,
    query: str,
    context: Optional[Mapping[str, Any]] = None,
) -> Optional[SemanticExtensionResult]:
    declaration = _declaration(domain_config)
    if declaration is None:
        return None
    extension_id = str(declaration.get("extension_id") or declaration.get("id") or "").strip()
    required = bool(declaration.get("required", True))
    if not extension_id:
        raise SemanticExtensionConfigurationError("semantic_extension_declaration_missing_id")
    extension = registry.resolve(extension_id) if registry is not None else None
    if extension is None:
        if required:
            raise SemanticExtensionConfigurationError(
                f"semantic_extension_not_registered:{extension_id}"
            )
        return None
    raw = dict(getattr(domain_config, "raw", {}) or {}) if hasattr(domain_config, "raw") else dict(domain_config or {})
    payload = extension.resolve(
        str(query or ""),
        domain_pack=raw,
        context=dict(context or {}),
    )
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise SemanticExtensionConfigurationError(
            f"semantic_extension_invalid_result:{extension_id}"
        )
    prohibited = {
        "planner",
        "planner_id",
        "selected_planner",
        "logical_plan",
        "logical_plan_id",
        "executable_plan",
        "executable_plan_id",
        "execution",
        "execution_engine",
        "execution_receipt",
        "receipt",
        "renderer",
        "render_model",
        "governance",
    }
    conflicting = sorted(str(key) for key in payload if str(key) in prohibited)
    if conflicting:
        raise SemanticExtensionConfigurationError(
            f"semantic_extension_authority_field_forbidden:{extension_id}:{','.join(conflicting)}"
        )
    try:
        json.dumps(dict(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise SemanticExtensionConfigurationError(
            f"semantic_extension_result_must_be_json_compatible:{extension_id}"
        ) from exc
    return SemanticExtensionResult(
        extension_id=extension_id,
        protocol_id=DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_ID,
        protocol_version=DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_VERSION,
        payload=dict(payload),
    )


def attach_semantic_extension(plan: Any, result: SemanticExtensionResult) -> Any:
    """Attach extension output to the existing plan without replacing it."""
    features = dict(getattr(plan, "features", None) or {})
    features["domain_semantic_extension"] = result.to_dict()
    # Keep the plan object and all authority fields intact.  The canonical
    # plan is immutable; the fallback supports legacy test doubles.
    try:
        return type(plan)(**{**plan.__dict__, "features": features})
    except Exception:
        try:
            plan.features = features
        except Exception as exc:
            raise SemanticExtensionConfigurationError("semantic_extension_plan_attachment_failed") from exc
        return plan


def apply_extension_to_plan(
    plan: Any,
    *,
    result: Optional[SemanticExtensionResult],
) -> Any:
    if plan is None or result is None:
        return plan
    return attach_semantic_extension(plan, result)
