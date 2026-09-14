"""Neutral R4E canonical semantic contract and evidence helpers.

This module is deliberately independent of application-specific compatibility
runtimes. It describes the canonical semantic contract and provides an
implementation-neutral normalizer for semantic conformance evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


CANONICAL_SEMANTIC_CONTRACT_ID = "ia-rag.semantic-conformance.v1"
CANONICAL_SEMANTIC_CONTRACT_VERSION = 1


class LogicalPlanType(str, Enum):
    TRAVERSE = "TRAVERSE"
    EXISTS = "EXISTS"
    BOOLEAN_CHECK = "BOOLEAN_CHECK"
    AGGREGATE = "AGGREGATE"


class WorldModel(str, Enum):
    OPEN_WORLD = "OPEN_WORLD"
    CLOSED_WORLD = "CLOSED_WORLD"


@dataclass(frozen=True)
class CanonicalAnchor:
    node_type: str
    node_id: Optional[str] = None


@dataclass(frozen=True)
class CanonicalStep:
    relation: str
    direction: str
    source_type: str = "ENTITY"
    target_type: str = "ENTITY"


@dataclass(frozen=True)
class CanonicalBounds:
    max_hops: int
    max_results: int
    cardinality_cap_per_hop: int


@dataclass(frozen=True)
class CanonicalProjection:
    kind: str
    fields: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalAggregation:
    operation: str
    top_n: Optional[int] = None
    date_keys: Tuple[str, ...] = ()
    group_by_node_type: Optional[str] = None
    group_by_relation_type: Optional[str] = None


@dataclass(frozen=True)
class NormativeSemanticConstraint:
    """A correctness-affecting constraint that must survive lowering."""

    kind: str
    value: Any


@dataclass(frozen=True)
class SemanticAnnotation:
    """Observational metadata with no enforcement authority."""

    key: str
    value: Any


@dataclass(frozen=True)
class CanonicalCompositionUnit:
    unit_id: str
    depends_on: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalSemanticPlan:
    """Target field-level logical-plan contract for R4E-C."""

    plan_type: LogicalPlanType
    anchor: CanonicalAnchor
    steps: Tuple[CanonicalStep, ...]
    projection: CanonicalProjection
    bounds: CanonicalBounds
    world_model: WorldModel
    normative_constraints: Tuple[NormativeSemanticConstraint, ...] = ()
    annotations: Tuple[SemanticAnnotation, ...] = ()
    capability_use: Tuple[str, ...] = ()
    semantic_program_id: Optional[str] = None
    semantic_program_source: Optional[str] = None
    aggregation: Optional[CanonicalAggregation] = None
    composition: Tuple[CanonicalCompositionUnit, ...] = ()


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _canonical_value(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_canonical_value(item) for item in value), key=lambda item: repr(item))
    return value


def canonical_json(value: Any) -> str:
    """Return deterministic JSON for semantic evidence and digest inputs."""

    return json.dumps(
        _canonical_value(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def semantic_fingerprint(value: Any) -> str:
    """Hash canonical semantic fields; never use this as the sole test oracle."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _attach_fingerprint(normalized: Dict[str, Any]) -> Dict[str, Any]:
    """Attach a digest that excludes evidence-only telemetry."""

    digest_input = {
        key: value
        for key, value in normalized.items()
        if key not in {"fingerprint", "telemetry"}
    }
    normalized["fingerprint"] = semantic_fingerprint(digest_input)
    return normalized


def execution_fields(plan: CanonicalSemanticPlan) -> Dict[str, Any]:
    """Return only fields that can affect canonical execution semantics.

    Annotations and provenance identify why a plan was produced, but cannot
    authorize a different plan or change execution.  They therefore remain
    visible in the full contract while being excluded from this identity.
    """

    return {
        "plan_type": plan.plan_type,
        "anchor": plan.anchor,
        "steps": plan.steps,
        "projection": plan.projection,
        "bounds": plan.bounds,
        "world_model": plan.world_model,
        "normative_constraints": plan.normative_constraints,
        "capability_use": plan.capability_use,
        "semantic_program_id": plan.semantic_program_id,
        "semantic_program_source": plan.semantic_program_source,
        "aggregation": plan.aggregation,
        "composition": plan.composition,
    }


def execution_fingerprint(plan: CanonicalSemanticPlan) -> str:
    """Digest the typed execution contract, excluding annotations."""

    return semantic_fingerprint(execution_fields(plan))


def _enum_value(value: Any, default: str = "") -> str:
    raw = getattr(value, "value", value)
    return str(raw or default).strip().upper()


