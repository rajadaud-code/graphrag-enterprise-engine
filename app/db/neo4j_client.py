import logging
from typing import AsyncGenerator
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)


async def get_neo4j() -> AsyncGenerator[AsyncDriver, None]:
    driver: AsyncDriver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        yield driver
    except Exception as exc:
        logger.error(f"Neo4j driver error: {exc}")
        raise
    finally:
        await driver.close()
