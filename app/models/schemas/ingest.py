from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    task_id: str = Field(..., description="Unique Celery task identifier")
    tenant_id: str = Field(..., description="Tenant ID associated with this document ingestion")
    filename: str = Field(..., description="Uploaded document filename")
    message: str = Field(..., description="Status message regarding document ingestion")
    status: str = Field("processing", description="Current status of the ingestion task")
