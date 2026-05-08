from app.services.news_analysis_service import NewsAnalysisService


def test_analyze_ticker_news_limits_to_latest_five_articles(monkeypatch) -> None:
    service = NewsAnalysisService()
    xml_items = "".join(
        [
            f"""
            <item>
                <title>Item {i} surge in growth</title>
                <link>https://example.com/{i}</link>
                <pubDate>Wed, 08 May 2026 10:00:00 GMT</pubDate>
                <description>Company reports profit growth and no major issues.</description>
                <source url="https://example.com">Example News</source>
            </item>
            """
            for i in range(8)
        ]
    )
    xml_payload = f"<rss><channel>{xml_items}</channel></rss>".encode()

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def read(self):
            return xml_payload

    monkeypatch.setattr(
        "app.services.news_analysis_service.urlopen",
        lambda *_args, **_kwargs: DummyResponse(),
    )

    payload = service.analyze_ticker_news("AAPL")
    assert payload["source"] == "google_news_rss"
    assert len(payload["articles"]) == 5
    assert payload["overall_sentiment"] == "bullish"


def test_analyze_ticker_news_detects_risk_keywords_and_bearish_tone(monkeypatch) -> None:
    service = NewsAnalysisService()
    xml_payload = b"""
    <rss>
      <channel>
        <item>
          <title>ABC faces lawsuit and downgrade</title>
          <link>https://example.com/1</link>
          <pubDate>Wed, 08 May 2026 10:00:00 GMT</pubDate>
          <description>Investigation expands after fraud allegations and decline in outlook.</description>
          <source url="https://example.com">Example News</source>
        </item>
      </channel>
    </rss>
    """

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def read(self):
            return xml_payload

    monkeypatch.setattr(
        "app.services.news_analysis_service.urlopen",
        lambda *_args, **_kwargs: DummyResponse(),
    )

    payload = service.analyze_ticker_news("ABC")
    article = payload["articles"][0]
    assert article["sentiment"] == "bearish"
    assert "lawsuit" in article["risk_keywords"]
    assert "fraud" in article["risk_keywords"]
    assert "investigation" in payload["risk_keywords_detected"]
