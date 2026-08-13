from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    task_id: str = Field(..., description="Unique Celery task identifier")
    message: str = Field(..., description="Status message regarding document ingestion")
    status: str = Field("processing", description="Current status of the ingestion task")
