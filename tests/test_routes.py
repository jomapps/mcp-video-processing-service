from __future__ import annotations

from fastapi.testclient import TestClient


def test_submit_concat_job(api_client: TestClient, enqueue_spy: list[tuple[str, str, dict]]) -> None:
    payload = {
        "inputs": [{"media_id": "media-1"}, {"media_id": "media-2", "start_ms": 0, "end_ms": 5000}],
        "metadata": {"requestedBy": "tests"},
    }

    response = api_client.post("/jobs/concat", json=payload)
    assert response.status_code == 202
    job_id = response.json()["jobId"]

    assert enqueue_spy and enqueue_spy[0][0] == "concat"
    _, recorded_job_id, recorded_payload = enqueue_spy[0]
    assert recorded_job_id == job_id
    assert recorded_payload["inputs"][0]["media_id"] == "media-1"

    status_response = api_client.get(f"/jobs/{job_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["jobId"] == job_id
    assert body["status"] == "queued"


def test_submit_overlay_job(api_client: TestClient, enqueue_spy: list[tuple[str, str, dict]]) -> None:
    payload = {
        "input_media_id": "base-video",
        "overlays": [
            {
                "media_id": "overlay-1",
                "position_x": 100,
                "position_y": 200,
                "start_ms": 0,
                "end_ms": 2000,
            }
        ],
    }

    response = api_client.post("/jobs/overlay", json=payload)
    assert response.status_code == 202
    job_id = response.json()["jobId"]

    recorded_overlay = next(item for item in enqueue_spy if item[0] == "overlay")
    assert recorded_overlay[1] == job_id
    assert recorded_overlay[2]["overlays"][0]["media_id"] == "overlay-1"


def test_get_job_not_found(api_client: TestClient) -> None:
    response = api_client.get("/jobs/missing")
    assert response.status_code == 404
