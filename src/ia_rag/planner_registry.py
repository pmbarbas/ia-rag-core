"""Neutral planner-selection and route-registration contracts.

The registry is deliberately unaware of application domains.  Domain packs
declare a planner identifier; composition roots register the implementation and
the criteria under which that identifier is valid.  Selection is fail-closed:
an unsupported planner or an unresolved priority conflict is an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


class PlannerSelectionError(ValueError):
    """Base error for fail-closed planner selection."""


class UnsupportedPlannerError(PlannerSelectionError):
    """The requested planner has no registration for the active domain pack."""


class AmbiguousPlannerError(PlannerSelectionError):
    """More than one registration remains after deterministic priority."""


@dataclass(frozen=True)
class PlannerSelection:
    """The planner choice declared by a domain pack before compilation."""

    planner_id: str
    domain_name: str
    source: str = "domain_pack"
    # Kept out of equality so the historical three-field public value remains
    # compatible while registration matching can use pack identity.
    domain_pack_identity: str = field(default="", compare=False, repr=False)


@dataclass(frozen=True)
class PlannerContext:
    """Neutral dependencies made available to a registered planner."""

    planner_id: str
    domain_name: str
    domain_pack_identity: str
    domain_source: Any
    raw: Dict[str, Any]
    compiler: Any
    assurance: Any
    hybrid_reasoning: Any
    attach_continuity_to_plan: Callable[..., Any]
    composition_policy: Callable[[], str]


@dataclass(frozen=True)
class PlannerRegistration:
    """Metadata and implementation for one planner capability."""

    planner_id: str
    route_fn: Callable[..., "RouteResult"]
    supported_domains: Tuple[str, ...] = ()
    supported_domain_packs: Tuple[str, ...] = ()
    planner_type: str = "generic"
    capabilities: Tuple[str, ...] = ()
    priority: int = 0
    can_handle_fn: Optional[Callable[..., bool]] = None
    execution_path: Tuple[str, ...] = ()
    requires_projection_policy: bool = False

    def __post_init__(self) -> None:
        planner_id = str(self.planner_id or "").strip()
        if not planner_id:
            raise ValueError("planner_id is required")
        if not callable(self.route_fn):
            raise TypeError("route_fn must be callable")
        object.__setattr__(self, "planner_id", planner_id)
        object.__setattr__(self, "supported_domains", _normalized_tuple(self.supported_domains))
        object.__setattr__(self, "supported_domain_packs", _normalized_tuple(self.supported_domain_packs))
        object.__setattr__(self, "planner_type", str(self.planner_type or "generic").strip())
        object.__setattr__(self, "capabilities", _normalized_tuple(self.capabilities))
        object.__setattr__(self, "execution_path", _normalized_tuple(self.execution_path))
        object.__setattr__(self, "requires_projection_policy", bool(self.requires_projection_policy))
        object.__setattr__(self, "priority", int(self.priority))

    def matches(self, selection: PlannerSelection) -> bool:
        if self.planner_id != str(selection.planner_id or "").strip():
            return False
        domain = str(selection.domain_name or "").strip()
        pack = str(selection.domain_pack_identity or "").strip()
        if self.supported_domains and domain not in self.supported_domains:
            return False
        if self.supported_domain_packs and pack not in self.supported_domain_packs:
            return False
        return True

    def can_handle(self, context: PlannerContext, query: str) -> bool:
        if self.can_handle_fn is None:
            return True
        return bool(self.can_handle_fn(context, query))


@dataclass(frozen=True)
class RouteResult:
    """Planner output, retaining the selected logical/executable lineage."""

    domain_name: str
    planner_name: str
    plan: Optional[Any]
    plans: List[Any] = field(default_factory=list)
    interpretation: Any = None
    compile_result: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    selection: Optional[PlannerSelection] = None
    logical_plan: Any = None
    logical_plans: List[Any] = field(default_factory=list)


def _normalized_tuple(values: Sequence[Any]) -> Tuple[str, ...]:
    return tuple(str(value or "").strip() for value in values if str(value or "").strip())


class PlannerRegistry:
    """Explicit, domain-neutral planner registry with fail-closed resolution."""

    def __init__(self) -> None:
        self._registrations: List[PlannerRegistration] = []

    @property
    def registrations(self) -> Tuple[PlannerRegistration, ...]:
        return tuple(self._registrations)

    def register(
        self,
        registration: PlannerRegistration | str,
        route_fn: Optional[Callable[..., RouteResult]] = None,
        *,
        supported_domains: Sequence[str] = (),
        supported_domain_packs: Sequence[str] = (),
        planner_type: str = "generic",
        capabilities: Sequence[str] = (),
        priority: int = 0,
        can_handle_fn: Optional[Callable[..., bool]] = None,
        execution_path: Sequence[str] = (),
        requires_projection_policy: bool = False,
    ) -> PlannerRegistration:
        """Register one planner and return its immutable registration.

        The string form is retained as a small compatibility convenience, but
        all registrations are normalized to explicit metadata before storage.
        """
        if isinstance(registration, PlannerRegistration):
            if route_fn is not None:
                raise TypeError("route_fn cannot accompany PlannerRegistration")
            candidate = registration
        else:
            candidate = PlannerRegistration(
                planner_id=registration,
                route_fn=route_fn,
                supported_domains=tuple(supported_domains),
                supported_domain_packs=tuple(supported_domain_packs),
                planner_type=planner_type,
                capabilities=tuple(capabilities),
                priority=priority,
                can_handle_fn=can_handle_fn,
                execution_path=tuple(execution_path),
                requires_projection_policy=requires_projection_policy,
            )
        if any(existing == candidate for existing in self._registrations):
            raise ValueError(f"Planner registration '{candidate.planner_id}' is already registered")
        self._registrations.append(candidate)
        return candidate

    def resolve_registration(self, selection: PlannerSelection) -> PlannerRegistration:
        matches = [item for item in self._registrations if item.matches(selection)]
        if not matches:
            raise UnsupportedPlannerError(
                f"Unsupported planner '{selection.planner_id}' for domain '{selection.domain_name}'."
            )
        highest = max(item.priority for item in matches)
        winners = [item for item in matches if item.priority == highest]
        if len(winners) != 1:
            ids = ", ".join(sorted(item.planner_id for item in winners))
            raise AmbiguousPlannerError(
                f"Ambiguous planner '{selection.planner_id}' for domain '{selection.domain_name}': {ids}."
            )
        return winners[0]

    def resolve(self, selection: PlannerSelection) -> Callable[..., RouteResult]:
        """Compatibility accessor returning the selected route implementation."""
        return self.resolve_registration(selection).route_fn
