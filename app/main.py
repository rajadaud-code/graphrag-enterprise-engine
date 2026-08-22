import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.security import store_api_key

# Configure structured logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for initialization and cleanup."""
    logger.info(f"Starting {settings.project_name} in '{settings.environment}' mode...")
    
    # Initialize default development API key in Redis if available
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        if settings.default_dev_api_key:
            await store_api_key(
                redis_client=redis_client,
                api_key=settings.default_dev_api_key,
                tenant_id=settings.default_tenant_id,
                client_name="Default Local Tenant",
                description="Default seeded API key for local development and widget testing",
                is_active=True,
            )
            logger.info(f"Registered default dev API key in Redis for tenant '{settings.default_tenant_id}'.")
        await redis_client.aclose()
    except Exception as exc:
        logger.warning(f"Could not seed default dev key in Redis during startup: {exc}")

    yield

    logger.info(f"Shutting down {settings.project_name}...")


app = FastAPI(
    title=settings.project_name,
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# SaaS Embeddable Widget CORS: Permissive origin policy allowing client websites to embed the widget
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permissive for embeddable chat widgets across client domains
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 router
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": f"Welcome to {settings.project_name} (Multi-Tenant SaaS Edition)",
        "docs": "/docs",
        "health": "/api/v1/health",
        "auth": "/api/v1/auth/verify",
    }
