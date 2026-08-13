import logging
import uuid
from pathlib import Path
import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile, status

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
    summary="Upload PDF Document for Asynchronous Ingestion",
)
async def ingest_document(file: UploadFile = File(...)) -> IngestResponse:
    """Accept PDF document upload and dispatch Celery worker task non-blockingly."""
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

    unique_filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = DOWNLOAD_DIR / unique_filename

    logger.info(f"Saving uploaded file '{file.filename}' asynchronously to '{file_path}'")

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

    # Dispatch Celery background task
    task = process_document_task.delay(str(file_path), file.filename)
    logger.info(f"Dispatched process_document task with task_id: {task.id}")

    return IngestResponse(
        task_id=task.id,
        message=f"Document '{file.filename}' accepted for background ingestion",
        status="processing",
    )
