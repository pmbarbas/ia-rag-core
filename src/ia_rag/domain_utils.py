"""
Domain schema normalization utilities.

Provides a single source of truth for domain_name normalization across
ingestion and query pipelines.
"""

import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def normalize_domain_schema(
    schema: Optional[Dict[str, Any]],
    *,
    context: str = "unknown",
    allow_default: bool = False,  # A2: Changed default to False (fail fast)
) -> Dict[str, Any]:
    """
    Normalize domain schema dict to ensure domain_name key exists.
    
    DomainSchema.model_dump() returns {"name": "X"} but GraphEngine expects
    {"domain_name": "X"}. This function provides non-mutating normalization.
    
    A2: Domain must be explicit. Fails fast if domain_name is missing unless
    allow_default=True is explicitly set.
    
    Args:
        schema: Raw schema dict (may have "name" or "domain_name" or both)
        context: Caller context for debug logging (e.g., "GraphIngestionOrchestrator")
        allow_default: If True, allows fallback to "default" (for backward compat).
                      If False (default), raises ValueError when domain_name is missing.
    
    Returns:
        Normalized schema dict with domain_name key
    
    Raises:
        ValueError: If allow_default=False and domain_name is missing or empty
    """
    # Non-mutating copy
    base = dict(schema or {})
    
    # Check for name/domain_name mismatch (potential wiring bug)
    if "name" in base and "domain_name" in base:
        name_val = str(base["name"]).strip()
        domain_val = str(base["domain_name"]).strip()
        if name_val and domain_val and name_val != domain_val:
            if os.getenv("IA_RAG_DEBUG_DOMAIN"):
                logger.warning(
                    "[DOMAIN][%s] Schema has both 'name' and 'domain_name' with different values: "
                    "name='%s', domain_name='%s'. Using domain_name (policy: domain_name wins).",
                    context, name_val, domain_val
                )
    
    # Normalize: ensure domain_name key exists
    if "domain_name" not in base and "name" in base:
        base["domain_name"] = base["name"]
    
    # A2: Extract domain_name - NO DEFAULT FALLBACK unless explicitly allowed
    domain_name = str(base.get("domain_name") or "").strip()
    
    # A2: Fail fast if domain_name is missing (unless allow_default=True)
    if not domain_name:
        if allow_default:
            # Backward compatibility: allow explicit opt-in to "default"
            domain_name = "default"
            if os.getenv("IA_RAG_DEBUG_DOMAIN"):
                logger.warning(
                    "[DOMAIN][%s] domain_name is missing, falling back to 'default' "
                    "(allow_default=True). Schema keys: %s",
                    context, list(base.keys())
                )
        else:
            # A2: Fail fast - domain is required
            raise ValueError(
                f"[DOMAIN][{context}] domain_name is required but was not provided. "
                f"Schema keys: {list(base.keys())}. "
                f"Provide 'domain_name' or 'name' in schema, or set allow_default=True "
                f"to explicitly allow 'default' fallback."
            )
    
    # Store normalized domain_name back in base
    base["domain_name"] = domain_name
    
    return base

# Made with Bob
