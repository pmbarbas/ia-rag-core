"""R4E-D consolidated canonical compiler (shadow/conformance only).

This module is intentionally independent of alternate compilers.  It consumes
a typed, canonical domain-pack view and emits the
R4E-C :class:`CanonicalLogicalPlan` directly.  It does not execute a plan,
select a runtime planner, or create an execution receipt.

The input boundary is deliberately small:

    question + CanonicalDomainPack + neutral entity resolver
        -> CanonicalCompileResult

The compiler has no runtime side effects.  Comparison implementations, when
used by an application, are injected and are never dependencies of this
compiler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Protocol, Sequence, Tuple

from .canonical_plan import (
    CANONICAL_PLAN_PROTOCOL_VERSION,
    CanonicalCapabilityUse,
    CanonicalCompositionPolicy,
    CanonicalLogicalPlan,
    CanonicalLogicalUnit,
    CanonicalPlanType,
    CanonicalPlanValidationError,
    CanonicalSemanticProgramProvenance,
    CanonicalWorldMode,
    CanonicalWorldSemantics,
    lower_logical_plan,
    logical_plan_digest,
    validate_logical_plan,
)
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


CANONICAL_COMPILER_ID = "ia-rag.canonical-compiler.v1"
CANONICAL_COMPILER_PROTOCOL_ID = "ia-rag.compiler.v1"
CANONICAL_COMPILER_PROTOCOL_VERSION = CANONICAL_PLAN_PROTOCOL_VERSION


class CanonicalCompilerConfigurationError(ValueError):
    """A canonical DomainPack or compiler configuration is malformed."""


class CanonicalSemanticRejection(ValueError):
    """A supported request cannot be represented canonically."""

    def __init__(self, reason_code: str, message: str = "") -> None:
        self.reason_code = str(reason_code).strip() or "semantic_rejection"
        super().__init__(message or self.reason_code)


class CompileDisposition(str, Enum):
    OK = "OK"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class CanonicalDiagnostic:
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class CanonicalCompileResult:
    """Structured compiler output; it never carries a runtime receipt."""

    disposition: CompileDisposition
    reason_code: str
    plan: Optional[CanonicalLogicalPlan] = None
    diagnostics: Tuple[CanonicalDiagnostic, ...] = ()
    semantic_program: Optional[CanonicalSemanticProgramProvenance] = None

    @property
    def ok(self) -> bool:
        return self.disposition == CompileDisposition.OK and self.plan is not None

    @property
    def rejected(self) -> bool:
        return self.disposition == CompileDisposition.REJECTED

    @property
    def failed(self) -> bool:
        return self.disposition == CompileDisposition.FAILED

    @property
    def logical_plan_digest(self) -> Optional[str]:
        return logical_plan_digest(self.plan) if self.plan is not None else None


@dataclass(frozen=True)
class CanonicalEntityCandidate:
    node_id: str
    node_type: str
    display_name: str = ""
    score: float = 0.0


class CanonicalEntityResolver(Protocol):
    """Neutral typed entity-resolution seam used by the canonical compiler."""

    def resolve(self, mention: str, expected_type: Optional[str] = None) -> Sequence[Any]:
        """Return typed candidates; the compiler chooses deterministically."""


@dataclass(frozen=True)
class CanonicalRelation:
    relation_type: str
    source_type: str
    target_type: str
    aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalProgramStep:
    relation_type: str
    direction: str
    expected_source_type: Optional[str] = None
    expected_target_type: Optional[str] = None


@dataclass(frozen=True)
class CanonicalSemanticProgram:
    program_id: str
    patterns: Tuple[str, ...]
    anchor_type: str
    steps: Tuple[CanonicalProgramStep, ...]
    projection: str = "TYPED_FACTS"
    plan_type: Optional[CanonicalPlanType] = None
    priority: int = 0
    normative_constraints: Tuple[NormativeSemanticConstraint, ...] = ()
    annotations: Tuple[SemanticAnnotation, ...] = ()
    aggregation: Optional[CanonicalAggregation] = None
    source: str = "query.semantic_programs"


@dataclass(frozen=True)
class CanonicalDomainPack:
    """Canonical, domain-neutral read model consumed by the compiler.

    ``from_mapping`` only reads canonical keys.  In particular, it does not
    read ``query.programs``, ``query.aggregations.legacy_patterns``, legacy
    date aliases, derived-path aliases, or compiler compatibility flags.
    """

    domain_id: str
    pack_version: str
    pack_fingerprint: str
    relations: Tuple[CanonicalRelation, ...]
    entity_types: Tuple[str, ...]
    capabilities: Tuple[str, ...]
    semantic_programs: Tuple[CanonicalSemanticProgram, ...] = ()
    world: CanonicalWorldSemantics = field(default_factory=CanonicalWorldSemantics)
    max_hops: Optional[int] = None
    max_results: int = 50
    cardinality_cap_per_hop: int = 200
    aggregation_operations: Tuple[str, ...] = ()
    aggregation_date_keys: Tuple[str, ...] = ()
    composition_policy: CanonicalCompositionPolicy = CanonicalCompositionPolicy.FAIL_CLOSED

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "CanonicalDomainPack":
        if not isinstance(raw, Mapping):
            raise CanonicalCompilerConfigurationError("domain_pack_mapping_required")

        domain_id = _text(raw.get("domain_name") or raw.get("name"))
        version = _text(raw.get("pack_version"))
        if not domain_id:
            raise CanonicalCompilerConfigurationError("domain_id_required")
        if not version:
            raise CanonicalCompilerConfigurationError("domain_pack_version_required")

        raw_relations = raw.get("relations")
        if raw_relations is None:
            raw_relations = []
        if not isinstance(raw_relations, list):
            raise CanonicalCompilerConfigurationError("canonical_relations_required")
        relations = []
        for index, item in enumerate(raw_relations):
            if not isinstance(item, Mapping):
                raise CanonicalCompilerConfigurationError(f"relation_must_be_mapping:{index}")
            relation_type = _upper(item.get("type") or item.get("relation_type"))
            source_type = _upper(item.get("source") or item.get("source_type"))
            target_type = _upper(item.get("target") or item.get("target_type"))
            if not relation_type or not source_type or not target_type:
                raise CanonicalCompilerConfigurationError(f"relation_declaration_incomplete:{index}")
            aliases = item.get("aliases") or ()
            if isinstance(aliases, str):
                aliases = (aliases,)
            if not isinstance(aliases, (list, tuple)):
                raise CanonicalCompilerConfigurationError(f"relation_aliases_invalid:{relation_type}")
            relations.append(
                CanonicalRelation(
                    relation_type=relation_type,
                    source_type=source_type,
                    target_type=target_type,
                    aliases=tuple(_text(value).lower() for value in aliases if _text(value)),
                )
            )

        entities = raw.get("entities") or ()
        if isinstance(entities, Mapping):
            entities = list(entities)
        if not isinstance(entities, (list, tuple)):
            raise CanonicalCompilerConfigurationError("entity_types_invalid")
        entity_types = []
        for item in entities:
            if isinstance(item, Mapping):
                value = item.get("type") or item.get("node_type")
            else:
                value = item
            if _text(value):
                entity_types.append(_upper(value))

        capabilities = _as_string_tuple(raw.get("capabilities"), upper=True)
        query = raw.get("query")
        if query is None:
            query = {}
        if not isinstance(query, Mapping):
            raise CanonicalCompilerConfigurationError("query_mapping_required")

        programs = _load_canonical_programs(query.get("semantic_programs"))
        world = _load_world(raw.get("world_model"))
        governance = raw.get("governance")
        if governance is None:
            governance = {}
        if not isinstance(governance, Mapping):
            raise CanonicalCompilerConfigurationError("governance_mapping_required")
        max_hops = _optional_int(governance.get("max_hops"), "governance.max_hops")
        max_results = _positive_int(governance.get("max_results", 50), "governance.max_results")
        cardinality = _positive_int(
            governance.get("cardinality_cap_per_hop", 200),
            "governance.cardinality_cap_per_hop",
        )

        aggregation = query.get("aggregations")
        if aggregation is None:
            aggregation = {}
        if not isinstance(aggregation, Mapping):
            raise CanonicalCompilerConfigurationError("query.aggregations_mapping_required")
        operations = aggregation.get("operations")
        if operations is None:
            operations = aggregation.get("allowed_operations") or ()
        if isinstance(operations, str):
            operations = (operations,)
        if not isinstance(operations, (list, tuple)):
            raise CanonicalCompilerConfigurationError("query.aggregations.operations_invalid")
        date_keys = aggregation.get("date_keys") or ()
        if isinstance(date_keys, str):
            date_keys = (date_keys,)
        if not isinstance(date_keys, (list, tuple)):
            raise CanonicalCompilerConfigurationError("query.aggregations.date_keys_invalid")

        policy_raw = raw.get("composition_policy") or query.get("composition_policy")
        policy = CanonicalCompositionPolicy.FAIL_CLOSED
        if policy_raw:
            try:
                policy = CanonicalCompositionPolicy(_upper(policy_raw))
            except ValueError as exc:
                raise CanonicalCompilerConfigurationError("composition_policy_invalid") from exc

        fingerprint = _text(raw.get("pack_fingerprint")) or semantic_fingerprint(
            {
                "domain_id": domain_id,
                "pack_version": version,
                "relations": relations,
                "entity_types": entity_types,
                "capabilities": capabilities,
                "semantic_programs": programs,
                "world": world,
                "governance": {
                    "max_hops": max_hops,
                    "max_results": max_results,
                    "cardinality_cap_per_hop": cardinality,
                },
                "aggregation_operations": operations,
                "aggregation_date_keys": date_keys,
            }
        )
        return cls(
            domain_id=domain_id,
            pack_version=version,
            pack_fingerprint=fingerprint,
            relations=tuple(sorted(relations, key=lambda item: item.relation_type)),
            entity_types=tuple(sorted(set(entity_types))),
            capabilities=tuple(sorted(set(capabilities))),
            semantic_programs=tuple(sorted(programs, key=lambda item: item.program_id)),
            world=world,
            max_hops=max_hops,
            max_results=max_results,
            cardinality_cap_per_hop=cardinality,
            aggregation_operations=tuple(sorted(set(_upper(value) for value in operations if _text(value)))),
            aggregation_date_keys=tuple(_text(value) for value in date_keys if _text(value)),
            composition_policy=policy,
        )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(getattr(value, "value", value)).upper()


def _as_string_tuple(value: Any, *, upper: bool = False) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, (list, tuple)):
        raise CanonicalCompilerConfigurationError("string_sequence_required")
    values = tuple((_upper(item) if upper else _text(item)) for item in value if _text(item))
    return values


def _optional_int(value: Any, path: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalCompilerConfigurationError(f"{path}_invalid") from exc
    if result < 0:
        raise CanonicalCompilerConfigurationError(f"{path}_invalid")
    return result


def _positive_int(value: Any, path: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalCompilerConfigurationError(f"{path}_invalid") from exc
    if result <= 0:
        raise CanonicalCompilerConfigurationError(f"{path}_invalid")
    return result


def _load_world(value: Any) -> CanonicalWorldSemantics:
    if value is None:
        return CanonicalWorldSemantics()
    if not isinstance(value, Mapping):
        raise CanonicalCompilerConfigurationError("world_model_mapping_required")
    mode = _upper(value.get("mode") or CanonicalWorldMode.OPEN_WORLD.value)
    try:
        world_mode = CanonicalWorldMode(mode)
    except ValueError as exc:
        raise CanonicalCompilerConfigurationError("world_mode_invalid") from exc
    scope = _text(value.get("scope")) or None
    completeness = _text(value.get("completeness")) or None
    # A closed-world declaration explicitly names its scope.  EXHAUSTIVE is
    # the typed meaning of the closed-world mode when the canonical pack does
    # not repeat the word, not an old compiler fallback.
    if world_mode == CanonicalWorldMode.CLOSED_WORLD and completeness is None:
        completeness = "EXHAUSTIVE"
    return CanonicalWorldSemantics(world_mode, scope, completeness)


def _load_constraint(value: Any, *, path: str) -> NormativeSemanticConstraint:
    if not isinstance(value, Mapping) or "kind" not in value or "value" not in value:
        raise CanonicalCompilerConfigurationError(f"{path}_must_be_typed")
    return NormativeSemanticConstraint(str(value["kind"]), value["value"])


def _load_annotation(value: Any, *, path: str) -> SemanticAnnotation:
    if not isinstance(value, Mapping) or "key" not in value or "value" not in value:
        raise CanonicalCompilerConfigurationError(f"{path}_must_be_typed")
    return SemanticAnnotation(str(value["key"]), value["value"])


def _load_canonical_programs(value: Any) -> Tuple[CanonicalSemanticProgram, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CanonicalCompilerConfigurationError("query.semantic_programs_must_be_list")
    programs = []
    seen = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise CanonicalCompilerConfigurationError(f"semantic_program_entry_must_be_mapping:{index}")
        program_id = _text(raw.get("program_id") or raw.get("id") or raw.get("name"))
        if not program_id:
            raise CanonicalCompilerConfigurationError(f"semantic_program_missing_id:{index}")
        if program_id in seen:
            raise CanonicalCompilerConfigurationError(f"semantic_program_duplicate_id:{program_id}")
        seen.add(program_id)
        patterns = raw.get("patterns")
        if isinstance(patterns, str):
            patterns = (patterns,)
        if not isinstance(patterns, (list, tuple)) or not any(_text(item) for item in patterns):
            raise CanonicalCompilerConfigurationError(f"semantic_program_missing_patterns:{program_id}")
        anchor_type = _upper(raw.get("anchor_type"))
        if not anchor_type:
            raise CanonicalCompilerConfigurationError(f"semantic_program_missing_anchor_type:{program_id}")
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list):
            raise CanonicalCompilerConfigurationError(f"semantic_program_missing_steps:{program_id}")
        steps = []
        for step_index, item in enumerate(raw_steps):
            if not isinstance(item, Mapping):
                raise CanonicalCompilerConfigurationError(
                    f"semantic_program_step_must_be_mapping:{program_id}:{step_index}"
                )
            relation_type = _upper(item.get("relation") or item.get("relation_type"))
            direction = _upper(item.get("direction"))
            if not relation_type:
                raise CanonicalCompilerConfigurationError(
                    f"semantic_program_invalid_step:{program_id}:{step_index}"
                )
            steps.append(
                CanonicalProgramStep(
                    relation_type=relation_type,
                    direction=direction,
                    expected_source_type=_optional_type(item, "expected_source_type", "source_type"),
                    expected_target_type=_optional_type(item, "expected_target_type", "target_type"),
                )
            )
        try:
            priority = int(raw.get("priority", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise CanonicalCompilerConfigurationError(f"semantic_program_priority_invalid:{program_id}") from exc
        projection = _upper(raw.get("plan_projection") or raw.get("projection") or "TYPED_FACTS")
        if projection not in {"NODE_ONLY", "EDGES", "TYPED_FACTS", "AGGREGATION"}:
            raise CanonicalCompilerConfigurationError(f"semantic_program_projection_invalid:{program_id}")
        plan_type = None
        if raw.get("plan_type") is not None:
            try:
                plan_type = CanonicalPlanType(_upper(raw.get("plan_type")))
            except ValueError as exc:
                raise CanonicalCompilerConfigurationError(f"semantic_program_plan_type_invalid:{program_id}") from exc
        constraints = tuple(
            _load_constraint(item, path=f"semantic_program.{program_id}.normative_constraints")
            for item in (raw.get("normative_constraints") or ())
        )
        annotations = tuple(
            _load_annotation(item, path=f"semantic_program.{program_id}.annotations")
            for item in (raw.get("annotations") or ())
        )
        metadata = raw.get("metadata")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise CanonicalCompilerConfigurationError(f"semantic_program_metadata_invalid:{program_id}")
        metadata = metadata or {}
        # These are canonical typed declarations, not opaque legacy semantic
        # requirements.  They are intentionally limited to neutral concepts.
        if metadata.get("required_subgraph") is not None:
            constraints += (NormativeSemanticConstraint("REQUIRED_SUBGRAPH", metadata["required_subgraph"]),)
        if metadata.get("path_selection_key") is not None:
            constraints += (NormativeSemanticConstraint("PATH_SELECTION_KEY", metadata["path_selection_key"]),)
        aggregation = _load_aggregation(raw.get("aggregation"))
        programs.append(
            CanonicalSemanticProgram(
                program_id=program_id,
                patterns=tuple(_text(item) for item in patterns if _text(item)),
                anchor_type=anchor_type,
                steps=tuple(steps),
                projection=projection,
                plan_type=plan_type,
                priority=priority,
                normative_constraints=constraints,
                annotations=annotations,
                aggregation=aggregation,
            )
        )
    return tuple(programs)


def _optional_type(item: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = _upper(item.get(key))
        if value:
            return value
    return None


def _load_aggregation(value: Any) -> Optional[CanonicalAggregation]:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise CanonicalCompilerConfigurationError("semantic_program_aggregation_invalid")
    date_keys = value.get("date_keys") or ()
    if isinstance(date_keys, str):
        date_keys = (date_keys,)
    return CanonicalAggregation(
        operation=_upper(value.get("operation") or value.get("op")),
        top_n=value.get("top_n"),
        date_keys=tuple(_text(item) for item in date_keys if _text(item)),
        group_by_node_type=_upper(value.get("group_by_node_type")) or None,
        group_by_relation_type=_upper(value.get("group_by_relation_type")) or None,
    )


def _normalize_candidate(value: Any) -> Optional[CanonicalEntityCandidate]:
    if isinstance(value, CanonicalEntityCandidate):
        return value
    if isinstance(value, Mapping):
        node_id = _text(value.get("node_id") or value.get("id"))
        node_type = _upper(value.get("node_type") or value.get("type"))
        display_name = _text(value.get("display_name") or value.get("name") or node_id)
        score = value.get("score", 0.0)
    else:
        node_id = _text(getattr(value, "node_id", None) or getattr(value, "id", None))
        node_type = _upper(getattr(value, "node_type", None) or getattr(value, "type", None))
        display_name = _text(getattr(value, "display_name", None) or getattr(value, "name", None) or node_id)
        score = getattr(value, "score", 0.0)
    if not node_id or not node_type:
        return None
    try:
        numeric_score = float(score or 0.0)
    except (TypeError, ValueError):
        numeric_score = 0.0
    return CanonicalEntityCandidate(node_id, node_type, display_name, numeric_score)


def _resolver_candidates(
    resolver: Optional[CanonicalEntityResolver],
    mention: str,
    expected_type: Optional[str],
) -> Tuple[CanonicalEntityCandidate, ...]:
    if resolver is None:
        return ()
    try:
        raw = resolver.resolve(mention, expected_type)
    except TypeError:
        raw = resolver.resolve(mention)  # type: ignore[misc]
    candidates = [candidate for candidate in (_normalize_candidate(item) for item in (raw or ())) if candidate is not None]
    if expected_type:
        candidates = [item for item in candidates if item.node_type == _upper(expected_type)]
    return tuple(
        sorted(
            candidates,
            key=lambda item: (-float(item.score), item.node_type, item.node_id, item.display_name),
        )
    )


def _resolve_one(
    resolver: Optional[CanonicalEntityResolver],
    mention: str,
    expected_type: Optional[str],
) -> CanonicalEntityCandidate:
    candidates = _resolver_candidates(resolver, mention, expected_type)
    if not candidates:
        raise CanonicalSemanticRejection("entity_not_found")
    if len(candidates) > 1 and float(candidates[0].score) == float(candidates[1].score):
        raise CanonicalSemanticRejection("entity_ambiguous")
    return candidates[0]


def _template_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a canonical literal/template or explicitly supplied regex."""
    if re.search(r"<[A-Za-z][A-Za-z0-9_]*>", pattern):
        pieces = []
        cursor = 0
        for match in re.finditer(r"<([A-Za-z][A-Za-z0-9_]*)>", pattern):
            pieces.append(re.escape(pattern[cursor : match.start()]))
            group = match.group(1).upper()
            pieces.append(rf"(?P<{group}>.+?)")
            cursor = match.end()
        pieces.append(re.escape(pattern[cursor:]))
        return re.compile(r"^" + "".join(pieces) + r"$", flags=re.IGNORECASE)
    try:
        return re.compile(pattern, flags=re.IGNORECASE)
    except re.error as exc:
        raise CanonicalCompilerConfigurationError("semantic_program_pattern_invalid") from exc


