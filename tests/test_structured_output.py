from app.services.structured_output import parse_ask_response, parse_decision_brief_payload


def test_parse_decision_brief_payload_normalizes_verdict() -> None:
    out = parse_decision_brief_payload(
        {
            "verdict": "invalid",
            "summary_bullets": ["one", "two"],
            "top_risks": [],
            "tensions": [],
            "evidence_quality": "high",
            "news_coverage_note": "ok",
        },
        fallback_note="fallback",
    )
    assert out["verdict"] == "cautious"
    assert out["synthesis_source"] == "llm"
    assert out["summary_bullets"] == ["one", "two"]


def test_parse_ask_response_defaults() -> None:
    out = parse_ask_response({"answer": "", "citations": []})
    assert "Insufficient evidence" in out["answer"]
    assert out["retrieval_confidence"] == "medium"
