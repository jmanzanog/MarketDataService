"""Yahoo Finance service using yfinance library."""

import logging
from datetime import UTC, datetime

import yfinance as yf

from src.models.schemas import InstrumentResponse, QuoteResponse

logger = logging.getLogger(__name__)


class YahooFinanceService:
    """Service class to interact with Yahoo Finance via yfinance library."""

    # Mapping of exchange suffixes to full names
    EXCHANGE_MAP = {
        "L": "London Stock Exchange",
        "DE": "Deutsche Börse",
        "PA": "Euronext Paris",
        "AS": "Euronext Amsterdam",
        "BR": "Euronext Brussels",
        "MI": "Borsa Italiana",
        "MC": "Bolsa de Madrid",
        "SW": "SIX Swiss Exchange",
        "TO": "Toronto Stock Exchange",
        "V": "TSX Venture Exchange",
        "AX": "Australian Securities Exchange",
        "HK": "Hong Kong Stock Exchange",
        "T": "Tokyo Stock Exchange",
        "SS": "Shanghai Stock Exchange",
        "SZ": "Shenzhen Stock Exchange",
    }

    def search_by_isin(self, isin: str) -> InstrumentResponse | None:
        """
        Search for an instrument by its ISIN code.

        Args:
            isin: The ISIN code to search for.

        Returns:
            InstrumentResponse if found, None otherwise.
        """
        try:
            # yfinance search endpoint
            search_result = yf.Search(isin, news_count=0, quotes_count=5)

            if not search_result.quotes:
                logger.warning(f"No results found for ISIN: {isin}")
                return None

            # Get the first matching quote
            quote = search_result.quotes[0]
            symbol = quote.get("symbol", "")

            if not symbol:
                logger.warning(f"No symbol found in search result for ISIN: {isin}")
                return None

            # Fetch detailed ticker info
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Determine instrument type
            quote_type = info.get("quoteType", "EQUITY")
            instrument_type = "etf" if quote_type == "ETF" else "stock"

            # Extract exchange from symbol suffix or info
            exchange = self._extract_exchange(symbol, info)

            # Get currency
            currency = info.get("currency", "USD")

            return InstrumentResponse(
                isin=isin,
                symbol=symbol,
                name=info.get("longName", info.get("shortName", quote.get("shortname", symbol))),
                type=instrument_type,
                currency=currency,
                exchange=exchange,
            )

        except Exception as e:
            logger.error(f"Error searching for ISIN {isin}: {e}")
            raise

    def get_quote(self, symbol: str) -> QuoteResponse | None:
        """
        Get current quote for a symbol.

        Args:
            symbol: The trading symbol (ticker).

        Returns:
            QuoteResponse if found, None otherwise.
        """
        try:
            ticker = yf.Ticker(symbol)

            # Try fast_info first (faster), fall back to info
            try:
                fast_info = ticker.fast_info
                price = fast_info.get("lastPrice") or fast_info.get("regularMarketPrice")
                currency = fast_info.get("currency", "USD")
            except Exception:
                info = ticker.info
                price = info.get("regularMarketPrice") or info.get("currentPrice")
                currency = info.get("currency", "USD")

            if price is None:
                logger.warning(f"No price data found for symbol: {symbol}")
                return None

            # Format price with 4 decimal places for consistency
            price_str = f"{price:.4f}"

            return QuoteResponse(
                symbol=symbol,
                price=price_str,
                currency=currency,
                time=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            logger.error(f"Error getting quote for symbol {symbol}: {e}")
            raise

    def _extract_exchange(self, symbol: str, info: dict) -> str:
        """Extract exchange name from symbol suffix or ticker info."""
        # First try to get from info
        exchange = info.get("exchange", "")
        if exchange:
            return exchange

        # Fall back to extracting from symbol suffix
        if "." in symbol:
            suffix = symbol.split(".")[-1]
            return self.EXCHANGE_MAP.get(suffix, suffix)

        # Default to US exchanges for symbols without suffix
        return "NYSE/NASDAQ"


# Singleton instance
yahoo_finance_service = YahooFinanceService()
