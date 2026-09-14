"""Deterministic rendering for the hermetic public reference runtime."""

from __future__ import annotations

from dataclasses import asdict
from enum import Enum
from typing import Any, Dict, Mapping

from .claims import ClaimBundle, ClaimPolarity, ClaimStatus


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _claim_dict(claim: Any) -> Dict[str, Any]:
    payload = asdict(claim)
    return {key: _value(value) for key, value in payload.items()}


class PublicResponseRenderer:
    """Render only claims and evidence already produced by execution."""

    protocol_id = "ia-rag.public-rendering.v1"
    protocol_version = 1

    @staticmethod
    def render(
        bundle: ClaimBundle,
        *,
        receipt: Mapping[str, Any],
        lineage: Mapping[str, Any],
        evidence: Mapping[str, Any],
    ) -> Dict[str, Any]:
        claims = bundle.deduped_sorted()
        known_affirm = [item for item in claims if item.status == ClaimStatus.KNOWN and item.polarity == ClaimPolarity.AFFIRM]
        known_deny = [item for item in claims if item.status == ClaimStatus.KNOWN and item.polarity == ClaimPolarity.DENY]
        unknown = [item for item in claims if item.status == ClaimStatus.UNKNOWN]
        if bundle.ask_clarify or bundle.ambiguity or unknown and not known_affirm:
            answer = "I don't know."
        elif bundle.is_existence_question or bundle.is_boolean_question:
            answer = "Yes." if known_affirm else ("No." if known_deny else "I don't know.")
        elif not claims:
            answer = "No results found."
        else:
            lines = [
                f"{claim.subject} —{claim.predicate.upper()}→ {claim.object}"
                for claim in known_affirm[:25]
            ]
            answer = "Facts:\n- " + "\n- ".join(lines) if lines else "I don't know."
        return {
            "answer": answer,
            "claims": [_claim_dict(item) for item in claims],
            "metadata": {
                "result_type": str(bundle.projection_kind or "TYPED_FACTS"),
                "domain_id": str(bundle.domain_name or ""),
                "execution_receipt": dict(receipt or {}),
                "lineage": dict(lineage or {}),
                "evidence": dict(evidence or {}),
            },
        }


__all__ = ["PublicResponseRenderer"]
