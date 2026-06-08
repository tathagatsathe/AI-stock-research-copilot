"""HTTP client for local Ollama inference."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Raised when Ollama request fails."""


class OllamaClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.timeout_seconds = settings.ollama_timeout_seconds

    def generate_json(self, *, prompt: str, system: str | None = None) -> dict[str, Any]:
        """Call Ollama /api/generate with JSON format and parse the response."""
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        if system:
            payload["system"] = system

        raw = self._post("/api/generate", payload)
        response_text = str(raw.get("response", "")).strip()
        if not response_text:
            raise OllamaError("Ollama returned an empty response.")
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Ollama response is not valid JSON: {response_text[:200]}") from exc
        if not isinstance(parsed, dict):
            raise OllamaError("Ollama JSON response must be an object.")
        return parsed

    def chat(self, *, messages: list[dict[str, str]], format_json: bool = False) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if format_json:
            payload["format"] = "json"
        raw = self._post("/api/chat", payload)
        message = raw.get("message") or {}
        content = str(message.get("content", "")).strip()
        if not content:
            raise OllamaError("Ollama chat returned empty content.")
        return content

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(  # noqa: S310
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_bytes = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.warning("Ollama request failed: %s", exc)
            raise OllamaError(f"Ollama request failed: {exc}") from exc

        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned non-JSON payload.") from exc
        if not isinstance(parsed, dict):
            raise OllamaError("Ollama response must be a JSON object.")
        return parsed

    def is_available(self) -> bool:
        try:
            self._get("/api/tags")
            return True
        except OllamaError:
            return False

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request = Request(url, method="GET")  # noqa: S310
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_bytes = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise OllamaError(f"Ollama GET failed: {exc}") from exc
        parsed = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise OllamaError("Ollama GET response must be a JSON object.")
        return parsed


@lru_cache
def get_ollama_client() -> OllamaClient:
    return OllamaClient()
