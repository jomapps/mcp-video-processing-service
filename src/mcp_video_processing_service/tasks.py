"""Celery task implementations for video processing operations."""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from celery import Task

from .celery_app import celery_app
from .config import settings
from .ffmpeg.command_builder import (
    build_concat_command,
    build_overlay_command,
    build_overlay_filter,
    generate_concat_filelist,
)
from .ffmpeg.probe import probe_streams, summarize_media
from .ffmpeg.runner import FFmpegExecutionError, execute_ffmpeg
from .job_models import JobRecord, JobStatus, ProgressSnapshot
from .job_store import JobStoreFactory, RedisJobStoreSync
from .payload_client import MediaAsset, PayloadMediaClient

logger = logging.getLogger(__name__)


JobStoreProvider = Callable[[], RedisJobStoreSync]
PayloadClientProvider = Callable[[], PayloadMediaClient]

_job_store_provider: Optional[JobStoreProvider] = None
_payload_client_provider: Optional[PayloadClientProvider] = None


def set_job_store_provider(provider: JobStoreProvider) -> None:
    """Override the job store provider (used during testing)."""

    global _job_store_provider
    _job_store_provider = provider


def set_payload_client_provider(provider: PayloadClientProvider) -> None:
    """Override the PayloadCMS client provider (used during testing)."""

    global _payload_client_provider
    _payload_client_provider = provider


def _get_job_store() -> RedisJobStoreSync:
    if _job_store_provider:
        return _job_store_provider()
    return RedisJobStoreSync(settings.redis_url)


def _get_payload_client() -> PayloadMediaClient:
    if _payload_client_provider:
        return _payload_client_provider()
    if not settings.payload_base_url:
        raise RuntimeError("PayloadCMS base URL not configured")
    return PayloadMediaClient(
        settings.payload_base_url,
        api_token=settings.payload_api_token,
        timeout=settings.request_timeout_seconds,
    )


def _progress(percent: int, step: str, message: str) -> ProgressSnapshot:
    return ProgressSnapshot(percent=percent, current_step=step, message=message)


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in metadata.items() if v is not None}


def _download_to_temp(client: PayloadMediaClient, asset: MediaAsset, directory: Path) -> Path:
    target = directory / asset.filename
    client.download_media(asset, target)
    return target


def _ensure_temp_dir() -> Path:
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="video-job-", dir=settings.temp_dir))


@celery_app.task(name="video.concat", bind=True)
def concat_video(self: Task, job_id: str, payload: dict[str, Any]) -> None:
    """Celery task that concatenates multiple video segments."""

    from .job_models import ConcatJobRequest  # local import to avoid cycle

    job_store = _get_job_store()
    job_store.update_job(job_id, status=JobStatus.RUNNING, progress=_progress(5, "accepted", "Job accepted by worker"))

    request = ConcatJobRequest.model_validate(payload)

    client = _get_payload_client()
    temp_dir = _ensure_temp_dir()
    segments_dir = temp_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    try:
        downloaded_paths: list[Path] = []
        for index, input_item in enumerate(request.inputs):
            job_store.update_job(job_id, progress=_progress(10 + index * 10, "download", f"Downloading input {index + 1}"))
            asset = client.fetch_media(input_item.media_id)
            downloaded = _download_to_temp(client, asset, segments_dir)

            if input_item.start_ms is not None or input_item.end_ms is not None:
                trimmed = segments_dir / f"segment_{index:03d}.mp4"
                command: list[str] = [settings.ffmpeg_binary, "-y", "-i", str(downloaded)]
                if input_item.start_ms is not None:
                    command.extend(["-ss", f"{input_item.start_ms / 1000:.3f}"])
                if input_item.end_ms is not None:
                    if input_item.start_ms is not None:
                        duration = (input_item.end_ms - input_item.start_ms) / 1000
                        command.extend(["-t", f"{duration:.3f}"])
                    else:
                        command.extend(["-to", f"{input_item.end_ms / 1000:.3f}"])
                command.extend(
                    [
                        "-c:v",
                        "libx264",
                        "-preset",
                        "medium",
                        "-crf",
                        str(settings.default_crf),
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        str(trimmed),
                    ]
                )
                execute_ffmpeg(command)
                downloaded_paths.append(trimmed)
            else:
                downloaded_paths.append(downloaded)

        job_store.update_job(job_id, progress=_progress(60, "processing", "Concatenating segments"))

        filelist_path = temp_dir / "inputs.txt"
        generate_concat_filelist(downloaded_paths, filelist_path)

        output_basename = temp_dir / f"concat-{uuid4().hex}"
        command = build_concat_command(
            settings.ffmpeg_binary,
            filelist_path,
            output_basename,
            output_format=request.output_format,
            crf=settings.default_crf,
            audio_passthrough=bool(request.audio_track is None),
        )

        execute_ffmpeg(command)
        final_output_path = output_basename.with_suffix(f".{request.output_format}")

        if request.audio_track:
            job_store.update_job(job_id, progress=_progress(75, "audio", "Mixing override audio track"))
            audio_asset = client.fetch_media(request.audio_track)
            audio_path = _download_to_temp(client, audio_asset, temp_dir)
            mixed_path = temp_dir / f"mixed-{uuid4().hex}.{request.output_format}"
            mix_command = [
                settings.ffmpeg_binary,
                "-y",
                "-i",
                str(final_output_path),
                "-i",
                str(audio_path),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(mixed_path),
            ]
            execute_ffmpeg(mix_command)
            final_output_path = mixed_path

        job_store.update_job(job_id, progress=_progress(85, "probe", "Analyzing output"))
        metadata = probe_streams(settings.ffprobe_binary, final_output_path)
        summary = summarize_media(metadata)

        job_store.update_job(job_id, progress=_progress(92, "upload", "Uploading result to PayloadCMS"))
        upload_metadata = {
            "jobId": job_id,
            "operation": "concat",
            "inputs": json.dumps([item.media_id for item in request.inputs]),
            **request.metadata,
            **summary,
        }
        upload_response = client.upload_media(final_output_path, upload_metadata)
        result_media_id = str(upload_response.get("id") or upload_response.get("_id"))

        job_store.update_job(
            job_id,
            status=JobStatus.SUCCEEDED,
            progress=_progress(100, "completed", "Job completed"),
            result_media_id=result_media_id,
            metadata=_safe_metadata(summary),
            message="Video concatenation successful",
        )

    except FFmpegExecutionError as exc:
        logger.error("FFmpeg execution failed", job_id=job_id, error=exc.stderr)
        job_store.update_job(
            job_id,
            status=JobStatus.FAILED,
            progress=_progress(100, "failed", "Processing failed"),
            error=str(exc),
            message="FFmpeg command failed",
        )
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Concat job failed", job_id=job_id)
        job_store.update_job(
            job_id,
            status=JobStatus.FAILED,
            progress=_progress(100, "failed", "Processing failed"),
            error=str(exc),
            message="Unhandled error during video concat",
        )
        raise
    finally:
        _cleanup_temp_dir(temp_dir)


