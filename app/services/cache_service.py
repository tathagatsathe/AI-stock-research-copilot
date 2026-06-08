"""TTL cache for Yahoo Finance fetches (Redis with in-memory fallback)."""

from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheService:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.cache_enabled
        self.default_ttl_seconds = settings.cache_ttl_seconds
        self._memory: dict[str, tuple[float, str]] = {}
        self._redis = None
        if settings.redis_url:
            try:
                import redis  # type: ignore[import-untyped]

                self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("Redis cache connected.")
            except Exception as exc:
                logger.warning("Redis unavailable, using in-memory cache: %s", exc)
                self._redis = None

    def get_json(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        raw = self._get_raw(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self.delete(key)
            return None

    def set_json(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        if not self.enabled:
            return
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        payload = json.dumps(value, default=str)
        self._set_raw(key, payload, ttl)

    def delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(key)
            except Exception:
                logger.debug("Redis delete failed for key %s", key)
        self._memory.pop(key, None)

    def _get_raw(self, key: str) -> str | None:
        if self._redis is not None:
            try:
                value = self._redis.get(key)
                if value is not None:
                    return str(value)
            except Exception:
                logger.debug("Redis get failed for key %s", key)
        entry = self._memory.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if time.time() > expires_at:
            self._memory.pop(key, None)
            return None
        return payload

    def _set_raw(self, key: str, payload: str, ttl_seconds: int) -> None:
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl_seconds, payload)
                return
            except Exception:
                logger.debug("Redis set failed for key %s", key)
        self._memory[key] = (time.time() + ttl_seconds, payload)


@lru_cache
def get_cache_service() -> CacheService:
    return CacheService()
