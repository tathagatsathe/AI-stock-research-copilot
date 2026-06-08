from __future__ import annotations

import logging
import re
from datetime import timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from html import unescape
from typing import Final, Literal, Optional, TypedDict

from app.services.asset_registry import AssetClass
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
    error: Optional[str]


class NewsAnalysisError(Exception):
    """Base exception for news analysis service errors."""


class NewsFetchError(NewsAnalysisError):
    """Raised when news cannot be fetched from the upstream provider."""


class NewsAnalysisService:
    _GOOGLE_NEWS_LOCALES: Final[dict[str, str]] = {
        "us": "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
        "india": "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en",
        "global": "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
    }
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
    _BULLISH_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
        re.compile(rf"\b{re.escape(kw)}\b") for kw in _BULLISH_KEYWORDS
    )
    _BEARISH_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
        re.compile(rf"\b{re.escape(kw)}\b") for kw in _BEARISH_KEYWORDS
    )
    _RISK_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
        kw: re.compile(rf"\b{re.escape(kw)}\b") for kw in _RISK_KEYWORDS
    }

    def analyze_ticker_news(
        self,
        ticker: str,
        *,
        asset_class: AssetClass | None = None,
        display_name: str | None = None,
    ) -> NewsAnalysisPayload:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise NewsAnalysisError("Ticker symbol cannot be empty for news analysis.")

        items = self._fetch_news_items(
            normalized_ticker,
            asset_class=asset_class,
            display_name=display_name,
        )
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

    def _build_news_query(
        self,
        ticker: str,
        *,
        asset_class: AssetClass | None,
        display_name: str | None,
    ) -> tuple[str, str]:
        label = (display_name or ticker).strip()
        locale_key = "us"

        if asset_class == AssetClass.INDIA_EQUITY:
            locale_key = "india"
            query_text = f"{label} NSE stock"
        elif asset_class == AssetClass.GLOBAL_INDEX:
            locale_key = "global"
            query_text = f"{label} index market"
        elif asset_class == AssetClass.FOREX:
            locale_key = "global"
            query_text = f"{label} forex currency"
        elif asset_class == AssetClass.CRYPTO:
            locale_key = "global"
            query_text = f"{label} cryptocurrency"
        elif asset_class == AssetClass.COMMODITY:
            locale_key = "global"
            query_text = f"{label} commodity futures"
        else:
            query_text = f"{ticker} stock"

        return query_text, locale_key

    def _fetch_news_items(
        self,
        ticker: str,
        *,
        asset_class: AssetClass | None = None,
        display_name: str | None = None,
    ) -> list[ElementTree.Element]:
        query_text, locale_key = self._build_news_query(
            ticker,
            asset_class=asset_class,
            display_name=display_name,
        )
        query = quote_plus(query_text)
        base_url = self._GOOGLE_NEWS_LOCALES.get(locale_key, self._GOOGLE_NEWS_LOCALES["us"])
        url = base_url.format(query=query)
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
    def _text_or_default(value: Optional[str], default: str) -> str:
        cleaned = (value or "").strip()
        return cleaned or default

    def _parse_publish_date(self, value: Optional[str]) -> str:
        if not value:
            return ""
        try:
            published_dt = parsedate_to_datetime(value)
            return published_dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return ""

    def _clean_summary(self, value: Optional[str]) -> str:
        raw = unescape(value or "")
        without_tags = self._TAG_PATTERN.sub(" ", raw)
        normalized = self._WHITESPACE_PATTERN.sub(" ", without_tags).strip()
        if not normalized:
            return "No summary available."
        return normalized[:280]

    def _score_sentiment(self, *, title: str, summary: str) -> SentimentLabel:
        text = f"{title} {summary}".lower()
        bullish_score = sum(1 for pattern in self._BULLISH_PATTERNS if pattern.search(text))
        bearish_score = sum(1 for pattern in self._BEARISH_PATTERNS if pattern.search(text))

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
        return [kw for kw, pattern in self._RISK_PATTERNS.items() if pattern.search(text)]


@lru_cache
def get_news_analysis_service() -> NewsAnalysisService:
    return NewsAnalysisService()
