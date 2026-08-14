import json
import logging
import math
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.db.neo4j_client import get_neo4j
from app.db.qdrant_client import get_qdrant
from app.db.redis_client import get_redis
from app.models.schemas.chat import ChatRequest, ChatResponse
from app.services.embedding_service import generate_embeddings
from app.services.langgraph_agent.graph import build_graph

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_KEY = "semantic_cache_records"
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
    query_vector: List[float],
) -> Optional[Dict[str, Any]]:
    """Query Redis for semantically similar question vectors (> 0.95 Cosine Similarity)."""
    try:
        raw_items = await redis_client.lrange(CACHE_KEY, 0, 100)
        for raw in raw_items:
            data = json.loads(raw)
            cached_vector = data.get("vector")
            if cached_vector:
                similarity = calculate_cosine_similarity(query_vector, cached_vector)
                if similarity >= SIMILARITY_THRESHOLD:
                    logger.info(
                        f"Semantic Cache HIT! Similarity: {similarity:.4f} for cached question: '{data.get('question')}'"
                    )
                    return data
    except Exception as exc:
        logger.error(f"Error querying Redis semantic cache: {exc}")
    return None


async def save_semantic_cache(
    redis_client: Redis,
    question: str,
    query_vector: List[float],
    answer: str,
    route_decision: str,
    sources: Dict[str, Any],
) -> None:
    """Store question embedding vector and generated response in Redis."""
    try:
        record = {
            "question": question,
            "vector": query_vector,
            "answer": answer,
            "route_decision": route_decision,
            "sources": sources,
        }
        await redis_client.lpush(CACHE_KEY, json.dumps(record))
        await redis_client.ltrim(CACHE_KEY, 0, 500)  # Prune to last 500 entries
    except Exception as exc:
        logger.error(f"Error saving to Redis semantic cache: {exc}")


@router.post(
    "/",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with Stateful LangGraph Agentic Hybrid Search Engine",
)
async def chat_with_agent(
    request: ChatRequest,
    qdrant: AsyncQdrantClient = Depends(get_qdrant),
    neo4j: AsyncDriver = Depends(get_neo4j),
    redis: Redis = Depends(get_redis),
) -> ChatResponse:
    """Process user question via Redis Semantic Caching or LangGraph Hybrid Retrieval & Synthesis."""
    question = request.question.strip()
    logger.info(f"Received Chat query: '{question}'")

    # Step 1: Embed User Question
    query_vectors = generate_embeddings([question])
    query_vector = query_vectors[0] if query_vectors else []

    # Step 2: Redis Semantic Cache Lookup
    if query_vector:
        cached_entry = await get_semantic_cache(redis, query_vector)
        if cached_entry:
            return ChatResponse(
                question=question,
                answer=cached_entry.get("answer", ""),
                cache_hit=True,
                route_decision=cached_entry.get("route_decision", "cache"),
                sources=cached_entry.get("sources", {}),
            )

    logger.info("Semantic Cache MISS. Invoking LangGraph Agentic Search Workflow...")

    # Step 3: Invoke LangGraph Agentic Workflow
    try:
        graph_app = build_graph(qdrant_client=qdrant, neo4j_driver=neo4j)
        initial_state: GraphRAGState = {
            "question": question,
            "route_decision": "hybrid",
            "vector_context": [],
            "graph_context": [],
            "generation": "",
            "retry_count": 0,
        }

        final_state = await graph_app.ainvoke(initial_state)

        answer = final_state.get("generation", "No answer could be generated.")
        route_decision = final_state.get("route_decision", "hybrid")
        vector_ctx = final_state.get("vector_context", [])
        graph_ctx = final_state.get("graph_context", [])

        sources = {
            "vector_chunks_count": len(vector_ctx),
            "graph_relations_count": len(graph_ctx),
            "vector_sources": [v.get("filename") for v in vector_ctx],
        }

        # Step 4: Save Result to Redis Semantic Cache
        if query_vector and answer:
            await save_semantic_cache(
                redis_client=redis,
                question=question,
                query_vector=query_vector,
                answer=answer,
                route_decision=route_decision,
                sources=sources,
            )

        return ChatResponse(
            question=question,
            answer=answer,
            cache_hit=False,
            route_decision=route_decision,
            sources=sources,
        )

    except Exception as exc:
        logger.error(f"Error executing Chat agent workflow: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat agent processing failed: {str(exc)}",
        )
