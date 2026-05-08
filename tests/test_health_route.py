from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_expected_shape_and_utc_timestamp() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"]
    assert payload["environment"]
    parsed = datetime.fromisoformat(payload["timestamp"])
    assert parsed.tzinfo is not None
