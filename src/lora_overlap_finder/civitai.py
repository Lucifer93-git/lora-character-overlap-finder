from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(slots=True)
class CivitaiClient:
    api_token: str | None = None
    base_url: str = "https://civitai.com/api/v1"
    timeout: float = 20.0

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "lora-character-overlap-finder/0.1"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def get_model_version_by_hash(self, sha256: str) -> dict | None:
        response = requests.get(
            f"{self.base_url}/model-versions/by-hash/{sha256}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
