"""FFprobe integration helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def probe_streams(ffprobe_binary: str, media_path: Path) -> dict[str, Any]:
    """Return structured metadata for the supplied media file."""

    command = [
        ffprobe_binary,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-print_format",
        "json",
        str(media_path),
    ]
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout or "{}")


def summarize_media(metadata: dict[str, Any]) -> dict[str, Any]:
    """Extract lightweight summary info for job metadata."""

    format_info = metadata.get("format", {})
    duration = float(format_info.get("duration", 0)) if format_info.get("duration") else None
    video_streams = [s for s in metadata.get("streams", []) if s.get("codec_type") == "video"]
    audio_streams = [s for s in metadata.get("streams", []) if s.get("codec_type") == "audio"]

    summary: dict[str, Any] = {}
    if duration is not None:
        summary["durationMs"] = int(duration * 1000)
    if video_streams:
        video = video_streams[0]
        summary["videoCodec"] = video.get("codec_name")
        summary["width"] = video.get("width")
        summary["height"] = video.get("height")
    if audio_streams:
        summary["audioCodec"] = audio_streams[0].get("codec_name")
        summary["audioChannels"] = audio_streams[0].get("channels")
    return summary