def _program_matches(
    programs: Sequence[CanonicalSemanticProgram], question: str
) -> Tuple[CanonicalSemanticProgram, re.Match[str], str]:
    matches = []
    normalized_question = question.strip().strip("?").strip()
    for program in programs:
        for pattern in program.patterns:
            compiled = _template_pattern(pattern)
            match = compiled.search(normalized_question)
            if match is None:
                match = compiled.search(question.strip())
            if match:
                matches.append((program, match, pattern, len(pattern)))
                break
    if not matches:
        return None  # type: ignore[return-value]
    matches.sort(key=lambda item: (-item[0].priority, -item[3], item[0].program_id))
    top = matches[0]
    tied = [item for item in matches if item[0].priority == top[0].priority and item[3] == top[3]]
    if len({item[0].program_id for item in tied}) > 1:
        raise CanonicalSemanticRejection(
            "semantic_program_ambiguous",
            ",".join(sorted(item[0].program_id for item in tied)),
        )
    return top[0], top[1], top[2]


def _matching_programs(
    programs: Sequence[CanonicalSemanticProgram], question: str
) -> Tuple[CanonicalSemanticProgram, ...]:
    """Return every declaration-level semantic-program match without resolving.

    This is a recognition-only operation.  It performs no entity lookup and
    does not change the compiler's existing priority selection semantics.
    Runtime activation profiles use it to reject generic fallback requests
    before a resolver or execution store is touched.
    """

    normalized_question = question.strip().strip("?").strip()
    matches = []
    for program in programs:
        for pattern in program.patterns:
            compiled = _template_pattern(pattern)
            match = compiled.search(normalized_question)
            if match is None:
                match = compiled.search(question.strip())
            if match:
                matches.append((program, len(pattern)))
                break
    matches.sort(key=lambda item: (-item[0].priority, -item[1], item[0].program_id))
    return tuple(item[0] for item in matches)


