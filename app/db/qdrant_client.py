import logging
from typing import AsyncGenerator
from qdrant_client import AsyncQdrantClient

from app.core.config import settings

logger = logging.getLogger(__name__)


async def get_qdrant() -> AsyncGenerator[AsyncQdrantClient, None]:
    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    try:
        yield client
    except Exception as exc:
        logger.error(f"Qdrant client error: {exc}")
        raise
    finally:
        await client.close()
