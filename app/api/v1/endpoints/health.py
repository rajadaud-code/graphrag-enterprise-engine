import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.neo4j_client import get_neo4j
from app.db.postgres import get_db
from app.db.qdrant_client import get_qdrant
from app.db.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", status_code=status.HTTP_200_OK)
async def check_health(
    db: AsyncSession = Depends(get_db),
    qdrant: AsyncQdrantClient = Depends(get_qdrant),
    neo4j: AsyncDriver = Depends(get_neo4j),
    redis: Redis = Depends(get_redis),
) -> Dict[str, Any]:
    details: Dict[str, str] = {}
    is_healthy = True

    # 1. Check PostgreSQL
    try:
        res = await db.execute(text("SELECT 1"))
        if res.scalar() == 1:
            details["postgres"] = "healthy"
        else:
            details["postgres"] = "unhealthy: unexpected query response"
            is_healthy = False
    except Exception as exc:
        logger.error(f"Postgres health check failed: {exc}")
        details["postgres"] = f"unhealthy: {str(exc)}"
        is_healthy = False

    # 2. Check Qdrant
    try:
        await qdrant.get_collections()
        details["qdrant"] = "healthy"
    except Exception as exc:
        logger.error(f"Qdrant health check failed: {exc}")
        details["qdrant"] = f"unhealthy: {str(exc)}"
        is_healthy = False

    # 3. Check Neo4j
    try:
        await neo4j.verify_connectivity()
        details["neo4j"] = "healthy"
    except Exception as exc:
        logger.error(f"Neo4j health check failed: {exc}")
        details["neo4j"] = f"unhealthy: {str(exc)}"
        is_healthy = False

    # 4. Check Redis
    try:
        ping_res = await redis.ping()
        if ping_res:
            details["redis"] = "healthy"
        else:
            details["redis"] = "unhealthy: ping returned False"
            is_healthy = False
    except Exception as exc:
        logger.error(f"Redis health check failed: {exc}")
        details["redis"] = f"unhealthy: {str(exc)}"
        is_healthy = False

    if not is_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "degraded",
                "details": details,
            },
        )

    return {
        "status": "all systems operational",
        "details": details,
    }