def _type_words(node_type: str) -> Tuple[str, ...]:
    lower = _text(node_type).lower()
    singular = lower[:-1] if lower.endswith("s") and not lower.endswith("ss") else lower
    plural = singular + "s"
    return tuple(dict.fromkeys((lower.replace("_", " "), singular.replace("_", " "), plural.replace("_", " "))))


def _relation_words(relation: CanonicalRelation) -> Tuple[str, ...]:
    raw = relation.relation_type.lower().replace("_", " ")
    words = [raw]
    if raw.endswith("s") and not raw.endswith("ss"):
        words.append(raw[:-1])
    words.extend(alias.lower() for alias in relation.aliases)
    return tuple(dict.fromkeys(item for item in words if item))


def _find_relation(question: str, relations: Sequence[CanonicalRelation]) -> Tuple[CanonicalRelation, str, int]:
    candidates = []
    lowered = question.lower()
    for relation in relations:
        for word in _relation_words(relation):
            match = re.search(r"(?<![\w])" + re.escape(word) + r"(?![\w])", lowered)
            if match:
                candidates.append((relation, word, len(word), match.start()))
    if not candidates:
        raise CanonicalSemanticRejection("unsupported_intent")
    candidates.sort(key=lambda item: (-item[2], item[0].relation_type, item[3]))
    top = candidates[0]
    tied = [item for item in candidates if item[2] == top[2] and item[3] == top[3]]
    if len({item[0].relation_type for item in tied}) > 1:
        raise CanonicalSemanticRejection("relation_ambiguous")
    return top[0], top[1], top[2]


