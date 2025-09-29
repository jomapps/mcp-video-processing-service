"""Configuration for the video processing service."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration sourced from environment variables."""

    payload_base_url: Optional[AnyUrl] = Field(
        default=None, description="Base URL of the PayloadCMS API"
    )
    payload_api_token: Optional[str] = Field(
        default=None,
        description="Bearer token for authenticating with PayloadCMS",
    )
    payload_media_collection: str = Field(
        default="media", description="PayloadCMS collection for media assets"
    )

    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string for job metadata",
    )
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker connection string",
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend connection string",
    )
    celery_task_queue: str = Field(
        default="video-processing",
        description="Celery queue for video processing tasks",
    )

    temp_dir: Path = Field(
        default=Path("/tmp/mcp-video-processing"),
        description="Base directory for transient media files",
    )
    ffmpeg_binary: str = Field(default="ffmpeg", description="FFmpeg executable path")
    ffprobe_binary: str = Field(default="ffprobe", description="FFprobe executable path")
    default_output_format: str = Field(
        default="mp4", description="Default output container format"
    )
    default_resolution: str = Field(
        default="1280x720",
        description="Target resolution for generated videos in the form WxH",
    )
    default_crf: int = Field(
        default=21,
        ge=0,
        le=51,
        description="Constant Rate Factor to use for H.264 encoding",
    )

    request_timeout_seconds: float = Field(
        default=30.0,
        description="HTTP timeout when communicating with external services",
    )

    log_level: str = Field(default="INFO", description="Application log level")

    model_config = SettingsConfigDict(env_prefix="VIDEO_", env_file=None, extra="ignore")


settings = Settings()
