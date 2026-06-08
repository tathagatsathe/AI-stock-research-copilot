from app.services.rag_service import RagService


def test_rag_memory_retrieve_from_seed_filings() -> None:
    rag = RagService()
    rag._retrieve_chroma = lambda *_args, **_kwargs: []  # force in-memory token overlap path
    hits = rag.retrieve(ticker="AAPL", query="competition supply chain risk")
    assert len(hits) >= 1
    assert any("competition" in hit["text"].lower() for hit in hits)


def test_rag_ask_without_chunks_returns_low_confidence() -> None:
    rag = RagService()
    out = rag.ask(ticker="ZZZZ", question="What are the main risks?")
    assert out["retrieval_confidence"] == "low"
    assert out["citations"] == []
