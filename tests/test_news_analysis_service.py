from urllib.error import HTTPError, URLError

import pytest

from app.services.news_analysis_service import (
    NewsAnalysisError,
    NewsAnalysisService,
    NewsFetchError,
)


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


def test_sentiment_keyword_matching_uses_word_boundaries(monkeypatch) -> None:
    service = NewsAnalysisService()
    xml_payload = b"""
    <rss>
      <channel>
        <item>
          <title>ABC dismisses market rumors</title>
          <link>https://example.com/1</link>
          <pubDate>Wed, 08 May 2026 10:00:00 GMT</pubDate>
          <description>Leadership discusses strategy with stable guidance.</description>
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
    assert payload["articles"][0]["sentiment"] == "neutral"


def test_analyze_ticker_news_rejects_empty_ticker() -> None:
    service = NewsAnalysisService()
    with pytest.raises(NewsAnalysisError):
        service.analyze_ticker_news("   ")


def test_analyze_ticker_news_valid_ticker_normalizes_symbol_and_source(monkeypatch) -> None:
    service = NewsAnalysisService()
    xml_payload = b"""
    <rss>
      <channel>
        <item>
          <title>MSFT reports record profit growth</title>
          <pubDate>Wed, 08 May 2026 10:00:00 GMT</pubDate>
          <description>Strong growth with stable demand.</description>
          <source>Example Wire</source>
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

    payload = service.analyze_ticker_news(" msft ")
    assert payload["source"] == "google_news_rss"
    assert payload["error"] is None
    assert payload["articles"][0]["title"] == "MSFT reports record profit growth"


def test_analyze_ticker_news_returns_empty_articles_when_channel_missing(monkeypatch) -> None:
    service = NewsAnalysisService()
    xml_payload = b"<rss><feed></feed></rss>"

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
    assert payload["articles"] == []
    assert payload["overall_sentiment"] == "neutral"
    assert payload["risk_keywords_detected"] == []


def test_analyze_ticker_news_returns_empty_articles_when_no_items(monkeypatch) -> None:
    service = NewsAnalysisService()
    xml_payload = b"<rss><channel></channel></rss>"

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
    assert payload["articles"] == []
    assert payload["overall_sentiment"] == "neutral"


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: HTTPError(url="https://example.com", code=503, msg="upstream down", hdrs=None, fp=None),
        lambda: URLError(reason="dns failure"),
        lambda: TimeoutError("timed out"),
    ],
    ids=["http-error", "url-error", "timeout-error"],
)
def test_fetch_news_items_raises_news_fetch_error_for_api_failures(monkeypatch, error_factory) -> None:
    service = NewsAnalysisService()

    def raise_error(*_args, **_kwargs):
        raise error_factory()

    monkeypatch.setattr("app.services.news_analysis_service.urlopen", raise_error)

    with pytest.raises(NewsFetchError):
        service.analyze_ticker_news("AAPL")


def test_fetch_news_items_raises_news_fetch_error_for_malformed_xml(monkeypatch) -> None:
    service = NewsAnalysisService()

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def read(self):
            return b"<rss><channel><item></rss>"

    monkeypatch.setattr(
        "app.services.news_analysis_service.urlopen",
        lambda *_args, **_kwargs: DummyResponse(),
    )

    with pytest.raises(NewsFetchError):
        service.analyze_ticker_news("AAPL")


def test_sentiment_classification_covers_bullish_bearish_and_neutral() -> None:
    service = NewsAnalysisService()
    assert (
        service._score_sentiment(
            title="Company beats earnings with record growth",
            summary="Profit rally continues after upgrade.",
        )
        == "bullish"
    )
    assert (
        service._score_sentiment(
            title="Company misses estimates and stock falls",
            summary="Warning issued as analysts discuss decline.",
        )
        == "bearish"
    )
    assert (
        service._score_sentiment(
            title="Company hosts annual investor event",
            summary="Management outlined long-term strategy.",
        )
        == "neutral"
    )


def test_risk_keyword_detection_is_case_insensitive_and_deduplicated_in_payload(monkeypatch) -> None:
    service = NewsAnalysisService()
    xml_payload = b"""
    <rss>
      <channel>
        <item>
          <title>ABC faces LAWSUIT</title>
          <description>Fraud probe begins after investigation report.</description>
          <source>Example News</source>
        </item>
        <item>
          <title>ABC mentions lawsuit updates</title>
          <description>No new fraud evidence reported.</description>
          <source>Example News</source>
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
    assert sorted(payload["risk_keywords_detected"]) == ["fraud", "investigation", "lawsuit"]


def test_build_fallback_payload_shape() -> None:
    service = NewsAnalysisService()
    payload = service.build_fallback_payload("simulated error")
    assert payload == {
        "source": "google_news_rss",
        "articles": [],
        "overall_sentiment": "neutral",
        "risk_keywords_detected": [],
        "error": "simulated error",
    }
