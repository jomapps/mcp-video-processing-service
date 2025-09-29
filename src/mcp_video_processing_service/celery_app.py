"""Celery application factory for video processing tasks."""

from __future__ import annotations

from celery import Celery

from .config import settings


def create_celery() -> Celery:
    """Instantiate and configure the Celery app."""

    app = Celery("mcp_video_processing_service")
    app.conf.update(
        broker_url=settings.celery_broker_url,
        result_backend=settings.celery_result_backend,
        task_default_queue=settings.celery_task_queue,
        task_acks_late=True,
        worker_max_tasks_per_child=50,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    return app


celery_app = create_celery()
