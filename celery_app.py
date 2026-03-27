import os
from celery import Celery


CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "sqlalchemy+sqlite:///./ocr_jobs.db")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "db+sqlite:///./ocr_jobs.db")

celery_app = Celery(
    "notary_v2",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=False,
)

# Ensure tasks are registered (Windows-friendly)
import tasks  # noqa: F401
