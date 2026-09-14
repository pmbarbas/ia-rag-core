"""Small neutral package surface for IA-RAG canonical contracts.

Optional adapters and historical application surfaces are lazy.  Importing
the package therefore does not require model, database, or extraction
dependencies and does not construct a runtime or assurance provider.
"""

from .domain import (
    Answer, Chunk, Document, EvalItem, EvalResult, GraphEdge, GraphNode,
    GraphResult, HybridSearchConfig, Metadata, Query, ScoredChunk,
)
from .protocols import (
    CompilerRuntime, DocumentStore, EmbeddingProvider, EntityExtractor,
    EntityResolver, GraphIntentHandler, GraphStore, LexicalIndex, LLMProvider,
    PlanGovernance, RelationExtractor, TelemetrySink, VectorIndex,
)
from .assurance_protocols import (
    ASSURANCE_PROTOCOL_ID, ASSURANCE_PROTOCOL_VERSION,
    AssuranceConfigurationError, AssuranceMode, AssuranceProvider,
)
from .claims import Claim, ClaimBundle, ClaimPolarity, ClaimStatus
from .planner_registry import (
    AmbiguousPlannerError, PlannerContext, PlannerRegistration, PlannerRegistry,
    PlannerSelection, PlannerSelectionError, RouteResult, UnsupportedPlannerError,
)
from .canonical_compiler import CanonicalCompileResult, CanonicalCompiler, CanonicalDomainPack
from .canonical_plan import (
    CanonicalExecutionPlan,
    CanonicalLogicalPlan,
    CanonicalPlanType,
    execution_plan_digest,
    logical_plan_digest,
)
from .canonical_execution_admission import CanonicalExecutionAdmission, admit_canonical_execution
from .canonical_execution_enforcement import (
    CanonicalEnforcementDecision,
    CanonicalEnforcementPhase,
    CanonicalEnforcementStatus,
)
from .canonical_execution_receipt import (
    CANONICAL_EXECUTION_RECEIPT_PROTOCOL_ID,
    CANONICAL_EXECUTION_RECEIPT_PROTOCOL_VERSION,
    CanonicalExecutionReceipt,
)
from .canonical_lineage import CanonicalLineageReadModel, lineage_metadata
from .query_router import QueryRouter
from .domain_semantic_extensions import (
    DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_ID,
    DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_VERSION,
    DomainSemanticExtension, DomainSemanticExtensionRegistry,
    SemanticExtensionConfigurationError,
)
from .public_runtime import (
    InMemoryEntityResolver, InMemoryGraphStore, PUBLIC_CANONICAL_PLANNER_TYPE,
    PUBLIC_RUNTIME_PROTOCOL_ID, PUBLIC_RUNTIME_PROTOCOL_VERSION,
    PublicCanonicalRuntime, PublicCompilation, PublicCoreConfigurationError,
    PublicExecutionError, PublicExecutionResult, PublicRuntimeComponents,
    build_canonical_runtime, register_public_canonical_planner,
)
from .public_rendering import PublicResponseRenderer
from .reference_assurance import ReferenceAssuranceProvider
from .reference_domains import (
    EQUIPMENT_NETWORK_DOMAIN, RESEARCH_NETWORK_DOMAIN, closed_world_domain,
    load_reference_domain, load_reference_facts,
)


_LAZY_OPTIONAL_EXPORTS = {
    "StructuralChunker": ("chunking", "StructuralChunker"),
    "GraphRAGCore": ("graph", "GraphRAGCore"),
    "GraphIngestionOrchestrator": ("graph", "GraphIngestionOrchestrator"),
    "ConfigDrivenGraphHandler": ("graph", "ConfigDrivenGraphHandler"),
    "JsonFileGraphStore": ("graph", "JsonFileGraphStore"),
    "JsonFileDocumentStore": ("storage", "JsonFileDocumentStore"),
    "JsonFileVectorIndex": ("storage", "JsonFileVectorIndex"),
    "UniversalExtractionCore": ("universal_extraction", "UniversalExtractionCore"),
    "UniversalLLMEntityExtractor": ("universal_extraction", "UniversalLLMEntityExtractor"),
    "UniversalLLMRelationExtractor": ("universal_extraction", "UniversalLLMRelationExtractor"),
    "load_domain_schema": ("universal_extraction", "load_domain_schema"),
    "UniversalEntityResolver": ("universal_resolver", "UniversalEntityResolver"),
    "UniversalEntityResolverConfig": ("universal_resolver", "UniversalEntityResolverConfig"),
    "InMemoryTelemetrySink": ("telemetry", "InMemoryTelemetrySink"),
    "HybridReasoningLayer": ("hybrid_reasoning", "HybridReasoningLayer"),
    "CrossDomainFederator": ("cross_domain_federation", "CrossDomainFederator"),
    "HybridSearcher": ("search", "HybridSearcher"),
    "IntentClassifier": ("search", "IntentClassifier"),
    "DynamicIntentClassifier": ("search", "DynamicIntentClassifier"),
    "HyDEGenerator": ("search", "HyDEGenerator"),
    "InMemoryLexicalIndex": ("search", "InMemoryLexicalIndex"),
    "LangChainOllamaLLMProvider": ("llm", "LangChainOllamaLLMProvider"),
    "LangChainEmbeddingProvider": ("llm", "LangChainEmbeddingProvider"),
    "DummyLLMProvider": ("llm", "DummyLLMProvider"),
    "MilvusLiteVectorIndex": ("milvus_adapter", "MilvusLiteVectorIndex"),
    "Neo4jGraphStore": ("neo4j_adapter", "Neo4jGraphStore"),
}


