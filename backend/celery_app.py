"""
Celery application configuration for PatentRAG.

Defines the Celery app instance used for async query processing.
Uses Redis as both the message broker and result backend.
"""
from celery import Celery
from backend.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

app = Celery(
    "patentrag",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

# Optional Celery configuration
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)