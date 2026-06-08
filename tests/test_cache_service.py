from app.services.cache_service import CacheService


def test_cache_set_and_get_json() -> None:
    cache = CacheService()
    cache.set_json("test:key", {"value": 42}, ttl_seconds=60)
    assert cache.get_json("test:key") == {"value": 42}


def test_cache_miss_returns_none() -> None:
    cache = CacheService()
    assert cache.get_json("missing:key:xyz") is None
