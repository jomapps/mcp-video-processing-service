"""Execution utilities for FFmpeg commands."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable


class FFmpegExecutionError(RuntimeError):
    """Raised when an FFmpeg command fails."""

    def __init__(self, command: Iterable[str], stderr: str) -> None:
        self.command = list(command)
        self.stderr = stderr
        super().__init__(f"FFmpeg command failed: {' '.join(self.command)}\n{stderr}")


def execute_ffmpeg(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run FFmpeg synchronously, raising FFmpegExecutionError on failure."""

    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise FFmpegExecutionError(command, completed.stderr)
    return completed
