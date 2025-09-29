"""HTTP API routes for the video processing service."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..job_models import (
    ConcatJobRequest,
    JobCreatedResponse,
    JobRecord,
    JobStatusResponse,
    JobStatus,
    OverlayJobRequest,
)
from ..job_store import AbstractJobStore
from ..tasks import enqueue_concat_job, enqueue_overlay_job


router = APIRouter()


def get_job_store(request: Request) -> AbstractJobStore:
    job_store = getattr(request.app.state, "job_store", None)
    if job_store is None:
        raise RuntimeError("Job store not configured")
    return job_store


@router.get("/health", tags=["health"])
async def healthcheck() -> dict[str, bool]:
    """Liveness probe endpoint."""

    return {"ok": True}


@router.post("/jobs/concat", response_model=JobCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_concat_job(
    request_body: ConcatJobRequest,
    job_store: AbstractJobStore = Depends(get_job_store),
) -> JobCreatedResponse:
    """Schedule a concatenation job."""

    job_id = uuid4().hex
    record = JobRecord(
        job_id=job_id,
        job_type="concat",
        params=request_body.model_dump(mode="json"),
        metadata=request_body.metadata,
        status=JobStatus.QUEUED,
    )
    await job_store.create_job(record)
    enqueue_concat_job(job_id, request_body.model_dump(mode="json"))
    return JobCreatedResponse(jobId=job_id)


@router.post("/jobs/overlay", response_model=JobCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_overlay_job(
    request_body: OverlayJobRequest,
    job_store: AbstractJobStore = Depends(get_job_store),
) -> JobCreatedResponse:
    """Schedule an overlay rendering job."""

    job_id = uuid4().hex
    record = JobRecord(
        job_id=job_id,
        job_type="overlay",
        params=request_body.model_dump(mode="json"),
        metadata=request_body.metadata,
        status=JobStatus.QUEUED,
    )
    await job_store.create_job(record)
    enqueue_overlay_job(job_id, request_body.model_dump(mode="json"))
    return JobCreatedResponse(jobId=job_id)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    job_store: AbstractJobStore = Depends(get_job_store),
) -> JobStatusResponse:
    """Fetch the status of a previously scheduled job."""

    record = await job_store.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return JobStatusResponse(
        jobId=record.job_id,
        jobType=record.job_type,
        status=record.status,
        progress=record.progress,
        resultMediaId=record.result_media_id,
        message=record.message,
        error=record.error,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
        metadata=record.metadata,
    )