@celery_app.task(name="video.overlay", bind=True)
def overlay_video(self: Task, job_id: str, payload: dict[str, Any]) -> None:
    """Celery task that applies overlay assets to a video."""

    from .job_models import OverlayJobRequest

    job_store = _get_job_store()
    job_store.update_job(job_id, status=JobStatus.RUNNING, progress=_progress(5, "accepted", "Job accepted by worker"))

    request = OverlayJobRequest.model_validate(payload)
    client = _get_payload_client()
    temp_dir = _ensure_temp_dir()

    try:
        base_asset = client.fetch_media(request.input_media_id)
        base_path = _download_to_temp(client, base_asset, temp_dir)

        overlay_assets: list[MediaAsset] = []
        overlay_paths: list[Path] = []
        for index, overlay in enumerate(request.overlays):
            job_store.update_job(job_id, progress=_progress(15 + index * 5, "download", f"Downloading overlay {index + 1}"))
            asset = client.fetch_media(overlay.media_id)
            overlay_assets.append(asset)
            overlay_paths.append(_download_to_temp(client, asset, temp_dir))

        filter_specs = [
            {
                "index": idx + 1,
                "x": overlay.position_x,
                "y": overlay.position_y,
                "start": overlay.start_ms,
                "end": overlay.end_ms,
                "opacity": overlay.opacity,
                "scale": overlay.scale,
            }
            for idx, overlay in enumerate(request.overlays)
        ]
        filter_graph = build_overlay_filter(filter_specs)

        job_store.update_job(job_id, progress=_progress(60, "processing", "Rendering overlays"))

        output_path = temp_dir / f"overlay-{uuid4().hex}.{request.output_format}"
        command = build_overlay_command(
            settings.ffmpeg_binary,
            base_path,
            overlay_paths,
            Path(output_path),
            output_format=request.output_format,
            filter_graph=filter_graph,
        )
        execute_ffmpeg(command)

        job_store.update_job(job_id, progress=_progress(85, "probe", "Analyzing output"))
        metadata = probe_streams(settings.ffprobe_binary, output_path)
        summary = summarize_media(metadata)

        job_store.update_job(job_id, progress=_progress(92, "upload", "Uploading result to PayloadCMS"))
        upload_metadata = {
            "jobId": job_id,
            "operation": "overlay",
            "inputs": json.dumps([request.input_media_id]),
            "overlays": json.dumps([overlay.media_id for overlay in request.overlays]),
            **request.metadata,
            **summary,
        }
        upload_response = client.upload_media(output_path, upload_metadata)
        result_media_id = str(upload_response.get("id") or upload_response.get("_id"))

        job_store.update_job(
            job_id,
            status=JobStatus.SUCCEEDED,
            progress=_progress(100, "completed", "Job completed"),
            result_media_id=result_media_id,
            metadata=_safe_metadata(summary),
            message="Overlay applied successfully",
        )

    except FFmpegExecutionError as exc:
        logger.error("FFmpeg execution failed", job_id=job_id, error=exc.stderr)
        job_store.update_job(
            job_id,
            status=JobStatus.FAILED,
            progress=_progress(100, "failed", "Processing failed"),
            error=str(exc),
            message="FFmpeg command failed",
        )
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Overlay job failed", job_id=job_id)
        job_store.update_job(
            job_id,
            status=JobStatus.FAILED,
            progress=_progress(100, "failed", "Processing failed"),
            error=str(exc),
            message="Unhandled error during overlay",
        )
        raise
    finally:
        _cleanup_temp_dir(temp_dir)


def enqueue_concat_job(job_id: str, payload: dict[str, Any]) -> None:
    concat_video.apply_async(args=(job_id, payload))


def enqueue_overlay_job(job_id: str, payload: dict[str, Any]) -> None:
    overlay_video.apply_async(args=(job_id, payload))


def _cleanup_temp_dir(temp_dir: Path) -> None:
    try:
        for nested in sorted(temp_dir.rglob("*"), reverse=True):
            if nested.is_file():
                nested.unlink(missing_ok=True)
            elif nested.is_dir():
                nested.rmdir()
        temp_dir.rmdir()
    except Exception:  # pragma: no cover - best effort cleanup
        logger.debug("Temporary directory cleanup failed", path=temp_dir)
