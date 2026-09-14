"""Neutral domain value objects shared by canonical IA-RAG contracts."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# --- 1. CORE DOCUMENTS ---
@dataclass
class Metadata:
    doc_type: str
    created_at: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Document:
    doc_id: str
    text: str
    title: str = ""
    raw_uri: str = ""
    metadata: Metadata = field(default_factory=lambda: Metadata("generic"))

@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    metadata: Metadata
    section_path: List[str] = field(default_factory=list)
    token_count: int = 0
    char_start: int = 0
    char_end: int = 0
    index: int = 0

# --- 2. SEARCH OBJECTS ---
@dataclass
class ScoredChunk:
    """
    Wrapper for a Chunk with a search score.
    Used by Retrievers (Vector/Lexical) to return ranked results.
    """
    chunk: Chunk
    score: float
    rank: int = 0

@dataclass
class HybridSearchConfig:
    weight_bm25: float = 0.5
    weight_vector: float = 0.5
    rrf_k: int = 60
    top_k_bm25: int = 10
    top_k_vector: int = 10
    final_top_k: int = 5
    bm25_weight: float = 0.5
    vector_weight: float = 0.5

# --- 3. GRAPH STRUCTURES ---

# STRATEGIC CHOICE: Use String Alias for Node Types.
# This prevents runtime crashes in the Extractor when LLMs output novel types,
# and allows loose coupling between Domain Schema (YAML) and Code.
GraphNodeType = str

@dataclass
class GraphNode:
    node_id: str
    node_type: GraphNodeType
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GraphEdge:
    edge_id: str
    src_id: str
    dst_id: str
    relation: str
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GraphResult:
    """
    Standard result from a Graph Traversal.
    """
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    answer: str = ""  # Default value prevents Orchestrator crashes
    path: List[Any] = field(default_factory=list)
    context_nodes: List[GraphNode] = field(default_factory=list)

# --- 4. QUERY & ANSWER ---
@dataclass
class Query:
    text: str
    query_id: str
    user_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    filters: Optional[Dict[str, Any]] = None

@dataclass
class Answer:
    text: str
    confidence: float = 1.0
    sources: List[Chunk] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class QueryIntent:
    intent_type: str 
    confidence: float = 0.0
    slots: Dict[str, Any] = field(default_factory=dict)

# --- 5. TELEMETRY & EVAL ---
@dataclass
class QueryLogEntry:
    query: Query
    answer: Answer
    latency_seconds: float
    timestamp: float

@dataclass
class EvalItem:
    query: str
    expected_answer: str = ""
    expected_chunks: List[str] = field(default_factory=list)

@dataclass
class EvalResult:
    query_id: str
    precision: float = 0.0
    recall: float = 0.0
    score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
