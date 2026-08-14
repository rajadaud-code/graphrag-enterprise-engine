import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient

from app.db.neo4j_client import get_neo4j
from app.db.qdrant_client import get_qdrant

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Query Qdrant vector counts and Neo4j node/edge counts",
)
async def get_test_data_counts(
    qdrant: AsyncQdrantClient = Depends(get_qdrant),
    neo4j: AsyncDriver = Depends(get_neo4j),
) -> Dict[str, Any]:
    """Retrieve current populated statistics from Qdrant vector store and Neo4j Knowledge Graph."""
    result: Dict[str, Any] = {
        "qdrant": {},
        "neo4j": {},
    }

    # 1. Query Qdrant
    try:
        collection_name = "documents"
        exists = await qdrant.collection_exists(collection_name)
        if exists:
            info = await qdrant.get_collection(collection_name)
            points_cnt = getattr(info, "points_count", 0)
            if points_cnt is None:
                points_cnt = 0

            result["qdrant"] = {
                "collection": collection_name,
                "status": str(info.status),
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
            node_res = await session.run("MATCH (n) RETURN count(n) AS node_count")
            node_record = await node_res.single()
            node_count = node_record["node_count"] if node_record else 0

            rel_res = await session.run("MATCH ()-[r]->() RETURN count(r) AS rel_count")
            rel_record = await rel_res.single()
            rel_count = rel_record["rel_count"] if rel_record else 0

            result["neo4j"] = {
                "nodes_count": node_count,
                "relationships_count": rel_count,
            }
    except Exception as exc:
        logger.error(f"Error querying Neo4j test data: {exc}")
        result["neo4j"] = {"error": str(exc)}

    return result
