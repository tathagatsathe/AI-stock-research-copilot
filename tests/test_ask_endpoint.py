from fastapi.testclient import TestClient

from app.main import app


def test_ask_endpoint_returns_grounded_payload() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/stocks/ask",
        json={"ticker": "AAPL", "question": "What competition risks are mentioned?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "answer" in data
    assert "citations" in data
    assert data["retrieval_confidence"] in {"high", "medium", "low"}
