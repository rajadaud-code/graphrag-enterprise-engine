import logging
import re
import uuid
from pathlib import Path
from typing import Optional
import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.security import get_optional_tenant
from app.models.schemas.auth import TenantContext
from app.models.schemas.ingest import IngestResponse
from app.tasks.document_worker import process_document_task

logger = logging.getLogger(__name__)

router = APIRouter()

DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post(
    "/",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload PDF Document for Asynchronous Multi-Tenant Ingestion",
)
async def ingest_document(
    file: UploadFile = File(...),
    tenant_id: Optional[str] = Form(None, description="Unique Tenant ID for data isolation"),
    auth_tenant: Optional[TenantContext] = Depends(get_optional_tenant),
) -> IngestResponse:
    """Accept PDF document upload and dispatch Celery worker task with tenant data isolation."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename cannot be empty",
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents are supported for ingestion",
        )

    # Determine effective tenant_id
    effective_tenant_id = (
        tenant_id
        or (auth_tenant.tenant_id if auth_tenant else None)
        or settings.default_tenant_id
    ).strip()

    # Sanitize and validate tenant_id
    if not re.match(r"^[a-zA-Z0-9_\-]+$", effective_tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant_id. Must contain only alphanumeric characters, dashes, and underscores.",
        )

    # If both API Key and form tenant_id are present, ensure consistency unless master admin
    if auth_tenant and auth_tenant.tenant_id != "admin_master" and tenant_id:
        if auth_tenant.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Authenticated tenant '{auth_tenant.tenant_id}' cannot ingest on behalf of '{tenant_id}'",
            )

    unique_filename = f"{effective_tenant_id}_{uuid.uuid4().hex}_{file.filename}"
    file_path = DOWNLOAD_DIR / unique_filename

    logger.info(
        f"Saving uploaded file '{file.filename}' asynchronously to '{file_path}' "
        f"for Tenant '{effective_tenant_id}'"
    )

    try:
        async with aiofiles.open(file_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):  # Read in 1MB chunks
                await out_file.write(chunk)
    except Exception as exc:
        logger.error(f"Failed to save uploaded file '{file.filename}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(exc)}",
        )

    # Dispatch Celery background task with tenant_id
    task = process_document_task.delay(str(file_path), file.filename, effective_tenant_id)
    logger.info(f"Dispatched process_document task with task_id: {task.id} (Tenant: {effective_tenant_id})")

    return IngestResponse(
        task_id=task.id,
        tenant_id=effective_tenant_id,
        filename=file.filename,
        message=f"Document '{file.filename}' accepted for background ingestion for tenant '{effective_tenant_id}'",
        status="processing",
    )
