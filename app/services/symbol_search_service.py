"""
Yahoo Finance symbol search for autocomplete / typeahead UIs.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Final
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.services.asset_registry import (
    MARKET_UNIVERSES,
    InvalidSymbolError,
    classify_asset,
    display_exchange,
    display_ticker,
    market_for_asset_class,
    resolve_display_name,
    resolve_market,
)

logger = logging.getLogger(__name__)

YAHOO_SEARCH_URL: Final[str] = "https://query1.finance.yahoo.com/v1/finance/search"
_USER_AGENT: Final[str] = "Mozilla/5.0 (compatible; NexusAI/1.0)"
_MAX_QUERY_LENGTH: Final[int] = 64
_DEFAULT_LIMIT: Final[int] = 8
_MAX_LIMIT: Final[int] = 15

_MARKET_UNIVERSE_SETS: Final[dict[str, frozenset[str]]] = {
    market: frozenset(symbols) for market, symbols in MARKET_UNIVERSES.items()
}
_US_EXCHANGES: Final[frozenset[str]] = frozenset(
    {"NMS", "NYQ", "NGM", "NCM", "PCX", "ASE", "BTS", "NAS", "NYSE"}
)
_INDIA_EXCHANGES: Final[frozenset[str]] = frozenset({"NSI", "BSE"})


class SymbolSearchError(Exception):
    """Raised when symbol search fails."""


class SymbolSearchService:
    def search(
        self,
        query: str,
        market: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        cleaned = query.strip()
        if not cleaned:
            return self._empty_payload(cleaned, resolve_market(market))

        if len(cleaned) > _MAX_QUERY_LENGTH:
            raise SymbolSearchError(
                f"Search query must be at most {_MAX_QUERY_LENGTH} characters."
            )

        market_key = resolve_market(market)
        bounded_limit = max(1, min(limit, _MAX_LIMIT))
        quotes = self._fetch_yahoo_quotes(cleaned, bounded_limit * 4)

        universe_set = _MARKET_UNIVERSE_SETS[market_key]
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        for quote in quotes:
            raw_symbol = quote.get("symbol")
            if not isinstance(raw_symbol, str) or not raw_symbol.strip():
                continue

            try:
                normalized = self._normalize_search_symbol(raw_symbol.strip())
            except InvalidSymbolError:
                continue

            if normalized in seen:
                continue
            if market_for_asset_class(classify_asset(normalized)) != market_key:
                continue
            if not self._quote_matches_market(
                normalized,
                quote.get("exchange") if isinstance(quote.get("exchange"), str) else None,
                market_key,
            ):
                continue

            seen.add(normalized)
            yahoo_name = quote.get("longname") or quote.get("shortname")
            name = (
                yahoo_name.strip()
                if isinstance(yahoo_name, str) and yahoo_name.strip()
                else resolve_display_name(normalized)
            )

            results.append(
                {
                    "ticker": normalized,
                    "display_ticker": display_ticker(normalized),
                    "name": name,
                    "exchange": display_exchange(
                        quote.get("exchange") if isinstance(quote.get("exchange"), str) else None
                    ),
                    "in_universe": normalized in universe_set,
                }
            )
            if len(results) >= bounded_limit:
                break

        return {
            "query": cleaned,
            "market": market_key,
            "count": len(results),
            "results": results,
        }

    @staticmethod
    def _normalize_search_symbol(symbol: str) -> str:
        from app.services.asset_registry import normalize_symbol

        return normalize_symbol(symbol)

    def _fetch_yahoo_quotes(self, query: str, quote_count: int) -> list[dict[str, Any]]:
        url = (
            f"{YAHOO_SEARCH_URL}?q={quote(query)}"
            f"&quotesCount={quote_count}&newsCount=0&enableFuzzyQuery=true"
        )
        request = Request(url, headers={"User-Agent": _USER_AGENT})

        try:
            with urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            logger.warning("Yahoo symbol search failed for query %r: %s", query, exc)
            raise SymbolSearchError("Failed to fetch symbol suggestions from Yahoo Finance.") from exc

        quotes = payload.get("quotes")
        if not isinstance(quotes, list):
            return []
        return [q for q in quotes if isinstance(q, dict)]

    @staticmethod
    def _quote_matches_market(
        normalized_symbol: str,
        exchange: str | None,
        market_key: str,
    ) -> bool:
        exch = exchange.strip().upper() if exchange else None

        if market_key == "us_stocks":
            if "." in normalized_symbol:
                return False
            return exch is None or exch in _US_EXCHANGES

        if market_key == "india_stocks":
            if normalized_symbol.endswith(".NS") or normalized_symbol.endswith(".BO"):
                return True
            return exch is None or exch in _INDIA_EXCHANGES

        return True

    @staticmethod
    def _empty_payload(query: str, market_key: str) -> dict[str, Any]:
        return {"query": query, "market": market_key, "count": 0, "results": []}


@lru_cache
def get_symbol_search_service() -> SymbolSearchService:
    return SymbolSearchService()
