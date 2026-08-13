import logging
import ssl
from celery import Celery
from app.core.config import settings

logger = logging.getLogger(__name__)

redis_url = settings.redis_url

# Configure SSL options if connection uses rediss:// scheme
broker_use_ssl = None
redis_backend_use_ssl = None

if redis_url.startswith("rediss://"):
    logger.info("Configuring Celery SSL for secure Redis connection (rediss://)")
    ssl_opts = {"ssl_cert_reqs": ssl.CERT_NONE}
    broker_use_ssl = ssl_opts
    redis_backend_use_ssl = ssl_opts

celery_app = Celery(
    "graphrag_tasks",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_use_ssl=broker_use_ssl,
    redis_backend_use_ssl=redis_backend_use_ssl,
    imports=("app.tasks.document_worker",),
)
