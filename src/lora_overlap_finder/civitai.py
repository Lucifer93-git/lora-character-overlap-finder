from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(slots=True)
class CivitaiClient:
    api_token: str | None = None
    base_url: str = "https://civitai.com/api/v1"
    timeout: float = 25.0

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "lora-character-overlap-finder/0.1",
        }
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

    def get_model_versions_by_hashes(self, hashes: list[str]) -> list[dict]:
        results: list[dict] = []
        unique = list(dict.fromkeys(h.upper() for h in hashes if len(h) == 64))
        # Use the documented single-hash endpoint for reliability. The cache means
        # each hash is normally requested only once across scans.
        for sha256 in unique:
            payload = self.get_model_version_by_hash(sha256)
            if payload:
                results.append(payload)
        return results

    def get_model(self, model_id: int) -> dict | None:
        response = requests.get(
            f"{self.base_url}/models/{model_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