def _selector_matches(text: str, node_type: str) -> bool:
    normalized = " ".join(_text(text).lower().split())
    return any(re.search(r"\b" + re.escape(word) + r"\b", normalized) for word in _type_words(node_type))


class CanonicalCompiler:
    """Compile canonical semantic inputs directly to the R4E-C logical plan."""

    def __init__(
        self,
        domain_pack: CanonicalDomainPack | Mapping[str, Any],
        *,
        entity_resolver: Optional[CanonicalEntityResolver] = None,
        compiler_id: str = CANONICAL_COMPILER_ID,
    ) -> None:
        self.domain_pack = (
            domain_pack
            if isinstance(domain_pack, CanonicalDomainPack)
            else CanonicalDomainPack.from_mapping(domain_pack)
        )
        self.entity_resolver = entity_resolver
        self.compiler_id = _text(compiler_id) or CANONICAL_COMPILER_ID

    def compile(
        self,
        question: str,
        *,
        declared_capabilities: Optional[Sequence[str]] = None,
        semantic_inputs: Optional[Mapping[str, Any]] = None,
    ) -> CanonicalCompileResult:
        try:
            if declared_capabilities is None and isinstance(semantic_inputs, Mapping):
                declared_capabilities = semantic_inputs.get("declared_capabilities")
            capabilities = tuple(
                sorted(
                    set(
                        _as_string_tuple(
                            self.domain_pack.capabilities if declared_capabilities is None else declared_capabilities,
                            upper=True,
                        )
                    )
                )
            )
            plan, provenance = self._compile_request(_text(question), capabilities)
            validate_logical_plan(plan)
            return CanonicalCompileResult(
                disposition=CompileDisposition.OK,
                reason_code="ok",
                plan=plan,
                semantic_program=provenance,
                diagnostics=(CanonicalDiagnostic("ok", "canonical logical plan compiled"),),
            )
        except CanonicalSemanticRejection as error:
            return CanonicalCompileResult(
                disposition=CompileDisposition.REJECTED,
                reason_code=error.reason_code,
                diagnostics=(CanonicalDiagnostic(error.reason_code, str(error)),),
            )
        except CanonicalPlanValidationError as error:
            reason = _validation_reason(str(error))
            return CanonicalCompileResult(
                disposition=CompileDisposition.REJECTED,
                reason_code=reason,
                diagnostics=(CanonicalDiagnostic(reason, str(error)),),
            )
        except CanonicalCompilerConfigurationError as error:
            return CanonicalCompileResult(
                disposition=CompileDisposition.FAILED,
                reason_code="configuration_error",
                diagnostics=(CanonicalDiagnostic("configuration_error", str(error)),),
            )
        except Exception as error:  # internal invariant failures are explicit failures
            return CanonicalCompileResult(
                disposition=CompileDisposition.FAILED,
                reason_code="internal_compiler_error",
                diagnostics=(CanonicalDiagnostic("internal_compiler_error", type(error).__name__),),
            )

    def match_semantic_program_ids(self, question: str) -> Tuple[str, ...]:
        """Recognize declared semantic programs without resolving entities."""

        return tuple(item.program_id for item in _matching_programs(self.domain_pack.semantic_programs, _text(question)))

    def _compile_request(
        self,
        question: str,
        capabilities: Tuple[str, ...],
    ) -> Tuple[CanonicalLogicalPlan, Optional[CanonicalSemanticProgramProvenance]]:
        if not question:
            raise CanonicalSemanticRejection("unsupported_intent")
        parts = _split_composite(question)
        if len(parts) > 1:
            return self._compile_composite(parts, capabilities)

        # Declared semantic programs are evaluated before generic rules.
        matched = _program_matches(self.domain_pack.semantic_programs, question)
        if matched:
            program, match, _pattern = matched
            return self._compile_program(question, capabilities, program, match)

        existence = re.match(r"^does\s+(.+?)\s+exist\??$", question, flags=re.IGNORECASE)
        if existence:
            return self._compile_existence(question, existence.group(1), capabilities)

        aggregation = self._detect_aggregation(question)
        relation_signal = _contains_relation_signal(question, self.domain_pack.relations)
        if aggregation is not None or relation_signal:
            relation, word, _length = _find_relation(question, self.domain_pack.relations)
            return self._compile_relation(question, capabilities, relation, word, aggregation)

        if _is_direct_lookup(question):
            return self._compile_direct_lookup(question, capabilities)

        raise CanonicalSemanticRejection("unsupported_intent")

    def _compile_program(
        self,
        question: str,
        capabilities: Tuple[str, ...],
        program: CanonicalSemanticProgram,
        match: re.Match[str],
    ) -> Tuple[CanonicalLogicalPlan, CanonicalSemanticProgramProvenance]:
        if program.source != "query.semantic_programs":
            raise CanonicalSemanticRejection("non_canonical_program_source")
        relation_steps = []
        current_type = program.anchor_type
        anchor_mention = ""
        groups = match.groupdict()
        for key, value in groups.items():
            if value and (key.upper() == program.anchor_type or not anchor_mention):
                anchor_mention = value.strip()
        if not anchor_mention:
            anchor_mention = _extract_program_mention(question, program.anchor_type)
        anchor = _resolve_one(self.entity_resolver, anchor_mention, program.anchor_type)

        for index, program_step in enumerate(program.steps):
            if program_step.direction not in {"IN", "OUT"}:
                raise CanonicalSemanticRejection("invalid_path_declaration")
            relation = self._relation(program_step.relation_type)
            if program_step.direction == "OUT":
                anchor_endpoint = relation.source_type
                reached_type = relation.target_type
            else:
                anchor_endpoint = relation.target_type
                reached_type = relation.source_type
            if index == 0 and anchor_endpoint != program.anchor_type:
                raise CanonicalSemanticRejection("invalid_path_declaration")
            if index > 0 and current_type not in {anchor_endpoint, "ENTITY", "ANY"}:
                raise CanonicalSemanticRejection("invalid_path_declaration")
            if program_step.expected_source_type and program_step.expected_source_type != relation.source_type:
                raise CanonicalSemanticRejection("invalid_path_declaration")
            if program_step.expected_target_type and program_step.expected_target_type != relation.target_type:
                raise CanonicalSemanticRejection("invalid_path_declaration")
            relation_steps.append(
                CanonicalStep(
                    relation=relation.relation_type,
                    direction=program_step.direction,
                    source_type=relation.source_type,
                    target_type=relation.target_type,
                )
            )
            current_type = reached_type

        if not relation_steps and program.projection == "NODE_ONLY":
            plan_type = program.plan_type or CanonicalPlanType.TRAVERSE
            required = ("ENTITY_LOOKUP",) if plan_type == CanonicalPlanType.TRAVERSE else self._required_capabilities(plan_type, False, None)
        else:
            plan_type = program.plan_type or CanonicalPlanType.TRAVERSE
            required = self._required_capabilities(plan_type, bool(relation_steps), program.aggregation)
        self._require_capabilities(required, capabilities)
        aggregation = program.aggregation
        if aggregation is not None:
            self._validate_aggregation_declared(aggregation)
        projection_kind = self._projection_for_question(question, program.projection)
        constraints = list(program.normative_constraints)
        if relation_steps and not constraints and plan_type == CanonicalPlanType.BOOLEAN_CHECK:
            # The proof path is already typed; no opaque metadata is needed.
            pass
        bounds = self._bounds_for(plan_type, len(relation_steps), aggregation, relation_steps, question)
        plan = self._make_plan(
            plan_type=plan_type,
            anchors=(CanonicalAnchor(anchor.node_type, anchor.node_id),),
            steps=tuple(relation_steps),
            projection=CanonicalProjection(projection_kind),
            bounds=bounds,
            capabilities=capabilities,
            required_capabilities=required,
            constraints=constraints,
            annotations=program.annotations,
            provenance=CanonicalSemanticProgramProvenance(program.source, program.program_id),
            aggregation=aggregation,
        )
        return plan, CanonicalSemanticProgramProvenance(program.source, program.program_id)

    def _compile_direct_lookup(
        self, question: str, capabilities: Tuple[str, ...]
    ) -> Tuple[CanonicalLogicalPlan, None]:
        mention = re.sub(r"^\s*(?:show|find|lookup|get|display)\s+", "", question, flags=re.IGNORECASE).strip(" ?")
        candidates = _resolver_candidates(self.entity_resolver, mention, None)
        if not candidates:
            raise CanonicalSemanticRejection("entity_not_found")
        candidate = _resolve_one(self.entity_resolver, mention, candidates[0].node_type)
        required = ("ENTITY_LOOKUP",)
        self._require_capabilities(required, capabilities)
        return self._make_plan(
            plan_type=CanonicalPlanType.TRAVERSE,
            anchors=(CanonicalAnchor(candidate.node_type, candidate.node_id),),
            steps=(),
            projection=CanonicalProjection("NODE_ONLY"),
            bounds=CanonicalBounds(0, 1, 1),
            capabilities=capabilities,
            required_capabilities=required,
            constraints=(),
            annotations=(),
            provenance=None,
            aggregation=None,
        ), None

    def _compile_existence(
        self, question: str, mention: str, capabilities: Tuple[str, ...]
    ) -> Tuple[CanonicalLogicalPlan, None]:
        candidates = _resolver_candidates(self.entity_resolver, mention.strip(" ?"), None)
        if not candidates:
            # The anchor identity remains a semantic input for canonical
            # existence checks only when a resolver can name it.  No guessing.
            raise CanonicalSemanticRejection("entity_not_found")
        candidate = _resolve_one(self.entity_resolver, mention.strip(" ?"), candidates[0].node_type)
        required = ("EXISTENCE_CHECK",)
        self._require_capabilities(required, capabilities)
        constraints = ()
        if self.domain_pack.world.mode == CanonicalWorldMode.CLOSED_WORLD:
            constraints = (NormativeSemanticConstraint("CLOSED_WORLD_SCOPE", self.domain_pack.world.scope),)
        return self._make_plan(
            plan_type=CanonicalPlanType.EXISTS,
            anchors=(CanonicalAnchor(candidate.node_type, candidate.node_id),),
            steps=(),
            projection=CanonicalProjection("NODE_ONLY"),
            bounds=CanonicalBounds(0, 1, 1),
            capabilities=capabilities,
            required_capabilities=required,
            constraints=constraints,
            annotations=(),
            provenance=None,
            aggregation=None,
        ), None

    def _compile_relation(
        self,
        question: str,
        capabilities: Tuple[str, ...],
        relation: CanonicalRelation,
        relation_word: str,
        aggregation: Optional[CanonicalAggregation],
    ) -> Tuple[CanonicalLogicalPlan, None]:
        match_out = re.search(
            r"\bdoes\s+(.+?)\s+" + re.escape(relation_word) + r"(?:\s+(.+?))?(?:\?|$)",
            question,
            flags=re.IGNORECASE,
        )
        match_in = re.search(
            r"\b(?:which|what|who)\s+(.+?)\s+" + re.escape(relation_word) + r"\s+(.+?)(?:\?|$)",
            question,
            flags=re.IGNORECASE,
        )
        match_aggregate_out = re.search(
            r"\b(?:top\s+\d+|latest|most\s+recent)\s+(.+?)\s+([A-Z][A-Za-z0-9 _-]*?)\s+"
            + re.escape(relation_word)
            + r"\b",
            question,
            flags=re.IGNORECASE,
        )
        direction = "OUT"
        anchor_mention = ""
        target_mention = ""
        selector = ""
        if match_out:
            left = match_out.group(1).strip()
            right = (match_out.group(2) or "").strip()
            if _is_negative_subject(left):
                direction = "IN"
                anchor_mention = right.strip(" ?")
            else:
                direction = "OUT"
                anchor_mention = left.strip(" ?")
                target_mention = right.strip(" ?")
        elif match_aggregate_out:
            selector = match_aggregate_out.group(1).strip()
            anchor_mention = match_aggregate_out.group(2).strip(" ?")
            direction = "OUT"
            if not _selector_matches(selector, relation.target_type):
                raise CanonicalSemanticRejection("unsupported_intent")
        elif match_in:
            selector = match_in.group(1).strip()
            target_mention = match_in.group(2).strip(" ?")
            if not _selector_matches(selector, relation.source_type):
                # A generic rule cannot turn an unrelated modifier (for
                # example, “legally”) into a schema relation.
                raise CanonicalSemanticRejection("unsupported_intent")
            direction = "IN"
            anchor_mention = target_mention
        else:
            raise CanonicalSemanticRejection("unsupported_intent")

        anchor_type = relation.source_type if direction == "OUT" else relation.target_type
        if selector and direction == "OUT" and not _selector_matches(selector, relation.target_type):
            raise CanonicalSemanticRejection("unsupported_intent")
        anchor = _resolve_one(self.entity_resolver, anchor_mention, anchor_type)

        plan_type = CanonicalPlanType.AGGREGATE if aggregation is not None else CanonicalPlanType.TRAVERSE
        if match_out and _is_boolean_question(question):
            plan_type = CanonicalPlanType.BOOLEAN_CHECK
        required = self._required_capabilities(plan_type, True, aggregation)
        self._require_capabilities(required, capabilities)

        constraints = []
        if aggregation is not None:
            self._validate_aggregation_declared(aggregation)
        if plan_type == CanonicalPlanType.BOOLEAN_CHECK and target_mention and direction == "OUT":
            target = _resolve_one(self.entity_resolver, target_mention, relation.target_type)
            constraints.append(NormativeSemanticConstraint("TARGET_ID", target.node_id))
        steps = (
            CanonicalStep(
                relation=relation.relation_type,
                direction=direction,
                source_type=relation.source_type,
                target_type=relation.target_type,
            ),
        )
        projection = "AGGREGATION" if aggregation is not None else "TYPED_FACTS"
        if re.search(r"\bas\s+edges\b", question, flags=re.IGNORECASE):
            projection = "EDGES"
        max_results = self.domain_pack.max_results
        cardinality = self.domain_pack.cardinality_cap_per_hop
        if plan_type == CanonicalPlanType.BOOLEAN_CHECK and not _is_negative_subject(match_out.group(1) if match_out else ""):
            max_results = 1
            cardinality = 1
        bounds = self._bounds_for(plan_type, 1, aggregation, steps, question, max_results=max_results, cardinality=cardinality)
        return self._make_plan(
            plan_type=plan_type,
            anchors=(CanonicalAnchor(anchor.node_type, anchor.node_id),),
            steps=steps,
            projection=CanonicalProjection(projection),
            bounds=bounds,
            capabilities=capabilities,
            required_capabilities=required,
            constraints=tuple(constraints),
            annotations=(),
            provenance=None,
            aggregation=aggregation,
        ), None

    def _compile_composite(
        self,
        parts: Sequence[str],
        capabilities: Tuple[str, ...],
    ) -> Tuple[CanonicalLogicalPlan, None]:
        self._require_capabilities(("COMPOSITION",), capabilities)
        units = []
        child_capabilities = capabilities
        for index, part in enumerate(parts, start=1):
            child, _ = self._compile_request(part, child_capabilities)
            units.append(
                CanonicalLogicalUnit(
                    unit_id=f"u{index}",
                    logical_plan=child,
                    dependencies=(),
                    required=True,
                )
            )
        max_hops = max((unit.logical_plan.bounds.max_hops for unit in units), default=0)
        max_results = max((unit.logical_plan.bounds.max_results for unit in units), default=self.domain_pack.max_results)
        parent = self._make_plan(
            plan_type=CanonicalPlanType.COMPOSITE,
            anchors=(),
            steps=(),
            projection=CanonicalProjection("COMPOSITE"),
            bounds=CanonicalBounds(max_hops, max_results, self.domain_pack.cardinality_cap_per_hop),
            capabilities=capabilities,
            required_capabilities=("COMPOSITION",),
            constraints=(NormativeSemanticConstraint("ORDERED_UNITS", [unit.unit_id for unit in units]),),
            annotations=(),
            provenance=None,
            aggregation=None,
            composition_units=tuple(units),
        )
        return parent, None

    def _make_plan(
        self,
        *,
        plan_type: CanonicalPlanType,
        anchors: Tuple[CanonicalAnchor, ...],
        steps: Tuple[CanonicalStep, ...],
        projection: CanonicalProjection,
        bounds: CanonicalBounds,
        capabilities: Tuple[str, ...],
        required_capabilities: Sequence[str],
        constraints: Sequence[NormativeSemanticConstraint],
        annotations: Sequence[SemanticAnnotation],
        provenance: Optional[CanonicalSemanticProgramProvenance],
        aggregation: Optional[CanonicalAggregation],
        composition_units: Tuple[CanonicalLogicalUnit, ...] = (),
    ) -> CanonicalLogicalPlan:
        all_constraints = list(constraints)
        if self.domain_pack.max_hops is not None and bounds.max_hops > self.domain_pack.max_hops:
            all_constraints.append(NormativeSemanticConstraint("GOVERNANCE_MAX_HOPS", self.domain_pack.max_hops))
        uses = tuple(
            CanonicalCapabilityUse(capability, "domain_pack")
            for capability in sorted(set(_upper(item) for item in required_capabilities))
        )
        plan = CanonicalLogicalPlan(
            planner_id=self.compiler_id,
            domain_id=self.domain_pack.domain_id,
            domain_pack_fingerprint=self.domain_pack.pack_fingerprint,
            domain_pack_version=self.domain_pack.pack_version,
            plan_type=plan_type,
            anchors=anchors,
            steps=steps,
            projection=projection,
            bounds=bounds,
            world=self.domain_pack.world,
            declared_capabilities=tuple(capabilities),
            capability_use=uses,
            normative_constraints=tuple(all_constraints),
            annotations=tuple(annotations),
            semantic_program=provenance,
            aggregation=aggregation,
            composition_units=composition_units,
            composition_policy=self.domain_pack.composition_policy,
        )
        return plan

    def _bounds_for(
        self,
        plan_type: CanonicalPlanType,
        path_length: int,
        aggregation: Optional[CanonicalAggregation],
        steps: Sequence[CanonicalStep],
        question: str,
        *,
        max_results: Optional[int] = None,
        cardinality: Optional[int] = None,
    ) -> CanonicalBounds:
        max_hops = 0 if not steps else path_length
        if aggregation is not None and aggregation.top_n is not None:
            max_results = int(aggregation.top_n)
        if max_results is None:
            max_results = self.domain_pack.max_results
        if plan_type in {CanonicalPlanType.EXISTS} or (not steps and plan_type == CanonicalPlanType.TRAVERSE):
            max_results = 1
        if cardinality is None:
            cardinality = self.domain_pack.cardinality_cap_per_hop
        if not steps:
            cardinality = 1
        return CanonicalBounds(max_hops, max(1, int(max_results)), max(1, int(cardinality)))

    def _relation(self, relation_type: str) -> CanonicalRelation:
        for relation in self.domain_pack.relations:
            if relation.relation_type == _upper(relation_type):
                return relation
        raise CanonicalSemanticRejection("invalid_path_declaration")

    def _required_capabilities(
        self,
        plan_type: CanonicalPlanType,
        has_path: bool,
        aggregation: Optional[CanonicalAggregation],
    ) -> Tuple[str, ...]:
        if plan_type == CanonicalPlanType.COMPOSITE:
            return ("COMPOSITION",)
        if plan_type == CanonicalPlanType.EXISTS:
            return ("EXISTENCE_CHECK",)
        if not has_path and plan_type == CanonicalPlanType.TRAVERSE:
            return ("ENTITY_LOOKUP",)
        if plan_type == CanonicalPlanType.BOOLEAN_CHECK:
            return ("BOOLEAN_CHECK",)
        if aggregation is not None or plan_type == CanonicalPlanType.AGGREGATE:
            return ("AGGREGATION", "RELATION_LOOKUP")
        return ("RELATION_LOOKUP",)

    def _require_capabilities(self, required: Sequence[str], declared: Sequence[str]) -> None:
        pack_caps = set(self.domain_pack.capabilities)
        declared_caps = set(declared)
        for capability in sorted(set(_upper(item) for item in required)):
            if capability not in pack_caps or capability not in declared_caps:
                if capability == "ENTITY_LOOKUP":
                    raise CanonicalSemanticRejection("entity_lookup_unsupported")
                raise CanonicalSemanticRejection("capability_unsupported")

    def _detect_aggregation(self, question: str) -> Optional[CanonicalAggregation]:
        lowered = question.lower()
        operation = None
        top_n = None
        if re.search(r"\bhow\s+many\b", lowered):
            operation = "COUNT"
        else:
            top_match = re.search(r"\btop\s+(\d+)\b", lowered)
            if top_match:
                operation = "TOP_N"
                top_n = int(top_match.group(1))
            elif re.search(r"\blatest\b", lowered):
                operation = "LATEST"
        if operation is None:
            return None
        if operation not in set(self.domain_pack.aggregation_operations):
            raise CanonicalSemanticRejection("unsupported_intent")
        date_keys = self.domain_pack.aggregation_date_keys if operation in {"TOP_N", "LATEST"} else ()
        if operation in {"TOP_N", "LATEST"} and not date_keys:
            raise CanonicalSemanticRejection("aggregation_date_keys_required")
        return CanonicalAggregation(operation=operation, top_n=top_n, date_keys=date_keys)

    def _validate_aggregation_declared(self, aggregation: CanonicalAggregation) -> None:
        if aggregation.operation in {"TOP_N", "LATEST"} and not aggregation.date_keys:
            raise CanonicalSemanticRejection("aggregation_date_keys_required")

    def _projection_for_question(self, question: str, declared: str) -> str:
        if re.search(r"\bas\s+edges\b", question, flags=re.IGNORECASE):
            return "EDGES"
        return declared