def _plan_fingerprint(plan: Any) -> Dict[str, Any]:
    if plan is None:
        return {"status": "MISSING_PLAN"}

    anchors = list(getattr(plan, "anchors", None) or [])
    anchor = anchors[0] if anchors else None
    bounds = getattr(plan, "bounds", None)
    projection = getattr(plan, "projection", None)
    aggregation = getattr(plan, "aggregation", None)
    features = dict(getattr(plan, "features", None) or {})

    steps = []
    for step in list(getattr(plan, "steps", None) or []):
        steps.append(
            {
                "relation": _enum_value(getattr(step, "relation_type", "")),
                "direction": _enum_value(getattr(step, "direction", "")),
                "source_type": _enum_value(getattr(step, "expected_source_type", "ENTITY"), "ENTITY"),
                "target_type": _enum_value(getattr(step, "expected_target_type", "ENTITY"), "ENTITY"),
            }
        )

    aggregate = None
    if aggregation is not None:
        aggregate = {
            "operation": _enum_value(getattr(aggregation, "op", "")),
            "top_n": getattr(aggregation, "top_n", None),
            "date_keys": list(getattr(aggregation, "date_keys", None) or []),
            "group_by_node_type": _enum_value(getattr(aggregation, "group_by_node_type", "")),
            "group_by_relation_type": _enum_value(getattr(aggregation, "group_by_relation_type", "")),
        }

    return {
        "plan_type": _enum_value(getattr(plan, "plan_type", "TRAVERSE"), "TRAVERSE"),
        "anchor": {
            "node_id": str(getattr(anchor, "node_id", "") or ""),
            "node_type": _enum_value(getattr(anchor, "node_type", "ENTITY"), "ENTITY"),
        },
        "steps": steps,
        "projection": {
            "kind": _enum_value(getattr(projection, "kind", "")),
            "fields": list(getattr(projection, "fields", None) or []),
        },
        "bounds": {
            "max_hops": getattr(bounds, "max_hops", None),
            "max_results": getattr(bounds, "max_results", None),
            "cardinality_cap_per_hop": getattr(bounds, "cardinality_cap_per_hop", None),
        },
        "aggregation": aggregate,
        "world_model": features.get("closed_world", features.get("world_model")),
        "normative_constraints": features.get("normative_constraints", features.get("semantic_requirements", [])),
        "capability_use": features.get("capability_use", []),
        "semantic_interpretation": features.get("semantic_interpretation"),
        "semantic_resolution": features.get("semantic_resolution"),
        "semantic_program_id": features.get("semantic_program_id"),
        "semantic_program_source": features.get("semantic_program_source"),
        "annotations": features.get("semantic_annotations", features.get("annotations", [])),
        "relevant_metadata": {
            key: features[key]
            for key in sorted(features)
            if key in {
                "plan_type",
                "semantic_program_id",
                "semantic_program_source",
                "semantic_program_legacy_compatibility",
                "closed_world",
                "world_model",
                "normative_constraints",
                "semantic_requirements",
                "capability_use",
                "semantic_annotations",
                "annotations",
                "multi_intent",
            }
        },
    }


def normalize_compile_result(result: Any) -> Dict[str, Any]:
    """Normalize a current compiler result for differential evidence.

    The returned mapping is observational.  It does not confer authority on
    either current compiler and deliberately keeps field-level values visible
    beside the derived fingerprint.
    """

    if result is None:
        normalized = {"status": "FAILURE", "reason": "missing_result", "units": []}
    elif not bool(getattr(result, "ok", False)):
        telemetry = dict(getattr(result, "telemetry", None) or {})
        normalized = {
            "status": "REJECTED",
            "reason": str(
                telemetry.get("reason")
                or telemetry.get("rejection_reason")
                or telemetry.get("error")
                or "compiler_rejected"
            ),
            "units": [],
        }
    else:
        raw_plans = list(getattr(result, "plans", None) or [])
        if not raw_plans and getattr(result, "plan", None) is not None:
            raw_plans = [getattr(result, "plan")]
        normalized = {
            "status": "ACCEPTED",
            "shape": "PLAN_SET" if len(raw_plans) > 1 else "SINGLE",
            "units": [_plan_fingerprint(plan) for plan in raw_plans],
            "telemetry": dict(getattr(result, "telemetry", None) or {}),
        }

    return _attach_fingerprint(normalized)


def normalize_compile_failure(error: BaseException) -> Dict[str, Any]:
    """Normalize an exception without making exception text a semantic oracle."""

    normalized = {
        "status": "FAILURE",
        "reason": type(error).__name__,
        "units": [],
    }
    return _attach_fingerprint(normalized)


def normalize_many(results: Iterable[Any]) -> Tuple[Dict[str, Any], ...]:
    return tuple(normalize_compile_result(result) for result in results)
