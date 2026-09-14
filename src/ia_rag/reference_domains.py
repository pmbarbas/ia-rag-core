"""Synthetic, non-production reference domains for the public core."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping


RESEARCH_NETWORK_DOMAIN: Dict[str, Any] = {
    "domain_name": "research_network",
    "pack_version": "1.0",
    "entities": ["PROJECT", "RESEARCHER", "LAB", "DATASET"],
    "relations": [
        {"type": "MEMBER_OF", "source": "RESEARCHER", "target": "LAB", "aliases": ["member of"]},
        {"type": "CONTRIBUTED_TO", "source": "RESEARCHER", "target": "PROJECT", "aliases": ["contributed to"]},
        {"type": "PRODUCED", "source": "PROJECT", "target": "DATASET", "aliases": ["produced"]},
    ],
    "capabilities": ["ENTITY_LOOKUP", "RELATION_LOOKUP", "BOOLEAN_CHECK", "EXISTENCE_CHECK", "COMPOSITION"],
    "world_model": {"mode": "OPEN_WORLD"},
    "governance": {"max_hops": 2, "max_results": 25, "cardinality_cap_per_hop": 25},
    "query": {
        "router": {"planner": "reference.research_network.v1"},
        "semantic_programs": [
            {
                "program_id": "research.datasets_from_contributor",
                "patterns": ["Which datasets were produced by projects contributed to by <RESEARCHER>"],
                "anchor_type": "RESEARCHER",
                "steps": [
                    {"relation": "CONTRIBUTED_TO", "direction": "OUT", "source_type": "RESEARCHER", "target_type": "PROJECT"},
                    {"relation": "PRODUCED", "direction": "OUT", "source_type": "PROJECT", "target_type": "DATASET"},
                ],
                "projection": "TYPED_FACTS",
                "metadata": {"required_subgraph": "research_contribution_path"},
            },
            {
                "program_id": "research.labs_for_researcher",
                "patterns": ["Which labs is <RESEARCHER> member of"],
                "anchor_type": "RESEARCHER",
                "steps": [{"relation": "MEMBER_OF", "direction": "OUT", "source_type": "RESEARCHER", "target_type": "LAB"}],
                "projection": "TYPED_FACTS",
            },
            {
                "program_id": "research.researcher_contributes",
                "patterns": ["Does <RESEARCHER> contribute"],
                "anchor_type": "RESEARCHER",
                "steps": [{"relation": "CONTRIBUTED_TO", "direction": "OUT", "source_type": "RESEARCHER", "target_type": "PROJECT"}],
                "projection": "TYPED_FACTS",
                "plan_type": "BOOLEAN_CHECK",
            },
        ],
    },
}


EQUIPMENT_NETWORK_DOMAIN: Dict[str, Any] = {
    "domain_name": "equipment_network",
    "pack_version": "1.0",
    "entities": ["DEVICE", "FACILITY", "COMPONENT", "MAINTENANCE_RECORD"],
    "relations": [
        {"type": "LOCATED_AT", "source": "DEVICE", "target": "FACILITY", "aliases": ["located at"]},
        {"type": "CONTAINS", "source": "FACILITY", "target": "COMPONENT", "aliases": ["contains"]},
        {"type": "SERVICED_BY", "source": "COMPONENT", "target": "MAINTENANCE_RECORD", "aliases": ["serviced by"]},
    ],
    "capabilities": ["ENTITY_LOOKUP", "RELATION_LOOKUP", "BOOLEAN_CHECK", "EXISTENCE_CHECK", "COMPOSITION"],
    "world_model": {"mode": "OPEN_WORLD"},
    "governance": {"max_hops": 2, "max_results": 25, "cardinality_cap_per_hop": 25},
    "query": {
        "router": {"planner": "reference.equipment_network.v1"},
        "semantic_programs": [
            {
                "program_id": "equipment.components_at_device_facility",
                "patterns": ["Which components are contained by facilities located at <DEVICE>"],
                "anchor_type": "DEVICE",
                "steps": [
                    {"relation": "LOCATED_AT", "direction": "OUT", "source_type": "DEVICE", "target_type": "FACILITY"},
                    {"relation": "CONTAINS", "direction": "OUT", "source_type": "FACILITY", "target_type": "COMPONENT"},
                ],
                "projection": "TYPED_FACTS",
                "metadata": {"required_subgraph": "equipment_location_path"},
            },
        ],
    },
}


def closed_world_domain(domain: Mapping[str, Any]) -> Dict[str, Any]:
    """Return an explicit complete-scope variant of a synthetic domain."""

    result = deepcopy(dict(domain))
    result["world_model"] = {
        "mode": "CLOSED_WORLD",
        "scope": f"{result['domain_name']}.reference.graph",
        "completeness": "EXHAUSTIVE",
    }
    return result


REFERENCE_FACTS: Dict[str, Dict[str, Any]] = {
    "research_network": {
        "nodes": [
            {"node_id": "researcher-alice", "node_type": "RESEARCHER", "properties": {"name": "Alice"}},
            {"node_id": "researcher-bob", "node_type": "RESEARCHER", "properties": {"name": "Bob"}},
            {"node_id": "project-atlas", "node_type": "PROJECT", "properties": {"name": "Atlas"}},
            {"node_id": "project-beacon", "node_type": "PROJECT", "properties": {"name": "Beacon"}},
            {"node_id": "lab-north", "node_type": "LAB", "properties": {"name": "North Lab"}},
            {"node_id": "dataset-atlas-1", "node_type": "DATASET", "properties": {"name": "Atlas Dataset"}},
        ],
        "edges": [
            {"edge_id": "edge-alice-atlas", "src_id": "researcher-alice", "dst_id": "project-atlas", "relation": "CONTRIBUTED_TO", "properties": {"source_ref": "synthetic:record:1"}},
            {"edge_id": "edge-atlas-dataset", "src_id": "project-atlas", "dst_id": "dataset-atlas-1", "relation": "PRODUCED", "properties": {"source_ref": "synthetic:record:2"}},
            {"edge_id": "edge-alice-lab", "src_id": "researcher-alice", "dst_id": "lab-north", "relation": "MEMBER_OF", "properties": {"source_ref": "synthetic:record:3"}},
        ],
    },
    "equipment_network": {
        "nodes": [
            {"node_id": "device-one", "node_type": "DEVICE", "properties": {"name": "Device One"}},
            {"node_id": "facility-east", "node_type": "FACILITY", "properties": {"name": "East Facility"}},
            {"node_id": "component-pump", "node_type": "COMPONENT", "properties": {"name": "Pump"}},
            {"node_id": "maintenance-1", "node_type": "MAINTENANCE_RECORD", "properties": {"name": "Maintenance One"}},
        ],
        "edges": [
            {"edge_id": "edge-device-facility", "src_id": "device-one", "dst_id": "facility-east", "relation": "LOCATED_AT", "properties": {"source_ref": "synthetic:record:4"}},
            {"edge_id": "edge-facility-component", "src_id": "facility-east", "dst_id": "component-pump", "relation": "CONTAINS", "properties": {"source_ref": "synthetic:record:5"}},
            {"edge_id": "edge-component-maintenance", "src_id": "component-pump", "dst_id": "maintenance-1", "relation": "SERVICED_BY", "properties": {"source_ref": "synthetic:record:6"}},
        ],
    },
}


def load_reference_domain(name: str) -> Dict[str, Any]:
    """Load a synthetic domain from package code, without filesystem paths."""

    key = str(name or "").strip()
    domains = {
        "research_network": RESEARCH_NETWORK_DOMAIN,
        "equipment_network": EQUIPMENT_NETWORK_DOMAIN,
    }
    try:
        return deepcopy(domains[key])
    except KeyError as exc:
        raise KeyError(f"reference_domain_not_found:{key}") from exc


def load_reference_facts(name: str) -> Dict[str, Any]:
    key = str(name or "").strip()
    try:
        return deepcopy(REFERENCE_FACTS[key])
    except KeyError as exc:
        raise KeyError(f"reference_facts_not_found:{key}") from exc


__all__ = [
    "EQUIPMENT_NETWORK_DOMAIN",
    "REFERENCE_FACTS",
    "RESEARCH_NETWORK_DOMAIN",
    "closed_world_domain",
    "load_reference_domain",
    "load_reference_facts",
]