def _validation_reason(message: str) -> str:
    if message == "path_exceeds_governance_max_hops":
        return "max_hops_exceeds_governance"
    if message == "direct_lookup_capability_required":
        return "entity_lookup_unsupported"
    if message == "semantic_program_multiple_matches":
        return "semantic_program_ambiguous"
    return message.split(":", 1)[0] or "canonical_plan_invalid"


def _split_composite(question: str) -> Tuple[str, ...]:
    parts = tuple(item.strip(" ?") for item in re.split(r"\s+and\s+", question, flags=re.IGNORECASE) if item.strip(" ?"))
    return parts if len(parts) > 1 else (question,)


def _is_direct_lookup(question: str) -> bool:
    return bool(re.match(r"^\s*(?:show|find|lookup|get|display)\s+.+", question, flags=re.IGNORECASE))


def _is_boolean_question(question: str) -> bool:
    return bool(re.match(r"^\s*does\b", question, flags=re.IGNORECASE))


def _is_negative_subject(subject: str) -> bool:
    return _text(subject).lower() in {"nobody", "no one", "noone", "nothing"}


def _contains_relation_signal(question: str, relations: Sequence[CanonicalRelation]) -> bool:
    lowered = question.lower()
    return any(
        re.search(r"(?<![\w])" + re.escape(word) + r"(?![\w])", lowered)
        for relation in relations
        for word in _relation_words(relation)
    )