def __getattr__(name):
    target = _LAZY_OPTIONAL_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    from importlib import import_module

    try:
        value = getattr(import_module(f"{__name__}.{target[0]}"), target[1])
    except ImportError:  # Optional compatibility surface is unavailable.
        value = None
    globals()[name] = value
    return value


__all__ = [
    "Answer", "Chunk", "Document", "EvalItem", "EvalResult", "GraphEdge", "GraphNode", "GraphResult",
    "HybridSearchConfig", "Metadata", "Query", "ScoredChunk",
    "CompilerRuntime", "DocumentStore", "EmbeddingProvider", "EntityExtractor", "EntityResolver",
    "GraphIntentHandler", "GraphStore", "LexicalIndex", "LLMProvider", "PlanGovernance",
    "RelationExtractor", "TelemetrySink", "VectorIndex",
    "ASSURANCE_PROTOCOL_ID", "ASSURANCE_PROTOCOL_VERSION", "AssuranceConfigurationError",
    "AssuranceMode", "AssuranceProvider",
    "Claim", "ClaimBundle", "ClaimPolarity", "ClaimStatus",
    "AmbiguousPlannerError", "PlannerContext", "PlannerRegistration", "PlannerRegistry",
    "PlannerSelection", "PlannerSelectionError", "RouteResult", "UnsupportedPlannerError", "QueryRouter",
    "CanonicalCompileResult", "CanonicalCompiler", "CanonicalDomainPack",
    "CanonicalExecutionPlan", "CanonicalLogicalPlan", "CanonicalPlanType",
    "execution_plan_digest", "logical_plan_digest", "CanonicalExecutionAdmission",
    "admit_canonical_execution", "CanonicalEnforcementDecision", "CanonicalEnforcementPhase",
    "CanonicalEnforcementStatus", "CANONICAL_EXECUTION_RECEIPT_PROTOCOL_ID",
    "CANONICAL_EXECUTION_RECEIPT_PROTOCOL_VERSION", "CanonicalExecutionReceipt",
    "CanonicalLineageReadModel", "lineage_metadata",
    "DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_ID", "DOMAIN_SEMANTIC_EXTENSION_PROTOCOL_VERSION",
    "DomainSemanticExtension", "DomainSemanticExtensionRegistry", "SemanticExtensionConfigurationError",
    "InMemoryEntityResolver", "InMemoryGraphStore", "PUBLIC_CANONICAL_PLANNER_TYPE",
    "PUBLIC_RUNTIME_PROTOCOL_ID", "PUBLIC_RUNTIME_PROTOCOL_VERSION", "PublicCanonicalRuntime",
    "PublicCompilation", "PublicCoreConfigurationError", "PublicExecutionError", "PublicExecutionResult",
    "PublicRuntimeComponents", "PublicResponseRenderer", "ReferenceAssuranceProvider",
    "build_canonical_runtime", "register_public_canonical_planner",
    "EQUIPMENT_NETWORK_DOMAIN", "RESEARCH_NETWORK_DOMAIN", "closed_world_domain",
    "load_reference_domain", "load_reference_facts",
]


EXPORT_CLASSIFICATION = {
    "PUBLIC_CORE": tuple(__all__),
    "PUBLIC_OPTIONAL_EXTRA": tuple(sorted(_LAZY_OPTIONAL_EXPORTS)),
    "EXCLUDED_APPLICATION_SURFACES": ("historical_compatibility", "application_specific_adapters"),
}
