"""Deterministic query router for planner selection."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Dict, Iterable, List, Optional

from .domain_utils import normalize_domain_schema
from .assurance_protocols import (
    AssuranceProvider,
    resolve_assurance_provider,
)
from .planner_registry import (
    AmbiguousPlannerError,
    PlannerContext,
    PlannerRegistration,
    PlannerRegistry,
    PlannerSelection,
    PlannerSelectionError,
    RouteResult,
    UnsupportedPlannerError,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return dict(value)
    except Exception:
        return {}


@dataclass(frozen=True)
class _NoOpRefinementResult:
    plans: List[Any]
    metadata: Dict[str, Any]


class _NoOpHybridReasoning:
    """Internal neutral value; optional refinement is never imported by default."""

    enabled = False

    @staticmethod
    def refine(plan: Any) -> Any:
        return plan

    @classmethod
    def refine_many(cls, plans: Iterable[Any]) -> _NoOpRefinementResult:
        return _NoOpRefinementResult(list(plans or ()), {"enabled": False})


class QueryRouter:
    """
    Deterministically route a query to the planner declared by the domain pack.
    """

    def __init__(
        self,
        domain_config: Any,
        *,
        compiler: Any = None,
        hybrid_reasoning: Optional[Any] = None,
        assurance_provider: Optional[AssuranceProvider] = None,
        planner_registry: Optional[PlannerRegistry] = None,
        planner_id_override: Optional[str] = None,
    ):
        self._domain_source = domain_config
        if hasattr(domain_config, "raw"):
            raw = dict(getattr(domain_config, "raw", {}) or {})
        elif hasattr(domain_config, "schema"):
            raw = dict(getattr(domain_config, "schema", {}) or {})
        else:
            raw = dict(domain_config or {})

        self.raw = normalize_domain_schema(raw, context="QueryRouter", allow_default=False)
        self.domain_name = str(self.raw.get("domain_name") or "").strip()
        self.query_config = self.raw.get("query", {}) if isinstance(self.raw.get("query"), dict) else {}
        self.router_config = self.query_config.get("router", {}) if isinstance(self.query_config.get("router"), dict) else {}
        self.planner_name = str(planner_id_override or self.router_config.get("planner") or "").strip()
        self.planner_source = "runtime_authority" if planner_id_override else "domain_pack"
        self.compiler = compiler
        self.assurance = resolve_assurance_provider(assurance_provider)
        hybrid_enabled = bool(self.router_config.get("hybrid_reasoning", False))
        if hybrid_reasoning is not None:
            self.hybrid_reasoning = hybrid_reasoning
        elif hybrid_enabled:
            optional_type = getattr(import_module(f"{__package__}.hybrid_reasoning"), "HybridReasoningLayer")
            self.hybrid_reasoning = optional_type(enabled=True)
        else:
            self.hybrid_reasoning = _NoOpHybridReasoning()
        self.planner_registry = planner_registry or PlannerRegistry()
        if not self.planner_name:
            raise ValueError(
                f"Domain '{self.domain_name}' is missing query.router.planner in its schema."
            )

    def select_planner(self, query: str = "") -> PlannerSelection:
        """Select exactly one registered planner before planner compilation."""
        del query  # Selection is domain-configured and intentionally deterministic.
        selection = PlannerSelection(
            planner_id=self.planner_name,
            domain_name=self.domain_name,
            source=self.planner_source,
            domain_pack_identity=self._domain_pack_identity(),
        )
        # Resolve now so an invalid planner fails at the selection boundary,
        # without falling through to another planner.
        self.planner_registry.resolve_registration(selection)
        return selection

    def resolve_registration(self, selection: PlannerSelection) -> PlannerRegistration:
        return self.planner_registry.resolve_registration(selection)

    def can_handle(self, query: str) -> bool:
        """Check whether the selected planner recognizes a request.

        This is a recognition probe, not compilation.  It exists for an
        application dispatch boundary and never invokes a fallback planner.
        """
        selection = self.select_planner(query)
        registration = self.resolve_registration(selection)
        return registration.can_handle(self._planner_context(selection), query)

    def route(
        self,
        query: str,
        *,
        compile_result: Any = None,
        principal_context: Any = None,
        selection: Optional[PlannerSelection] = None,
    ) -> RouteResult:
        selection = selection or self.select_planner(query)
        registration = self.resolve_registration(selection)
        route_fn = registration.route_fn
        routed = route_fn(
            self._planner_context(selection),
            query,
            compile_result=compile_result,
            principal_context=principal_context,
        )
        if str(routed.planner_name or "").strip() != selection.planner_id:
            raise RuntimeError(
                "planner_selection_mismatch: "
                f"selected={selection.planner_id} routed={routed.planner_name}"
            )
        return RouteResult(
            domain_name=routed.domain_name,
            planner_name=routed.planner_name,
            plan=routed.plan,
            plans=list(routed.plans or []),
            interpretation=routed.interpretation,
            compile_result=routed.compile_result,
            metadata=dict(routed.metadata or {}),
            selection=selection,
            logical_plan=routed.logical_plan,
            logical_plans=list(routed.logical_plans or []),
        )

    def _planner_context(self, selection: PlannerSelection) -> PlannerContext:
        return PlannerContext(
            planner_id=selection.planner_id,
            domain_name=self.domain_name,
            domain_pack_identity=self._domain_pack_identity(),
            domain_source=self._domain_source,
            raw=dict(self.raw),
            compiler=self.compiler,
            assurance=self.assurance,
            hybrid_reasoning=self.hybrid_reasoning,
            attach_continuity_to_plan=self._attach_continuity_to_plan,
            composition_policy=self._composition_policy,
        )

    def _attach_continuity_to_plan(
        self,
        plan: Any,
        *,
        principal_context: Any,
        step_ordinal: int,
    ) -> Any:
        # Planner-specific continuity attachment belongs to the registered
        # planner.  The neutral router never imports or constructs a plan type.
        del principal_context, step_ordinal
        return plan

    @staticmethod
    def _replace_interpretation_plan(interpretation: Any, plan: Optional[Any]) -> Any:
        if interpretation is None or plan is None:
            return interpretation
        return type(interpretation)(
            query=getattr(interpretation, "query", ""),
            intent_id=getattr(interpretation, "intent_id", None),
            render=dict(getattr(interpretation, "render", None) or {}),
            resolved=dict(getattr(interpretation, "resolved", None) or {}),
            plan=plan,
            error_code=getattr(interpretation, "error_code", None),
            metadata=dict(getattr(interpretation, "metadata", None) or {}),
        )

    def _composition_policy(self) -> str:
        composition = self.query_config.get("composition", {})
        if isinstance(composition, dict):
            policy = composition.get("policy") or composition.get("composition_policy")
            if policy:
                return str(policy).strip().upper()
            if bool(composition.get("allow_partial_results", False)):
                return "ALLOW_PARTIAL"
        policy = self.query_config.get("composition_policy")
        return str(policy or "FAIL_CLOSED").strip().upper()

    def _domain_pack_identity(self) -> str:
        return ":".join(
            item
            for item in (
                str(self.raw.get("pack") or self.raw.get("domain_name") or "").strip(),
                str(self.raw.get("pack_version") or self.raw.get("version") or "").strip(),
            )
            if item
        )
