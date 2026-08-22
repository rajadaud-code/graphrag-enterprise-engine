import datetime
import hashlib
import json
import logging
import secrets
from typing import Optional
from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery
import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import settings
from app.db.redis_client import get_redis
from app.models.schemas.auth import TenantContext

logger = logging.getLogger(__name__)

# FastAPI Security Schemes (Header: X-API-Key or Query Param: api_key for easy widget embedding)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

API_KEY_PREFIX = "grag:apikey:"
TENANT_KEYS_PREFIX = "grag:tenant_keys:"


def generate_api_key(tenant_id: str) -> str:
    """Generate a cryptographically secure random API key for a tenant."""
    random_bytes = secrets.token_hex(20)
    return f"grag_live_{random_bytes}"


async def store_api_key(
    redis_client: Redis,
    api_key: str,
    tenant_id: str,
    client_name: str,
    description: Optional[str] = None,
    is_active: bool = True,
) -> TenantContext:
    """Store tenant API key record in Redis."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = {
        "tenant_id": tenant_id,
        "client_name": client_name,
        "description": description or "",
        "created_at": now_iso,
        "is_active": is_active,
    }
    key_name = f"{API_KEY_PREFIX}{api_key}"
    await redis_client.set(key_name, json.dumps(record))
    await redis_client.sadd(f"{TENANT_KEYS_PREFIX}{tenant_id}", api_key)
    logger.info(f"Stored API key for tenant '{tenant_id}' ({client_name}) in Redis.")
    return TenantContext(
        tenant_id=tenant_id,
        client_name=client_name,
        is_active=is_active,
        created_at=now_iso,
    )


async def resolve_api_key(
    api_key: str,
    redis_client: Redis,
) -> Optional[TenantContext]:
    """Validate and resolve an API key to its TenantContext."""
    if not api_key:
        return None

    # Check 1: Master Admin Key
    if settings.master_admin_key and api_key == settings.master_admin_key:
        return TenantContext(
            tenant_id="admin_master",
            client_name="Master Administrator",
            is_active=True,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    # Check 2: Default Dev Key
    if settings.default_dev_api_key and api_key == settings.default_dev_api_key:
        return TenantContext(
            tenant_id=settings.default_tenant_id,
            client_name="Default Local Tenant",
            is_active=True,
            created_at="2026-01-01T00:00:00Z",
        )

    # Check 3: Lookup in Redis
    try:
        raw = await redis_client.get(f"{API_KEY_PREFIX}{api_key}")
        if raw:
            data = json.loads(raw)
            if data.get("is_active", True):
                return TenantContext(
                    tenant_id=data.get("tenant_id", ""),
                    client_name=data.get("client_name", ""),
                    is_active=data.get("is_active", True),
                    created_at=data.get("created_at"),
                )
            else:
                logger.warning(f"API key for tenant '{data.get('tenant_id')}' is deactivated.")
                return None
    except Exception as exc:
        logger.error(f"Error resolving API key from Redis: {exc}")

    return None


async def get_current_tenant(
    key_from_header: Optional[str] = Security(api_key_header),
    key_from_query: Optional[str] = Security(api_key_query),
    redis_client: Redis = Depends(get_redis),
) -> TenantContext:
    """FastAPI Dependency enforcing and resolving API key authentication.
    
    Accepts API key via 'X-API-Key' HTTP header or '?api_key=' URL query parameter.
    """
    api_key = key_from_header or key_from_query

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Please provide 'X-API-Key' header or '?api_key=' query parameter.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    tenant_context = await resolve_api_key(api_key, redis_client)
    if not tenant_context:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or deactivated API Key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return tenant_context


async def get_optional_tenant(
    key_from_header: Optional[str] = Security(api_key_header),
    key_from_query: Optional[str] = Security(api_key_query),
    redis_client: Redis = Depends(get_redis),
) -> Optional[TenantContext]:
    """Optional tenant authentication (returns None if no key provided, validates if provided)."""
    api_key = key_from_header or key_from_query
    if not api_key:
        return None
    return await resolve_api_key(api_key, redis_client)


async def verify_admin_access(
    key_from_header: Optional[str] = Security(api_key_header),
    key_from_query: Optional[str] = Security(api_key_query),
    redis_client: Redis = Depends(get_redis),
) -> TenantContext:
    """Dependency verifying master admin access for provisioning new tenant API keys."""
    api_key = key_from_header or key_from_query
    
    # In development mode, allow key generation with default dev key or master key
    if not api_key:
        if settings.environment == "development":
            return TenantContext(
                tenant_id="dev_admin",
                client_name="Development Admin",
                is_active=True,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin access requires 'X-API-Key' header with master admin key.",
        )

    tenant = await resolve_api_key(api_key, redis_client)
    if tenant and (tenant.tenant_id == "admin_master" or settings.environment == "development"):
        return tenant

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions. Master admin API key required.",
    )
