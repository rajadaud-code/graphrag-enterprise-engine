import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Security, status
from redis.asyncio import Redis

from app.core.security import (
    api_key_header,
    api_key_query,
    generate_api_key,
    get_current_tenant,
    resolve_api_key,
    store_api_key,
    verify_admin_access,
)
from app.db.redis_client import get_redis
from app.models.schemas.auth import (
    APIKeyCreateRequest,
    APIKeyResponse,
    APIKeyVerifyResponse,
    TenantContext,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/api-keys",
    response_model=APIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a New API Key for a Tenant",
)
async def create_tenant_api_key(
    request: APIKeyCreateRequest,
    admin: TenantContext = Depends(verify_admin_access),
    redis: Redis = Depends(get_redis),
) -> APIKeyResponse:
    """Provision a new unique API key tied to a specific tenant_id.
    
    In development mode or when authenticated with the Master Admin Key,
    this generates a cryptographically secure key and registers it in Redis.
    """
    logger.info(f"Admin '{admin.tenant_id}' creating API key for tenant: '{request.tenant_id}' ({request.client_name})")

    api_key = generate_api_key(request.tenant_id)
    tenant_context = await store_api_key(
        redis_client=redis,
        api_key=api_key,
        tenant_id=request.tenant_id,
        client_name=request.client_name,
        description=request.description,
        is_active=True,
    )

    return APIKeyResponse(
        api_key=api_key,
        tenant_id=tenant_context.tenant_id,
        client_name=tenant_context.client_name,
        description=request.description,
        created_at=tenant_context.created_at or "",
        is_active=tenant_context.is_active,
    )


@router.get(
    "/verify",
    response_model=APIKeyVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify an API Key and Retrieve Tenant Context",
)
async def verify_api_key(
    tenant: TenantContext = Depends(get_current_tenant),
) -> APIKeyVerifyResponse:
    """Verify that an API key is active and return the associated tenant information."""
    return APIKeyVerifyResponse(
        valid=True,
        tenant=tenant,
        message=f"API Key is valid and authenticated for tenant '{tenant.tenant_id}' ({tenant.client_name})",
    )
