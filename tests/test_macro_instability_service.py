import pandas as pd
import pytest

from app.services.macro_instability_service import MacroInstabilityService


def test_instability_score_bounds_and_regime() -> None:
    svc = MacroInstabilityService()
    assert svc._regime(12.0) == "compressed"
    assert svc._regime(20.0) == "normal"
    assert svc._regime(30.0) == "elevated"

    score = svc._instability_score(level=18.0, change_5d_pct=None)
    assert 1 <= score <= 10


def test_snapshot_fallback_when_history_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.macro_instability_service as macro_mod

    class DummyTicker:
        def history(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(macro_mod.yf, "Ticker", lambda _: DummyTicker())

    svc = MacroInstabilityService()
    payload = svc.snapshot()

    assert payload["coverage"] == "low"
    assert payload["error"] is not None
    assert payload["instability_score_1_10"] == 5
    assert payload["region"] == "us"


def test_snapshot_uses_india_region_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.macro_instability_service as macro_mod

    captured: dict[str, str] = {}

    class DummyTicker:
        def __init__(self, symbol: str) -> None:
            captured["symbol"] = symbol

        def history(self, **kwargs):
            return pd.DataFrame({"Close": [15.0, 16.0, 17.0, 18.0, 19.0, 20.0]})

    monkeypatch.setattr(macro_mod.yf, "Ticker", DummyTicker)

    svc = MacroInstabilityService()
    payload = svc.snapshot(region="india")

    assert captured["symbol"] == "^INDIAVIX"
    assert payload["region"] == "india"
    assert payload["coverage"] == "high"
