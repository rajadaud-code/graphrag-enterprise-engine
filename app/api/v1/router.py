from fastapi import APIRouter

from app.api.v1.endpoints import chat, health, ingest, test_db

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(ingest.router, prefix="/ingest", tags=["ingestion"])
api_router.include_router(test_db.router, prefix="/test-data", tags=["test-data"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
