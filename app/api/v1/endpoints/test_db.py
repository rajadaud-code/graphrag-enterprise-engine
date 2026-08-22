import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.db.neo4j_client import get_neo4j
from app.db.qdrant_client import get_qdrant

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Query Qdrant vector counts and Neo4j node/edge counts (optional tenant filter)",
)
async def get_test_data_counts(
    tenant_id: Optional[str] = Query(None, description="Optional tenant_id to filter statistics"),
    qdrant: AsyncQdrantClient = Depends(get_qdrant),
    neo4j: AsyncDriver = Depends(get_neo4j),
) -> Dict[str, Any]:
    """Retrieve current populated statistics from Qdrant vector store and Neo4j Knowledge Graph."""
    result: Dict[str, Any] = {
        "tenant_id": tenant_id or "all",
        "qdrant": {},
        "neo4j": {},
    }

    # 1. Query Qdrant
    try:
        collection_name = "documents"
        exists = await qdrant.collection_exists(collection_name)
        if exists:
            if tenant_id:
                count_res = await qdrant.count(
                    collection_name=collection_name,
                    count_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="tenant_id",
                                match=models.MatchValue(value=tenant_id),
                            )
                        ]
                    ),
                )
                points_cnt = count_res.count
            else:
                info = await qdrant.get_collection(collection_name)
                points_cnt = getattr(info, "points_count", 0) or 0

            result["qdrant"] = {
                "collection": collection_name,
                "tenant_filter": tenant_id or "none",
                "points_count": points_cnt,
            }
        else:
            result["qdrant"] = {
                "collection": collection_name,
                "status": "not_created",
                "points_count": 0,
            }
    except Exception as exc:
        logger.error(f"Error querying Qdrant test data: {exc}")
        result["qdrant"] = {"error": str(exc)}

    # 2. Query Neo4j
    try:
        async with neo4j.session() as session:
            if tenant_id:
                node_query = "MATCH (n {tenant_id: $tenant_id}) RETURN count(n) AS node_count"
                rel_query = "MATCH ()-[r {tenant_id: $tenant_id}]->() RETURN count(r) AS rel_count"
                params = {"tenant_id": tenant_id}
            else:
                node_query = "MATCH (n) RETURN count(n) AS node_count"
                rel_query = "MATCH ()-[r]->() RETURN count(r) AS rel_count"
                params = {}

            node_res = await session.run(node_query, **params)
            node_record = await node_res.single()
            node_count = node_record["node_count"] if node_record else 0

            rel_res = await session.run(rel_query, **params)
            rel_record = await rel_res.single()
            rel_count = rel_record["rel_count"] if rel_record else 0

            result["neo4j"] = {
                "tenant_filter": tenant_id or "none",
                "nodes_count": node_count,
                "relationships_count": rel_count,
            }
    except Exception as exc:
        logger.error(f"Error querying Neo4j test data: {exc}")
        result["neo4j"] = {"error": str(exc)}

    return result
