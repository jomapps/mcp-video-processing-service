"""Utility functions for constructing FFmpeg command lines."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional


DEFAULT_SCALE_FILTER = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1"


def build_concat_command(
    ffmpeg_binary: str,
    filelist_path: Path,
    output_path: Path,
    *,
    output_format: str = "mp4",
    crf: int = 21,
    audio_passthrough: bool = False,
) -> list[str]:
    """Build the FFmpeg command for concatenating multiple segments.

    Args:
        ffmpeg_binary: Executable path for ffmpeg.
        filelist_path: Path to the concat demuxer filelist.
        output_path: Destination path for the rendered video.
        output_format: Desired container format.
        crf: Constant Rate Factor for libx264.
        audio_passthrough: Whether to copy audio from sources verbatim.
    """

    command = [
        ffmpeg_binary,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(filelist_path),
        "-vf",
        DEFAULT_SCALE_FILTER,
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-preset",
        "medium",
    ]

    if audio_passthrough:
        command.extend(["-c:a", "copy"])
    else:
        command.extend(["-c:a", "aac", "-b:a", "192k"])

    command.extend(["-movflags", "+faststart", str(output_path.with_suffix(f".{output_format}"))])
    return command


def generate_concat_filelist(inputs: Iterable[Path], filelist_path: Path) -> None:
    """Write a concat demuxer filelist for FFmpeg.

    Each input is marked with ``file 'path'`` and a newline.
    """

    lines = [f"file '{path.as_posix()}'" for path in inputs]
    filelist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_overlay_filter(overlays: list[dict[str, float | int]]) -> str:
    """Generate an overlay filter_complex string for FFmpeg.

    The overlays list contains dictionaries with keys ``index``, ``x``, ``y``, ``start``,
    ``end``, and ``opacity``.
    """

    base_label = "base"
    filter_parts: list[str] = []
    filter_parts.append(f"[0:v]{DEFAULT_SCALE_FILTER}[{base_label}]")

    current_label = base_label

    for idx, spec in enumerate(overlays, start=1):
        label_in = current_label
        label_out = f"ov{idx}"
        source_label = f"{idx}:v"
        components: list[str] = []
        if spec.get("scale"):
            components.append(f"scale=iw*{spec['scale']}:ih*{spec['scale']}")
        if spec.get("opacity") is not None and spec["opacity"] < 1.0:
            components.append(f"format=rgba,colorchannelmixer=aa={spec['opacity']}")
        overlay_stream = source_label
        if components:
            filter_parts.append(f"[{source_label}]" + ",".join(components) + f"[overlay{idx}]")
            overlay_stream = f"overlay{idx}"

        enable_clause = ""
        start = spec.get("start")
        end = spec.get("end")
        if start is not None or end is not None:
            conditions: list[str] = []
            if start is not None:
                conditions.append(f"gte(t,{start / 1000:.3f})")
            if end is not None:
                conditions.append(f"lte(t,{end / 1000:.3f})")
            enable_clause = ":enable='" + "*".join(conditions) + "'"

        filter_parts.append(
            f"[{label_in}][{overlay_stream}]overlay=x={int(spec['x'])}:y={int(spec['y'])}{enable_clause}[{label_out}]"
        )
        current_label = label_out

    filter_parts.append(f"[{current_label}]setsar=1[outv]")
    return ";".join(filter_parts)


def build_overlay_command(
    ffmpeg_binary: str,
    base_video: Path,
    overlay_paths: list[Path],
    output_path: Path,
    *,
    output_format: str = "mp4",
    filter_graph: Optional[str] = None,
) -> list[str]:
    """Construct the FFmpeg command for applying overlays to a video."""

    command: list[str] = [ffmpeg_binary, "-y", "-i", str(base_video)]
    for path in overlay_paths:
        command.extend(["-i", str(path)])

    graph = filter_graph or f"[0:v]{DEFAULT_SCALE_FILTER}[outv]"
    command.extend(["-filter_complex", graph, "-map", "[outv]"])
    # Map audio from first input
    command.extend(["-map", "0:a?", "-c:v", "libx264", "-crf", "21", "-preset", "medium", "-c:a", "aac", "-b:a", "192k"])
    command.extend(["-movflags", "+faststart", str(output_path.with_suffix(f".{output_format}"))])
    return command
