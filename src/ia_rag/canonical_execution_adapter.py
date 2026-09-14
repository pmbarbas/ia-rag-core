"""Native production adapter for admitted canonical execution plans.

This module is deliberately independent of the historical ``QueryPlan`` and
``ExecutionEngine``.  It consumes one already-admitted
``CanonicalExecutionPlan`` and reads only neutral graph facts after the caller
has passed assurance and pre-execution enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .canonical_execution_enforcement import (
    CanonicalAggregationEvidence,
    CanonicalEvidenceEdge,
    CanonicalEvidenceEnvelope,
    CanonicalEvidenceNode,
    CanonicalTypedFact,
)
from .canonical_plan import (
    CanonicalExecutionPlan,
    CanonicalPlanType,
    execution_plan_digest,
)
from .canonical_semantic_contract import semantic_fingerprint
from .domain import GraphEdge, GraphNode, GraphResult


class CanonicalExecutionAdapterError(RuntimeError):
    """A native adapter cannot represent or execute the exact plan."""


@dataclass(frozen=True)
class CanonicalGraphRow:
    node_id: str
    node_type: str
    display_name: str
    path_node_ids: Tuple[str, ...] = ()
    path_edge_ids: Tuple[str, ...] = ()
    relation: str = ""
    properties: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.display_name,
            "display_name": self.display_name,
            "path_node_ids": list(self.path_node_ids),
            "path_edge_ids": list(self.path_edge_ids),
            "relation": self.relation,
            **dict(self.properties or {}),
        }


@dataclass(frozen=True)
class CanonicalProductionExecutionResult:
    executable_plan_digest: str
    rows: Tuple[CanonicalGraphRow, ...]
    evidence: CanonicalEvidenceEnvelope
    graph_result: GraphResult
    result_reference: str
    evidence_reference: str
    aggregation: Optional[Mapping[str, Any]] = None
    child_results: Mapping[str, "CanonicalProductionExecutionResult"] = field(default_factory=dict)

    @property
    def returned_result_count(self) -> int:
        return int(self.evidence.returned_result_count)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rows": [row.to_dict() for row in self.rows],
            "count": self.returned_result_count,
            "aggregation": dict(self.aggregation or {}),
            "result_reference": self.result_reference,
            "evidence_reference": self.evidence_reference,
            "executable_plan_digest": self.executable_plan_digest,
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(getattr(value, "value", value)).upper()


def _properties(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return dict(getattr(value, "properties", None) or {})


def _node(value: Any, fallback_id: str = "") -> Optional[GraphNode]:
    if isinstance(value, GraphNode):
        return value
    if isinstance(value, Mapping):
        node_id = _text(value.get("node_id") or value.get("id") or fallback_id)
        node_type = _text(value.get("node_type") or value.get("type"))
        props = dict(value.get("properties") or {})
    else:
        node_id = _text(getattr(value, "node_id", None) or getattr(value, "id", None) or fallback_id)
        node_type = _text(getattr(value, "node_type", None) or getattr(value, "type", None))
        props = _properties(value)
    if not node_id or not node_type:
        return None
    return GraphNode(node_id=node_id, node_type=node_type, properties=props)


def _edge(value: Any, fallback_id: str = "") -> Optional[GraphEdge]:
    if isinstance(value, GraphEdge):
        return value
    if isinstance(value, Mapping):
        edge_id = _text(value.get("edge_id") or value.get("id") or fallback_id)
        src_id = _text(value.get("src_id") or value.get("source_id") or value.get("source"))
        dst_id = _text(value.get("dst_id") or value.get("target_id") or value.get("target"))
        relation = _text(value.get("relation") or value.get("relation_type"))
        props = dict(value.get("properties") or {})
    else:
        edge_id = _text(getattr(value, "edge_id", None) or getattr(value, "id", None) or fallback_id)
        src_id = _text(getattr(value, "src_id", None) or getattr(value, "source_id", None))
        dst_id = _text(getattr(value, "dst_id", None) or getattr(value, "target_id", None))
        relation = _text(getattr(value, "relation", None) or getattr(value, "relation_type", None))
        props = _properties(value)
    if not edge_id:
        edge_id = semantic_fingerprint({"source": src_id, "target": dst_id, "relation": relation})
    if not src_id or not dst_id or not relation:
        return None
    return GraphEdge(edge_id=edge_id, src_id=src_id, dst_id=dst_id, relation=relation, properties=props)


def _provenance(properties: Mapping[str, Any], fallback: str = "") -> Tuple[str, ...]:
    refs: List[str] = []
    for key in (
        "provenance_references",
        "provenance",
        "evidence_ref",
        "evidence_id",
        "source_ref",
        "source_id",
        "source_doc_ids",
        "source_chunk_ids",
    ):
        value = properties.get(key)
        if isinstance(value, (list, tuple, set)):
            refs.extend(_text(item) for item in value)
        elif value is not None:
            refs.append(_text(value))
    if fallback and not refs:
        refs.append(fallback)
    return tuple(sorted({item for item in refs if item}))


@dataclass(frozen=True)
class _Path:
    node_ids: Tuple[str, ...]
    edge_ids: Tuple[str, ...]


class CanonicalProductionAdapter:
    """Execute exact canonical plans over neutral graph-store primitives."""

    protocol_id = "ia-rag.canonical-production-adapter.v1"
    protocol_version = 1

    def __init__(self, graph_store: Any, *, supported_capabilities: Sequence[str] = ()) -> None:
        self.graph_store = graph_store
        self.supported_capabilities = tuple(sorted({_upper(item) for item in supported_capabilities if _text(item)}))

    def _snapshot(self) -> Tuple[Dict[str, GraphNode], Tuple[GraphEdge, ...]]:
        raw_nodes = getattr(self.graph_store, "nodes", {})
        if isinstance(raw_nodes, Mapping):
            nodes = {
                key: item
                for key, value in raw_nodes.items()
                if (item := _node(value, str(key))) is not None
            }
        else:
            nodes = {}
            for value in raw_nodes or ():
                item = _node(value)
                if item is not None:
                    nodes[item.node_id] = item
        raw_edges = getattr(self.graph_store, "edges", ())
        edges = tuple(item for index, value in enumerate(raw_edges or ()) if (item := _edge(value, f"edge:{index}")) is not None)
        return nodes, edges

    @staticmethod
    def _display(node: GraphNode) -> str:
        props = node.properties or {}
        return _text(props.get("name") or props.get("display_name") or props.get("label") or node.node_id) or node.node_id

    def execute(
        self,
        plan: CanonicalExecutionPlan,
        *,
        pre_execution_allowed: bool,
        execution_instance_reference: str,
    ) -> CanonicalProductionExecutionResult:
        if type(plan) is not CanonicalExecutionPlan:
            raise CanonicalExecutionAdapterError("canonical_execution_plan_required")
        if not pre_execution_allowed:
            raise CanonicalExecutionAdapterError("pre_execution_admission_required")
        if not _text(execution_instance_reference):
            raise CanonicalExecutionAdapterError("execution_instance_reference_required")

        unsupported = [
            _upper(use.capability_id)
            for use in tuple(plan.capability_use or ())
            if _upper(use.capability_id) not in self.supported_capabilities
        ]
        if unsupported:
            raise CanonicalExecutionAdapterError("unsupported_capability:" + ",".join(sorted(set(unsupported))))

        nodes, edges = self._snapshot()
        return self._execute_plan(plan, nodes, edges, execution_instance_reference)

    def _execute_plan(
        self,
        plan: CanonicalExecutionPlan,
        nodes: Mapping[str, GraphNode],
        edges: Sequence[GraphEdge],
        execution_instance_reference: str,
    ) -> CanonicalProductionExecutionResult:
        if plan.plan_type == CanonicalPlanType.COMPOSITE:
            children = {
                unit.unit_id: self._execute_plan(unit.execution_plan, nodes, edges, f"{execution_instance_reference}:{unit.unit_id}")
                for unit in plan.composition_units
            }
            rows = tuple(row for child in children.values() for row in child.rows)
            evidence = CanonicalEvidenceEnvelope(
                nodes=tuple(sorted({node for child in children.values() for node in child.evidence.nodes}, key=lambda item: item.node_id)),
                edges=tuple(sorted({edge for child in children.values() for edge in child.evidence.edges}, key=lambda item: (item.hop_index, item.edge_id or ""))),
                typed_facts=tuple(fact for child in children.values() for fact in child.evidence.typed_facts),
                provenance_references=tuple(sorted({ref for child in children.values() for ref in child.evidence.provenance_references})),
                returned_result_count=len(rows),
                per_hop_cardinality={
                    hop: sum(child.evidence.per_hop_cardinality.get(hop, 0) for child in children.values())
                    for hop in sorted({hop for child in children.values() for hop in child.evidence.per_hop_cardinality})
                },
                child_evidence={unit_id: child.evidence for unit_id, child in children.items()},
            )
            graph_result = self._graph_result(evidence, nodes, edges)
            return self._result(plan, rows, evidence, graph_result, children)

        anchor = plan.anchors[0]
        if anchor.node_id not in nodes:
            paths: List[_Path] = []
        else:
            anchor_node = nodes[anchor.node_id]
            if _upper(anchor_node.node_type) != _upper(anchor.node_type):
                raise CanonicalExecutionAdapterError("anchor_type_mismatch")
            paths = [_Path((anchor.node_id,), ())]

        for hop_index, step in enumerate(plan.steps, start=1):
            next_paths: List[_Path] = []
            for path in paths:
                current_id = path.node_ids[-1]
                current = nodes.get(current_id)
                if current is None:
                    continue
                for edge in edges:
                    if _upper(edge.relation) != _upper(step.relation):
                        continue
                    if _upper(step.direction) == "OUT":
                        if edge.src_id != current_id or edge.dst_id not in nodes:
                            continue
                        next_id = edge.dst_id
                        if _upper(current.node_type) != _upper(step.source_type):
                            raise CanonicalExecutionAdapterError("step_source_type_mismatch")
                        if _upper(nodes[next_id].node_type) != _upper(step.target_type):
                            continue
                    elif _upper(step.direction) == "IN":
                        if edge.dst_id != current_id or edge.src_id not in nodes:
                            continue
                        next_id = edge.src_id
                        if _upper(current.node_type) != _upper(step.target_type):
                            raise CanonicalExecutionAdapterError("step_target_type_mismatch")
                        if _upper(nodes[next_id].node_type) != _upper(step.source_type):
                            continue
                    else:
                        raise CanonicalExecutionAdapterError("relation_direction_unsupported")
                    next_paths.append(_Path(path.node_ids + (next_id,), path.edge_ids + (edge.edge_id,)))
            if len(next_paths) > int(plan.bounds.cardinality_cap_per_hop):
                raise CanonicalExecutionAdapterError("cardinality_cap_exceeded")
            paths = next_paths

        limit = int(plan.bounds.max_results)
        paths = paths[:limit]
        evidence_nodes = {
            node_id: nodes[node_id]
            for path in paths
            for node_id in path.node_ids
            if node_id in nodes
        }
        evidence_edges = {edge.edge_id: edge for edge in edges if any(edge.edge_id in path.edge_ids for path in paths)}
        evidence = self._evidence(plan, paths, evidence_nodes.values(), evidence_edges, nodes)
        rows = tuple(
            CanonicalGraphRow(
                node_id=path.node_ids[-1],
                node_type=nodes[path.node_ids[-1]].node_type,
                display_name=self._display(nodes[path.node_ids[-1]]),
                path_node_ids=path.node_ids,
                path_edge_ids=path.edge_ids,
                relation=(plan.steps[-1].relation if plan.steps else ""),
                properties=nodes[path.node_ids[-1]].properties,
            )
            for path in paths
        )
        aggregation = self._aggregation(plan, rows)
        graph_result = self._graph_result(evidence, nodes, edges)
        return self._result(plan, rows, evidence, graph_result, {}, aggregation=aggregation)

    def _evidence(
        self,
        plan: CanonicalExecutionPlan,
        paths: Sequence[_Path],
        nodes: Iterable[GraphNode],
        edges: Mapping[str, GraphEdge],
        all_nodes: Mapping[str, GraphNode],
    ) -> CanonicalEvidenceEnvelope:
        ev_nodes = tuple(
            CanonicalEvidenceNode(node.node_id, node.node_type)
            for node in sorted(nodes, key=lambda item: item.node_id)
        )
        ev_edges: List[CanonicalEvidenceEdge] = []
        hop_counts: Dict[int, int] = {}
        refs = set()
        for path in paths:
            for hop, edge_id in enumerate(path.edge_ids, start=1):
                edge = edges.get(edge_id)
                if edge is None:
                    continue
                ev_edges.append(
                    CanonicalEvidenceEdge(
                        source_id=edge.src_id,
                        target_id=edge.dst_id,
                        relation=edge.relation,
                        direction=plan.steps[hop - 1].direction,
                        hop_index=hop,
                        edge_id=edge.edge_id,
                    )
                )
                hop_counts[hop] = hop_counts.get(hop, 0) + 1
                refs.update(_provenance(edge.properties, edge.edge_id))
        for node in nodes:
            refs.update(_provenance(node.properties, node.node_id))
        facts = tuple(
            CanonicalTypedFact(
                subject_id=edge.source_id,
                predicate=edge.relation,
                object_value=edge.target_id,
                provenance_references=_provenance(edges[edge.edge_id].properties, edge.edge_id) if edge.edge_id in edges else (),
            )
            for edge in ev_edges
        )
        return CanonicalEvidenceEnvelope(
            nodes=ev_nodes,
            edges=tuple(ev_edges),
            typed_facts=facts,
            provenance_references=tuple(sorted(refs)),
            returned_result_count=len(paths),
            per_hop_cardinality=hop_counts,
        )

    @staticmethod
    def _aggregation(plan: CanonicalExecutionPlan, rows: Sequence[CanonicalGraphRow]) -> Optional[Mapping[str, Any]]:
        aggregation = plan.aggregation
        if aggregation is None:
            return None
        operation = _upper(aggregation.operation)
        if operation == "COUNT":
            return {"operation": operation, "value": len(rows)}
        if operation in {"TOP_N", "LATEST"}:
            date_keys = tuple(aggregation.date_keys or ())
            if not date_keys:
                raise CanonicalExecutionAdapterError("aggregation_date_key_missing")
            ranked = sorted(
                rows,
                key=lambda row: _text(next((row.properties.get(key) for key in date_keys if row.properties.get(key) is not None), "")),
                reverse=True,
            )
            selected = ranked[: int(aggregation.top_n or 1)] if operation == "TOP_N" else ranked[:1]
            return {
                "operation": operation,
                "value": selected[0].display_name if operation == "LATEST" and selected else [row.to_dict() for row in selected],
                "count": len(selected),
            }
        raise CanonicalExecutionAdapterError(f"aggregation_unsupported:{operation}")

    @staticmethod
    def _graph_result(evidence: CanonicalEvidenceEnvelope, nodes: Mapping[str, GraphNode], edges: Sequence[GraphEdge]) -> GraphResult:
        node_ids = {item.node_id for item in evidence.nodes}
        edge_ids = {item.edge_id for item in evidence.edges if item.edge_id}
        return GraphResult(
            nodes=[nodes[node_id] for node_id in sorted(node_ids) if node_id in nodes],
            edges=[edge for edge in edges if edge.edge_id in edge_ids],
        )

    @staticmethod
    def _result(
        plan: CanonicalExecutionPlan,
        rows: Sequence[CanonicalGraphRow],
        evidence: CanonicalEvidenceEnvelope,
        graph_result: GraphResult,
        children: Mapping[str, "CanonicalProductionExecutionResult"],
        *,
        aggregation: Optional[Mapping[str, Any]] = None,
    ) -> CanonicalProductionExecutionResult:
        digest = execution_plan_digest(plan)
        result_reference = semantic_fingerprint({"plan": digest, "rows": [row.to_dict() for row in rows], "aggregation": aggregation})
        evidence_reference = semantic_fingerprint({"plan": digest, "evidence": evidence})
        return CanonicalProductionExecutionResult(
            executable_plan_digest=digest,
            rows=tuple(rows),
            evidence=evidence,
            graph_result=graph_result,
            result_reference=result_reference,
            evidence_reference=evidence_reference,
            aggregation=aggregation,
            child_results=dict(children),
        )


__all__ = [
    "CanonicalExecutionAdapterError",
    "CanonicalGraphRow",
    "CanonicalProductionExecutionResult",
    "CanonicalProductionAdapter",
]
