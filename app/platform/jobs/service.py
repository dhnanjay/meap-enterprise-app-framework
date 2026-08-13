"""Job Service — durable async execution (Sections 32-34).

Large data processing must not depend on the request process surviving.
- Local dev: FastAPI BackgroundTasks (process-level)
- Production: RQ (Redis Queue) for distributed processing

The domain job model must not depend on the transport.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import structlog
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.platform.database.models import Job, JobStatus
from app.settings import get_settings

logger = structlog.get_logger()


class JobService:
    """Manages durable Job records and dispatches work.

    A job must delegate substantive business behavior to services,
    not duplicate business logic (Section 31).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_job(
        self,
        *,
        module: str,
        operation: str,
        created_by: str | None = None,
        correlation_id: str | None = None,
        input_artifact_ids: dict | None = None,
    ) -> Job:
        """Create a QUEUED job record."""
        job = Job(
            module=module,
            operation=operation,
            status=JobStatus.QUEUED,
            created_by=created_by,
            correlation_id=correlation_id,
            input_artifact_ids=input_artifact_ids,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        logger.info(
            "job.created",
            job_id=job.job_id,
            module=module,
            operation=operation,
            correlation_id=correlation_id,
        )
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self.db.get(Job, job_id)

    def update_progress(self, job_id: str, progress: float) -> None:
        job = self.db.get(Job, job_id)
        if job:
            job.progress = progress
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(timezone.utc)
            self.db.commit()

    def mark_running(self, job_id: str) -> None:
        job = self.db.get(Job, job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            self.db.commit()

    def mark_succeeded(
        self, job_id: str, output_artifact_ids: dict | None = None, result_meta: dict | None = None
    ) -> None:
        job = self.db.get(Job, job_id)
        if job:
            job.status = JobStatus.SUCCEEDED
            job.progress = 100.0
            job.finished_at = datetime.now(timezone.utc)
            if output_artifact_ids:
                job.output_artifact_ids = output_artifact_ids
            if result_meta:
                job.result_meta = result_meta
            self.db.commit()
            logger.info("job.succeeded", job_id=job_id)

    def mark_failed(self, job_id: str, error_code: str, error_message: str) -> None:
        job = self.db.get(Job, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.finished_at = datetime.now(timezone.utc)
            job.error_code = error_code
            job.error_message = error_message
            self.db.commit()
            logger.info("job.failed", job_id=job_id, error_code=error_code)

    def dispatch(
        self,
        job_id: str,
        func: Callable[..., Any],
        background_tasks: BackgroundTasks,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Dispatch a job using the appropriate runner.

        - If MEAP_REDIS_URL is set: enqueue to RQ.
        - Otherwise: use FastAPI BackgroundTasks (local dev).
        """
        settings = get_settings()

        if settings.redis_url:
            self._dispatch_rq(job_id, func, *args, **kwargs)
        else:
            self._dispatch_background_tasks(job_id, func, background_tasks, *args, **kwargs)

    def _dispatch_background_tasks(
        self,
        job_id: str,
        func: Callable[..., Any],
        background_tasks: BackgroundTasks,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Local dev runner using FastAPI BackgroundTasks."""

        def _wrapper() -> None:
            try:
                self.mark_running(job_id)
                func(*args, **kwargs)
                self.mark_succeeded(job_id)
            except Exception as e:
                self.mark_failed(job_id, type(e).__name__, str(e))

        background_tasks.add_task(_wrapper)

    def _dispatch_rq(
        self,
        job_id: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Production runner using RQ (Redis Queue)."""
        from rq import Queue  # type: ignore[import-not-found]
        from redis import Redis  # type: ignore[import-not-found]

        settings = get_settings()
        redis_conn = Redis.from_url(settings.redis_url)
        queue = Queue("meap", connection=redis_conn)

        queue.enqueue(
            _rq_wrapper,
            job_id=job_id,
            func=func,
            args=args,
            kwargs=kwargs,
        )


def _rq_wrapper(job_id: str, func: Callable, args: tuple, kwargs: dict) -> Any:
    """RQ worker entry point — updates job status around the function call."""
    from app.platform.database.session import get_session_factory

    db = get_session_factory()()
    service = JobService(db)
    try:
        service.mark_running(job_id)
        result = func(*args, **kwargs)
        service.mark_succeeded(job_id)
        return result
    except Exception as e:
        service.mark_failed(job_id, type(e).__name__, str(e))
        raise
    finally:
        db.close()