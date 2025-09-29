"""Pydantic models for job submission and status tracking."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class JobStatus(str, Enum):
    """Enumeration of possible job lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProgressSnapshot(BaseModel):
    """Represents the incremental progress emitted by workers."""

    percent: int = Field(default=0, ge=0, le=100)
    current_step: Optional[str] = Field(default=None)
    message: Optional[str] = Field(default=None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ConcatInput(BaseModel):
    """Video segment input definition for concatenation."""

    media_id: str = Field(min_length=1)
    start_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional start offset in milliseconds",
    )
    end_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional end offset in milliseconds",
    )

    @model_validator(mode="after")
    def validate_time_range(self) -> "ConcatInput":  # pragma: no cover - defensive
        if self.end_ms is not None and self.start_ms is not None:
            if self.end_ms <= self.start_ms:
                raise ValueError("end_ms must be greater than start_ms")
        return self


class ConcatJobRequest(BaseModel):
    """HTTP payload for concatenation jobs."""

    inputs: list[ConcatInput] = Field(min_length=1)
    audio_track: Optional[str] = Field(default=None, description="Optional audio media ID")
    output_format: str = Field(default="mp4", description="Output container format")
    metadata: dict[str, Any] = Field(default_factory=dict)


class OverlayAsset(BaseModel):
    """Defines an overlay element for a video."""

    media_id: str = Field(min_length=1)
    position_x: int = Field(default=0, ge=0)
    position_y: int = Field(default=0, ge=0)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, ge=0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    scale: Optional[float] = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def validate_duration(self) -> "OverlayAsset":  # pragma: no cover - defensive
        if self.end_ms is not None and self.start_ms is not None:
            if self.end_ms <= self.start_ms:
                raise ValueError("end_ms must be greater than start_ms")
        return self


class OverlayJobRequest(BaseModel):
    """HTTP payload for overlay jobs."""

    input_media_id: str = Field(min_length=1)
    overlays: list[OverlayAsset] = Field(min_length=1)
    output_format: str = Field(default="mp4")
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    """Persisted job metadata tracked by the API and workers."""

    job_id: str
    job_type: Literal["concat", "overlay"]
    params: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = JobStatus.QUEUED
    progress: Optional[ProgressSnapshot] = None
    result_media_id: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class JobCreatedResponse(BaseModel):
    """Response payload when a job is scheduled."""

    job_id: str = Field(alias="jobId")

    model_config = {
        "populate_by_name": True,
    }


class JobStatusResponse(BaseModel):
    """Response payload describing the current status of a job."""

    job_id: str = Field(alias="jobId")
    job_type: str = Field(alias="jobType")
    status: JobStatus
    progress: Optional[ProgressSnapshot] = None
    result_media_id: Optional[str] = Field(default=None, alias="resultMediaId")
    message: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
