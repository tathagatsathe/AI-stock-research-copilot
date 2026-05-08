import logging
import re
from datetime import timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from html import unescape
from typing import Final, Literal, TypedDict
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import urlopen
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

SentimentLabel = Literal["bullish", "bearish", "neutral"]


class NewsArticlePayload(TypedDict):
    title: str
    source: str
    publish_date: str
    summary: str
    sentiment: SentimentLabel
    risk_keywords: list[str]


class NewsAnalysisPayload(TypedDict):
    source: str
    articles: list[NewsArticlePayload]
    overall_sentiment: SentimentLabel
    risk_keywords_detected: list[str]
    error: str | None


class NewsAnalysisError(Exception):
    """Base exception for news analysis service errors."""


class NewsFetchError(NewsAnalysisError):
    """Raised when news cannot be fetched from the upstream provider."""


class NewsAnalysisService:
    _GOOGLE_NEWS_BASE_URL: Final[str] = (
        "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    )
    _MAX_ARTICLES: Final[int] = 5
    _REQUEST_TIMEOUT_SECONDS: Final[float] = 6.0
    _RISK_KEYWORDS: Final[tuple[str, ...]] = (
        "lawsuit",
        "fraud",
        "sanctions",
        "layoffs",
        "downgrade",
        "investigation",
        "bankruptcy",
    )
    _BULLISH_KEYWORDS: Final[tuple[str, ...]] = (
        "beat",
        "beats",
        "surge",
        "growth",
        "upgrade",
        "bullish",
        "rally",
        "profit",
        "record",
    )
    _BEARISH_KEYWORDS: Final[tuple[str, ...]] = (
        "miss",
        "falls",
        "drop",
        "downgrade",
        "bearish",
        "loss",
        "cuts",
        "warning",
        "decline",
    )
    _TAG_PATTERN: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")
    _WHITESPACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s+")

    def analyze_ticker_news(self, ticker: str) -> NewsAnalysisPayload:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise NewsAnalysisError("Ticker symbol cannot be empty for news analysis.")

        items = self._fetch_news_items(normalized_ticker)
        articles = [self._parse_item(item) for item in items[: self._MAX_ARTICLES]]

        all_risk_keywords = sorted({kw for article in articles for kw in article["risk_keywords"]})
        overall_sentiment = self._aggregate_sentiment(articles)

        return NewsAnalysisPayload(
            source="google_news_rss",
            articles=articles,
            overall_sentiment=overall_sentiment,
            risk_keywords_detected=all_risk_keywords,
            error=None,
        )

    def build_fallback_payload(self, error_message: str) -> NewsAnalysisPayload:
        return NewsAnalysisPayload(
            source="google_news_rss",
            articles=[],
            overall_sentiment="neutral",
            risk_keywords_detected=[],
            error=error_message,
        )

    def _fetch_news_items(self, ticker: str) -> list[ElementTree.Element]:
        query = quote_plus(f"{ticker} stock")
        url = self._GOOGLE_NEWS_BASE_URL.format(query=query)
        try:
            with urlopen(url, timeout=self._REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                xml_bytes = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.warning("News fetch failed for ticker %s from URL %s", ticker, url)
            raise NewsFetchError("Failed to fetch latest news from Google News RSS.") from exc

        try:
            root = ElementTree.fromstring(xml_bytes)
        except ElementTree.ParseError as exc:
            logger.warning("Invalid RSS response for ticker %s", ticker)
            raise NewsFetchError("Received malformed news feed from Google News RSS.") from exc

        channel = root.find("channel")
        if channel is None:
            return []
        return channel.findall("item")

    def _parse_item(self, item: ElementTree.Element) -> NewsArticlePayload:
        title = self._text_or_default(item.findtext("title"), "Untitled")
        source = self._text_or_default(item.findtext("source"), "Unknown")
        publish_date = self._parse_publish_date(item.findtext("pubDate"))
        summary = self._clean_summary(item.findtext("description"))

        sentiment = self._score_sentiment(title=title, summary=summary)
        risk_keywords = self._detect_risk_keywords(title=title, summary=summary)

        return NewsArticlePayload(
            title=title,
            source=source,
            publish_date=publish_date,
            summary=summary,
            sentiment=sentiment,
            risk_keywords=risk_keywords,
        )

    @staticmethod
    def _text_or_default(value: str | None, default: str) -> str:
        cleaned = (value or "").strip()
        return cleaned or default

    def _parse_publish_date(self, value: str | None) -> str:
        if not value:
            return ""
        try:
            published_dt = parsedate_to_datetime(value)
            return published_dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return ""

    def _clean_summary(self, value: str | None) -> str:
        raw = unescape(value or "")
        without_tags = self._TAG_PATTERN.sub(" ", raw)
        normalized = self._WHITESPACE_PATTERN.sub(" ", without_tags).strip()
        if not normalized:
            return "No summary available."
        return normalized[:280]

    def _score_sentiment(self, *, title: str, summary: str) -> SentimentLabel:
        text = f"{title} {summary}".lower()
        bullish_score = sum(1 for kw in self._BULLISH_KEYWORDS if kw in text)
        bearish_score = sum(1 for kw in self._BEARISH_KEYWORDS if kw in text)

        if bullish_score > bearish_score:
            return "bullish"
        if bearish_score > bullish_score:
            return "bearish"
        return "neutral"

    def _aggregate_sentiment(self, articles: list[NewsArticlePayload]) -> SentimentLabel:
        bullish_count = sum(1 for article in articles if article["sentiment"] == "bullish")
        bearish_count = sum(1 for article in articles if article["sentiment"] == "bearish")

        if bullish_count > bearish_count:
            return "bullish"
        if bearish_count > bullish_count:
            return "bearish"
        return "neutral"

    def _detect_risk_keywords(self, *, title: str, summary: str) -> list[str]:
        text = f"{title} {summary}".lower()
        return [kw for kw in self._RISK_KEYWORDS if kw in text]


@lru_cache
def get_news_analysis_service() -> NewsAnalysisService:
    return NewsAnalysisService()
