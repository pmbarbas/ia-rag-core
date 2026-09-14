"""Neutral claim and claim-bundle contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ClaimPolarity(str, Enum):
    AFFIRM = "affirm"
    DENY = "deny"


class ClaimStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Claim:
    """
    Canonical claim representation.

    subject/predicate/object are strings for stability across domains.
    polarity + status encode open-world semantics:
      - absence => UNKNOWN (not DENY)
      - explicit negation => DENY + provenance evidence
    """
    subject: str
    predicate: str
    object: str

    polarity: ClaimPolarity = ClaimPolarity.AFFIRM
    status: ClaimStatus = ClaimStatus.KNOWN

    confidence: float = 1.0
    provenance: Dict[str, Any] = field(default_factory=dict)
    scope_tags: Tuple[str, ...] = field(default_factory=tuple)

    def key(self) -> Tuple[str, str, str, str, str]:
        return (
            (self.subject or "").strip(),
            (self.predicate or "").strip(),
            (self.object or "").strip(),
            str(self.polarity.value),
            str(self.status.value),
        )


@dataclass
class ClaimBundle:
    """
    A stable answer contract:
      - claims are the only source of truth for rendering
      - machine-readable flags for downstream orchestration
    """
    claims: List[Claim] = field(default_factory=list)

    ask_clarify: bool = False
    ambiguity: bool = False
    ambiguity_reason: Optional[str] = None
    clarify: Dict[str, Any] = field(default_factory=dict)

    is_existence_question: bool = False
    is_boolean_question: bool = False  # For binary relation checks (e.g., "Does X supply Y?")
    closed_world: bool = False

    # Rendering hints
    projection_kind: str = ""
    domain_name: str = ""
    
    # A3/A4: Explicit truth-state from ExecutionResult
    truth_state: Optional[Any] = None

    # Wave 1: authoritative planner-to-execution lineage.
    execution_receipt: Optional[Dict[str, Any]] = None

    # Wave 2: parent composite outcome and explicit unresolved units.
    composite_status: Optional[str] = None
    unresolved_units: List[Dict[str, Any]] = field(default_factory=list)

    def deduped_sorted(self) -> List[Claim]:
        seen = set()
        uniq: List[Claim] = []
        for c in self.claims or []:
            k = c.key()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(c)

        def _sort_key(c: Claim):
            st = 0 if c.status == ClaimStatus.KNOWN else 1
            pol = 0 if c.polarity == ClaimPolarity.AFFIRM else 1
            return (st, pol, c.predicate, c.subject, c.object)

        uniq.sort(key=_sort_key)
        return uniq
