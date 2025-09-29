from __future__ import annotations

from pathlib import Path

from mcp_video_processing_service.ffmpeg.command_builder import (
    build_concat_command,
    build_overlay_command,
    build_overlay_filter,
    generate_concat_filelist,
)


def test_generate_concat_filelist(tmp_path: Path) -> None:
    inputs = [tmp_path / f"clip_{idx}.mp4" for idx in range(3)]
    for path in inputs:
        path.touch()

    manifest = tmp_path / "inputs.txt"
    generate_concat_filelist(inputs, manifest)

    content = manifest.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line.startswith("file ")]
    assert len(lines) == 3
    assert str(inputs[0].as_posix()) in lines[0]


def test_build_concat_command(tmp_path: Path) -> None:
    filelist = tmp_path / "inputs.txt"
    filelist.write_text("file 'a.mp4'\n")
    output_path = tmp_path / "output"

    command = build_concat_command(
        "ffmpeg",
        filelist,
        output_path,
        output_format="mp4",
        crf=23,
        audio_passthrough=False,
    )

    assert command[:4] == ["ffmpeg", "-y", "-f", "concat"]
    assert "-safe" in command
    assert command[-1].endswith(".mp4")


def test_build_overlay_command(tmp_path: Path) -> None:
    base = tmp_path / "base.mp4"
    base.touch()
    overlay = tmp_path / "overlay.png"
    overlay.touch()

    filter_graph = build_overlay_filter(
        [
            {"index": 1, "x": 10, "y": 20, "start": 0, "end": 1000, "opacity": 0.5, "scale": 0.5}
        ]
    )
    command = build_overlay_command(
        "ffmpeg",
        base,
        [overlay],
        tmp_path / "result.mp4",
        output_format="mp4",
        filter_graph=filter_graph,
    )

    assert command[0] == "ffmpeg"
    assert "-filter_complex" in command
    assert command[-1].endswith(".mp4")
