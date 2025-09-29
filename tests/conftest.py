from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp_video_processing_service.job_store import InMemoryJobStore
from mcp_video_processing_service.main import create_app


@pytest.fixture()
def in_memory_store() -> InMemoryJobStore:
    return InMemoryJobStore()


@pytest.fixture()
def enqueue_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict]]:
    captured: list[tuple[str, str, dict]] = []

    def record_concat(job_id: str, payload: dict) -> None:
        captured.append(("concat", job_id, payload))

    def record_overlay(job_id: str, payload: dict) -> None:
        captured.append(("overlay", job_id, payload))

    monkeypatch.setattr("mcp_video_processing_service.tasks.enqueue_concat_job", record_concat)
    monkeypatch.setattr("mcp_video_processing_service.tasks.enqueue_overlay_job", record_overlay)
    monkeypatch.setattr("mcp_video_processing_service.api.routes.enqueue_concat_job", record_concat)
    monkeypatch.setattr("mcp_video_processing_service.api.routes.enqueue_overlay_job", record_overlay)
    return captured


@pytest.fixture()
def api_client(in_memory_store: InMemoryJobStore) -> TestClient:
    app = create_app(job_store=in_memory_store)
    with TestClient(app) as client:
        yield client
