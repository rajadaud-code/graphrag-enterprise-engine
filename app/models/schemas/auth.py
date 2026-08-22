import datetime
from typing import Optional
from pydantic import BaseModel, Field


class APIKeyCreateRequest(BaseModel):
    tenant_id: str = Field(
        ...,
        min_length=2,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Unique Tenant Identifier (slug alphanumeric with dashes/underscores)",
        examples=["acme_corp", "tenant_001"],
    )
    client_name: str = Field(
        ...,
        min_length=2,
        max_length=128,
        description="Human-readable client/organization name",
        examples=["Acme Corporation"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Optional description or environment tag for this API key",
        examples=["Production Website Chat Widget Key"],
    )


class APIKeyResponse(BaseModel):
    api_key: str = Field(..., description="Generated Secret API Key (Keep secure)")
    tenant_id: str = Field(..., description="Unique Tenant Identifier")
    client_name: str = Field(..., description="Client or organization name")
    description: Optional[str] = Field(None, description="Key description")
    created_at: str = Field(..., description="Timestamp of key generation (ISO 8601)")
    is_active: bool = Field(True, description="Whether the API key is active")


class TenantContext(BaseModel):
    tenant_id: str = Field(..., description="Authenticated Tenant ID")
    client_name: str = Field(..., description="Client or organization name")
    is_active: bool = Field(True, description="Tenant active status")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class APIKeyVerifyResponse(BaseModel):
    valid: bool = Field(..., description="Whether the API key is valid")
    tenant: Optional[TenantContext] = Field(None, description="Resolved Tenant Context")
    message: str = Field(..., description="Validation status message")
