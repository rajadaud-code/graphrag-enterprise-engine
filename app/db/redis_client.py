import logging
from typing import AsyncGenerator
import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


async def get_redis() -> AsyncGenerator[Redis, None]:
    client: Redis = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    except Exception as exc:
        logger.error(f"Redis client error: {exc}")
        raise
    finally:
        await client.aclose()
