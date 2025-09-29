"""Job persistence abstractions for API and worker usage."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Optional

import redis
from redis.asyncio import Redis as AsyncRedis

from .job_models import JobRecord, JobStatus, ProgressSnapshot


class JobStoreError(RuntimeError):
    """Raised when job persistence operations fail."""


class AbstractJobStore:
    """Common interface for job metadata storage."""

    async def create_job(self, record: JobRecord) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def get_job(self, job_id: str) -> Optional[JobRecord]:  # pragma: no cover - interface
        raise NotImplementedError

    async def update_job(
        self,
        job_id: str,
        *,
        status: Optional[JobStatus] = None,
        progress: Optional[ProgressSnapshot] = None,
        result_media_id: Optional[str] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[JobRecord]:  # pragma: no cover - interface
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover - interface
        """Release any allocated resources."""
        return None


class InMemoryJobStore(AbstractJobStore):
    """Simple asyncio-safe in-memory store used for testing and local dev."""

    def __init__(self) -> None:
        self._records: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, record: JobRecord) -> None:
        async with self._lock:
            self._records[record.job_id] = record

    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        async with self._lock:
            record = self._records.get(job_id)
            return record.model_copy(deep=True) if record else None

    async def update_job(
        self,
        job_id: str,
        *,
        status: Optional[JobStatus] = None,
        progress: Optional[ProgressSnapshot] = None,
        result_media_id: Optional[str] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[JobRecord]:
        async with self._lock:
            record = self._records.get(job_id)
            if not record:
                return None

            update_data: dict[str, Any] = {
                "updated_at": datetime.utcnow(),
            }
            if status is not None:
                update_data["status"] = status
            if progress is not None:
                update_data["progress"] = progress
            if result_media_id is not None:
                update_data["result_media_id"] = result_media_id
            if message is not None:
                update_data["message"] = message
            if error is not None:
                update_data["error"] = error
            if metadata is not None:
                merged = {**record.metadata, **metadata}
                update_data["metadata"] = merged

            new_record = record.model_copy(update=update_data)
            self._records[job_id] = new_record
            return new_record.model_copy(deep=True)

    async def close(self) -> None:
        self._records.clear()


def _job_key(job_id: str) -> str:
    return f"video-job:{job_id}"


class RedisJobStore(AbstractJobStore):
    """Redis-backed store for use by the FastAPI service."""

    def __init__(self, redis_url: str) -> None:
        self._redis = AsyncRedis.from_url(redis_url, decode_responses=True)

    async def create_job(self, record: JobRecord) -> None:
        payload = record.model_dump(mode="json")
        payload_json = json.dumps(payload, default=str)
        await self._redis.set(_job_key(record.job_id), payload_json)

    async def get_job(self, job_id: str) -> Optional[JobRecord]:
        raw = await self._redis.get(_job_key(job_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return JobRecord.model_validate(data)

    async def update_job(
        self,
        job_id: str,
        *,
        status: Optional[JobStatus] = None,
        progress: Optional[ProgressSnapshot] = None,
        result_media_id: Optional[str] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[JobRecord]:
        async with self._redis.pipeline() as pipe:
            key = _job_key(job_id)
            await pipe.get(key)
            result = await pipe.execute()
        raw = result[0]
        if raw is None:
            return None

        data = json.loads(raw)
        record = JobRecord.model_validate(data)

        update_data: dict[str, Any] = {
            "updated_at": datetime.utcnow(),
        }
        if status is not None:
            update_data["status"] = status
        if progress is not None:
            update_data["progress"] = progress
        if result_media_id is not None:
            update_data["result_media_id"] = result_media_id
        if message is not None:
            update_data["message"] = message
        if error is not None:
            update_data["error"] = error
        if metadata is not None:
            merged = {**record.metadata, **metadata}
            update_data["metadata"] = merged

        updated = record.model_copy(update=update_data)
        await self._redis.set(key, json.dumps(updated.model_dump(mode="json"), default=str))
        return updated

    async def close(self) -> None:
        await self._redis.close()
        await self._redis.connection_pool.disconnect()


class RedisJobStoreSync:
    """Synchronous Redis store variant for use by Celery workers."""

    def __init__(self, redis_url: str) -> None:
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)

    def create_job(self, record: JobRecord) -> None:
        payload = json.dumps(record.model_dump(mode="json"), default=str)
        self._redis.set(_job_key(record.job_id), payload)

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        raw = self._redis.get(_job_key(job_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return JobRecord.model_validate(data)

    def update_job(
        self,
        job_id: str,
        *,
        status: Optional[JobStatus] = None,
        progress: Optional[ProgressSnapshot] = None,
        result_media_id: Optional[str] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[JobRecord]:
        pipe = self._redis.pipeline()
        key = _job_key(job_id)
        pipe.get(key)
        raw = pipe.execute()[0]
        if raw is None:
            return None
        record = JobRecord.model_validate(json.loads(raw))

        update_data: dict[str, Any] = {
            "updated_at": datetime.utcnow(),
        }
        if status is not None:
            update_data["status"] = status
        if progress is not None:
            update_data["progress"] = progress
        if result_media_id is not None:
            update_data["result_media_id"] = result_media_id
        if message is not None:
            update_data["message"] = message
        if error is not None:
            update_data["error"] = error
        if metadata is not None:
            merged = {**record.metadata, **metadata}
            update_data["metadata"] = merged

        updated = record.model_copy(update=update_data)
        self._redis.set(key, json.dumps(updated.model_dump(mode="json"), default=str))
        return updated


JobStoreFactory = Callable[[], RedisJobStoreSync]
