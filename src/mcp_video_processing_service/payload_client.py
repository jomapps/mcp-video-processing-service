"""Client for interacting with PayloadCMS media endpoints."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MediaAsset:
    """Minimal representation of a PayloadCMS media asset."""

    media_id: str
    filename: str
    mime_type: str
    download_url: str


class PayloadMediaClient:
    """Blocking client for managing PayloadCMS media assets."""

    def __init__(
        self,
        base_url: str,
        *,
        api_token: Optional[str] = None,
        timeout: float = 30.0,
        verify: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._api_token = api_token
        self._timeout = timeout
        self._verify = verify

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
        return headers

    def fetch_media(self, media_id: str) -> MediaAsset:
        """Retrieve metadata for a media asset."""

        url = f"{self._base_url}/media/{media_id}"
        with httpx.Client(timeout=self._timeout, verify=self._verify) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            data = response.json()

        download_url = data.get("directDownloadUrl") or data.get("url")
        if not download_url:
            raise ValueError("PayloadCMS response missing download URL")

        return MediaAsset(
            media_id=media_id,
            filename=data.get("filename") or data.get("originalFilename", media_id),
            mime_type=data.get("mimeType") or data.get("mimetype", "application/octet-stream"),
            download_url=download_url,
        )

    def download_media(self, asset: MediaAsset, destination: Path) -> None:
        """Download a media asset to the specified destination path."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=self._timeout, verify=self._verify) as client:
            with client.stream("GET", asset.download_url, headers=self._headers()) as response:
                response.raise_for_status()
                with destination.open("wb") as output_file:
                    for chunk in response.iter_bytes():
                        output_file.write(chunk)

    def upload_media(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        """Upload processed media back to PayloadCMS."""

        url = f"{self._base_url}/media"
        data: Dict[str, Any] = {k: str(v) for k, v in metadata.items() if k != "mimeType"}

        with file_path.open("rb") as file_handle:
            files = {
                "file": (
                    file_path.name,
                    file_handle,
                    metadata.get("mimeType", "video/mp4"),
                )
            }
            with httpx.Client(timeout=self._timeout, verify=self._verify) as client:
                response = client.post(
                    url,
                    headers=self._headers(),
                    data=data,
                    files=files,
                )
                response.raise_for_status()
                return response.json()
