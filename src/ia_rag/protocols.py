"""Neutral storage, retrieval, extraction, and runtime protocols."""

from __future__ import annotations
from typing import Protocol, List, Dict, Any, Iterable, Optional, runtime_checkable

# STRICT IMPORT from Master Domain
from .domain import (
    Document,
    Chunk,
    ScoredChunk,
    Query,
    Answer,
    GraphResult,
    GraphNode,
    QueryLogEntry,
    EvalResult,
    EvalItem,
)

class DocumentStore(Protocol):
    def upsert_documents(self, documents: Iterable[Document]) -> None: ...
    def get_document(self, doc_id: str) -> Optional[Document]: ...
    def upsert_chunks(self, chunks: Iterable[Chunk]) -> None: ...
    def get_chunk(self, chunk_id: str) -> Optional[Chunk]: ...
    def iter_chunks(self, filters: Dict[str, Any]) -> Iterable[Chunk]: ...


class VectorIndex(Protocol):
    def index_chunks(self, items: Iterable[tuple[Chunk, List[float]]]) -> None: ...
    def search(self, query_vector: List[float], filters: Dict[str, Any], k: int) -> List[ScoredChunk]: ...


class LexicalIndex(Protocol):
    def index_chunks(self, chunks: Iterable[Chunk]) -> None: ...
    def search(self, query: str, k: int, filters: Optional[Dict[str, Any]] = None) -> List[ScoredChunk]: ...


class GraphStore(Protocol):
    """
    Pre-Wave A Contract:
    --------------------
    GraphStore implementations are FACT PROVIDERS, not semantic executors.

    Responsibilities:
    - Persist graph nodes and edges
    - Return raw graph facts via query()
    - Provide backend-specific storage optimization

    NOT Responsibilities:
    - Determine semantic traversal meaning
    - Apply fallback direction flipping
    - Execute semantic rescue behavior
    - Return backend-specific semantic shortcuts that change answer meaning

    The selected application runtime is the sole authority for semantic
    execution and must operate over normalized graph facts.
    """
    def upsert_nodes(self, nodes: Iterable[GraphNode]) -> None: ...
    def upsert_edges(self, edges: Iterable[Any]) -> None: ...
    def query(self, query_spec: Dict[str, Any]) -> GraphResult: ...
    @property
    def nodes(self) -> Dict[str, GraphNode]: ...
    @property
    def edges(self) -> List[Any]: ...


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: List[str]) -> List[List[float]]: ...


class TelemetrySink(Protocol):
    def log_query(self, query: Query, answer: Answer, latency: float) -> None: ...


class GraphIntentHandler(Protocol):
    def can_handle(self, query: Query) -> bool: ...
    def build_query_spec(self, query: Query) -> Dict[str, Any]: ...
    def summarize(self, result: GraphResult) -> Dict[str, Any]: ...
    # Optional semantic-satisfaction hook for compatible providers.
    def is_satisfied(self, result: GraphResult) -> bool: ...


class EntityExtractor(Protocol):
    def extract(self, chunk: Chunk) -> List[GraphNode]: ...


class RelationExtractor(Protocol):
    def extract(self, chunk: Chunk, entities: List[GraphNode]) -> List[Any]: ...


class EntityResolver(Protocol):
    def resolve(self, text: str, type_hint: str, context: Dict[str, Any]) -> Optional[GraphNode]: ...


# =============================================================================
# Runtime protocols (optional, additive)
# =============================================================================

@runtime_checkable
class CompilerRuntime(Protocol):
    """
    Application runtime wrapper.
    """
    def answer(self, legacy_orchestrator: Any, user_id: str, query_text: str) -> Dict[str, Any]: ...


@runtime_checkable
class PlanGovernance(Protocol):
    """
    Governance gate for plan execution.
    """
    def decide(
        self,
        *,
        question_text: str,
        candidate_plans: List[Any],
        selected_plan: Optional[Any],
        ambiguity: bool = False,
        ambiguity_reason: Optional[str] = None,
    ) -> Any: ...
