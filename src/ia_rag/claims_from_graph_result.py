"""Neutral graph-evidence to claim projection."""

from __future__ import annotations
from typing import Any, Dict, Optional

from .claims import Claim, ClaimBundle, ClaimPolarity, ClaimStatus
from .domain import GraphResult


def build_claim_bundle_from_graph_result(
    *,
    graph_result: GraphResult,
    domain_name: str,
    projection_kind: str = "TYPED_FACTS",
    is_existence_question: bool = False,
    closed_world: bool = False,
    # Optional boolean proof context (only set when caller knows it's a bool question)
    bool_context: Optional[Dict[str, Any]] = None,
    # Step 3: Pass exists_node_id from plan features to confirm anchor was resolved
    exists_node_id: Optional[str] = None,
) -> ClaimBundle:
    """
    Deterministic adapter: GraphResult -> ClaimBundle

    - Does NOT infer Yes/No.
    - If bool_context is provided, caller should already have validated proof elsewhere
      OR will keep UNKNOWN unless proof was found.
    
    Step 3 Fix: Exists check returns "Yes" when anchor resolved
    - If is_existence_question=True and exists_node_id is provided, we create
      an AFFIRM claim even if graph_result is empty, because the anchor was
      successfully resolved by the entity linker.
    """
    bundle = ClaimBundle(
        claims=[],
        projection_kind=(projection_kind or "TYPED_FACTS").strip().upper(),
        domain_name=(domain_name or "").strip(),
        is_existence_question=bool(is_existence_question),
        closed_world=bool(closed_world),
    )

    nodes = getattr(graph_result, "nodes", None) or []
    edges = getattr(graph_result, "edges", None) or []
    
    # Step 3: If exists question and anchor was resolved, create AFFIRM claim
    # This ensures "Does X exist?" returns "Yes" when X is found, even if
    # the graph traversal returns no results
    if is_existence_question and exists_node_id:
        # Check if we have the node in results
        found_node = None
        for n in nodes:
            if str(getattr(n, "node_id", "")) == exists_node_id:
                found_node = n
                break
        
        # If node found OR anchor was resolved (exists_node_id provided),
        # create an AFFIRM claim
        if found_node or exists_node_id:
            node_to_use = found_node if found_node else None
            nid = exists_node_id
            nt = "ENTITY"
            nm = nid
            
            if node_to_use:
                nt = str(getattr(node_to_use, "node_type", "") or "ENTITY").upper()
                p = getattr(node_to_use, "properties", None) or {}
                nm = p.get("name") or p.get("id") or nid
            
            bundle.claims.append(
                Claim(
                    subject=str(nm).strip() or nid,
                    predicate="EXISTS",
                    object=nt,
                    polarity=ClaimPolarity.AFFIRM,
                    status=ClaimStatus.KNOWN,
                    confidence=1.0,
                    provenance={"exists_node_id": nid},
                    scope_tags=(f"domain:{bundle.domain_name}",),
                )
            )
            return bundle

    # node index for nice names
    node_by_id: Dict[str, Any] = {}
    for n in nodes:
        nid = str(getattr(n, "node_id", "") or "")
        if nid:
            node_by_id[nid] = n

    def _name(n: Any, fallback: str) -> str:
        if n is None:
            return fallback
        p = getattr(n, "properties", None) or {}
        nm = p.get("name") or p.get("id") or getattr(n, "node_id", None) or fallback
        return str(nm).strip() or fallback

    # If NODE_ONLY-style: create IS_A claims from nodes
    if not edges and nodes:
        for n in nodes[:25]:
            nid = str(getattr(n, "node_id", "") or "")
            nt = str(getattr(n, "node_type", "") or (getattr(n, "properties", {}) or {}).get("type") or "ENTITY").upper()
            nm = _name(n, nid or "node")

            bundle.claims.append(
                Claim(
                    subject=nm,
                    predicate="IS_A",
                    object=nt,
                    polarity=ClaimPolarity.AFFIRM,
                    status=ClaimStatus.KNOWN,
                    confidence=1.0,
                    provenance=dict(getattr(n, "properties", None) or {}),
                    scope_tags=(f"domain:{bundle.domain_name}",),
                )
            )
        return bundle

    # Regular edges -> claims
    for e in edges[:250]:  # deterministic cap
        src_id = str(getattr(e, "src_id", "") or "")
        dst_id = str(getattr(e, "dst_id", "") or "")
        rel = str(getattr(e, "relation", "") or "RELATED_TO").strip().upper()

        src_n = node_by_id.get(src_id)
        dst_n = node_by_id.get(dst_id)

        src = _name(src_n, src_id or "src")
        dst = _name(dst_n, dst_id or "dst")

        bundle.claims.append(
            Claim(
                subject=src,
                predicate=rel,
                object=dst,
                polarity=ClaimPolarity.AFFIRM,
                status=ClaimStatus.KNOWN,
                confidence=1.0,
                provenance=dict(getattr(e, "properties", None) or {}),
                scope_tags=(f"domain:{bundle.domain_name}",),
            )
        )

    return bundle
