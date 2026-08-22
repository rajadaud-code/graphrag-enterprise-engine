import json
import logging
import math
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.core.config import settings
from app.core.security import get_optional_tenant
from app.db.neo4j_client import get_neo4j
from app.db.qdrant_client import get_qdrant
from app.db.redis_client import get_redis
from app.models.schemas.auth import TenantContext
from app.models.schemas.chat import ChatRequest, ChatResponse
from app.services.embedding_service import generate_embeddings
from app.services.langgraph_agent.checkpointer import RedisSaver
from app.services.langgraph_agent.graph import build_graph
from app.services.langgraph_agent.state import GraphRAGState

logger = logging.getLogger(__name__)

router = APIRouter()

SIMILARITY_THRESHOLD = 0.95


def calculate_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate Cosine Similarity between two 1D float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


async def get_semantic_cache(
    redis_client: Redis,
    tenant_id: str,
    query_vector: List[float],
) -> Optional[Dict[str, Any]]:
    """Query Redis for semantically similar question vectors (> 0.95 Cosine Similarity) isolated by tenant."""
    cache_key = f"grag:semantic_cache:{tenant_id}"
    try:
        raw_items = await redis_client.lrange(cache_key, 0, 100)
        for raw in raw_items:
            data = json.loads(raw)
            cached_answer = data.get("answer", "")

            # Do NOT return cached error messages
            if "Unable to generate" in cached_answer or "service error" in cached_answer.lower():
                continue

            cached_vector = data.get("vector")
            if cached_vector:
                similarity = calculate_cosine_similarity(query_vector, cached_vector)
                if similarity >= SIMILARITY_THRESHOLD:
                    logger.info(
                        f"[Tenant: {tenant_id}] Semantic Cache HIT! Similarity: {similarity:.4f} for query: '{data.get('question')}'"
                    )
                    return data
    except Exception as exc:
        logger.error(f"Error querying Redis semantic cache for tenant '{tenant_id}': {exc}")
    return None


async def save_semantic_cache(
    redis_client: Redis,
    tenant_id: str,
    question: str,
    query_vector: List[float],
    answer: str,
    route_decision: str,
    sources: Dict[str, Any],
) -> None:
    """Store question embedding vector and generated response in tenant-partitioned Redis cache."""
    if not answer or "Unable to generate" in answer or "service error" in answer.lower():
        logger.info(f"Skipping cache storage for error or failed response (Tenant: {tenant_id}).")
        return

    cache_key = f"grag:semantic_cache:{tenant_id}"
    try:
        record = {
            "question": question,
            "vector": query_vector,
            "answer": answer,
            "route_decision": route_decision,
            "sources": sources,
        }
        await redis_client.lpush(cache_key, json.dumps(record))
        await redis_client.ltrim(cache_key, 0, 500)  # Prune to last 500 entries per tenant
    except Exception as exc:
        logger.error(f"Error saving to Redis semantic cache for tenant '{tenant_id}': {exc}")


@router.post(
    "/",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Multi-Tenant Stateful Chat with LangGraph Agentic Hybrid Engine",
)
async def chat_with_agent(
    request: ChatRequest,
    auth_tenant: Optional[TenantContext] = Depends(get_optional_tenant),
    qdrant: AsyncQdrantClient = Depends(get_qdrant),
    neo4j: AsyncDriver = Depends(get_neo4j),
    redis: Redis = Depends(get_redis),
) -> ChatResponse:
    """Process user query with strict multi-tenancy data isolation, persistent Redis session memory, and semantic caching."""
    question = request.question.strip()

    # Determine effective tenant_id
    effective_tenant_id = (
        (auth_tenant.tenant_id if auth_tenant and auth_tenant.tenant_id != "admin_master" else None)
        or request.tenant_id
        or (auth_tenant.tenant_id if auth_tenant else None)
        or settings.default_tenant_id
    ).strip()

    # Enforce tenant isolation if authenticated with non-admin API key
    if auth_tenant and auth_tenant.tenant_id != "admin_master" and request.tenant_id:
        if auth_tenant.tenant_id != request.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API Key belongs to tenant '{auth_tenant.tenant_id}' and cannot query tenant '{request.tenant_id}'",
            )

    logger.info(
        f"Received Chat query for Tenant: '{effective_tenant_id}', Session: '{request.session_id}': '{question}'"
    )

    # Step 1: Embed User Question
    query_vectors = generate_embeddings([question])
    query_vector = query_vectors[0] if query_vectors else []

    # Step 2: Tenant-Scoped Redis Semantic Cache Lookup
    if query_vector:
        cached_entry = await get_semantic_cache(redis, effective_tenant_id, query_vector)
        if cached_entry:
            return ChatResponse(
                tenant_id=effective_tenant_id,
                session_id=request.session_id,
                question=question,
                answer=cached_entry.get("answer", ""),
                cache_hit=True,
                route_decision=cached_entry.get("route_decision", "cache"),
                sources=cached_entry.get("sources", {}),
            )

    logger.info(
        f"[Tenant: {effective_tenant_id}] Semantic Cache MISS. Invoking LangGraph Agentic Search Workflow..."
    )

    # Step 3: Invoke Stateful LangGraph Agentic Workflow with Persistent Redis Saver
    try:
        checkpointer = RedisSaver(redis_client=redis)
        graph_app = build_graph(
            qdrant_client=qdrant,
            neo4j_driver=neo4j,
            checkpointer=checkpointer,
        )

        thread_id = f"{effective_tenant_id}:{request.session_id}"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state: GraphRAGState = {
            "tenant_id": effective_tenant_id,
            "session_id": request.session_id,
            "question": question,
            "route_decision": "hybrid",
            "vector_context": [],
            "graph_context": [],
            "generation": "",
            "retry_count": 0,
            "chat_history": [],
        }

        final_state = await graph_app.ainvoke(initial_state, config=config)

        answer = final_state.get("generation", "No answer could be generated.")
        route_decision = final_state.get("route_decision", "hybrid")
        vector_ctx = final_state.get("vector_context", [])
        graph_ctx = final_state.get("graph_context", [])

        sources = {
            "vector_chunks_count": len(vector_ctx),
            "graph_relations_count": len(graph_ctx),
            "vector_sources": list(set([v.get("filename") for v in vector_ctx if v.get("filename")])),
            "tenant_id": effective_tenant_id,
        }

        # Step 4: Save Valid Result to Tenant Redis Semantic Cache
        if query_vector and answer:
            await save_semantic_cache(
                redis_client=redis,
                tenant_id=effective_tenant_id,
                question=question,
                query_vector=query_vector,
                answer=answer,
                route_decision=route_decision,
                sources=sources,
            )

        return ChatResponse(
            tenant_id=effective_tenant_id,
            session_id=request.session_id,
            question=question,
            answer=answer,
            cache_hit=False,
            route_decision=route_decision,
            sources=sources,
        )

    except Exception as exc:
        logger.error(
            f"Error executing Chat agent workflow for tenant '{effective_tenant_id}': {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat agent processing failed: {str(exc)}",
        )