def _extract_program_mention(question: str, anchor_type: str) -> str:
    # A canonical program should normally provide a typed placeholder.  This
    # fallback handles a declaration with a fixed phrase without guessing an
    # unrelated relation; the resolver remains the authority on identity.
    words = _type_words(anchor_type)
    match = re.search(r"(?:which|what|who|show|find|lookup|get)\s+(.+)", question, flags=re.IGNORECASE)
    if match:
        value = match.group(1).strip(" ?")
        for word in words:
            value = re.sub(r"\b" + re.escape(word) + r"\b", "", value, flags=re.IGNORECASE).strip()
        if value:
            return value
    raise CanonicalSemanticRejection("entity_not_found")


@dataclass(frozen=True)
class MappingEntityResolver:
    """Small deterministic resolver for synthetic/reference conformance."""

    entities: Tuple[CanonicalEntityCandidate, ...]

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "MappingEntityResolver":
        candidates = []
        for value in values.values():
            item = _normalize_candidate(value)
            if item is not None:
                candidates.append(item)
        return cls(tuple(candidates))

    def resolve(self, mention: str, expected_type: Optional[str] = None) -> Sequence[CanonicalEntityCandidate]:
        normalized = " ".join(_text(mention).strip(" ?").lower().split())
        expected = _upper(expected_type)
        candidates = [
            item
            for item in self.entities
            if (not expected or item.node_type == expected)
            and normalized in {
                item.display_name.lower(),
                item.node_id.lower(),
                item.node_id.split(":", 1)[-1].replace("_", " ").lower(),
            }
        ]
        return tuple(sorted(candidates, key=lambda item: (-item.score, item.node_type, item.node_id)))


__all__ = [
    "CANONICAL_COMPILER_ID",
    "CANONICAL_COMPILER_PROTOCOL_ID",
    "CANONICAL_COMPILER_PROTOCOL_VERSION",
    "CanonicalCompiler",
    "CanonicalCompilerConfigurationError",
    "CanonicalCompileResult",
    "CanonicalDiagnostic",
    "CanonicalDomainPack",
    "CanonicalEntityCandidate",
    "CanonicalEntityResolver",
    "CanonicalRelation",
    "CanonicalSemanticProgram",
    "CanonicalProgramStep",
    "CompileDisposition",
    "MappingEntityResolver",
    "lower_logical_plan",
]
