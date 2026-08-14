import logging
from typing import AsyncGenerator
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_sanitized_neo4j_uri(uri: str) -> str:
    """Sanitize Neo4j URI for cloud instance SSL certificates (neo4j+s -> neo4j+ssc)."""
    if uri.startswith("neo4j+s://"):
        return uri.replace("neo4j+s://", "neo4j+ssc://", 1)
    if uri.startswith("bolt+s://"):
        return uri.replace("bolt+s://", "bolt+ssc://", 1)
    return uri


async def get_neo4j() -> AsyncGenerator[AsyncDriver, None]:
    neo4j_uri = get_sanitized_neo4j_uri(settings.neo4j_uri)
    driver: AsyncDriver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        yield driver
    except Exception as exc:
        logger.error(f"Neo4j driver error: {exc}")
        raise
    finally:
        await driver.close()
