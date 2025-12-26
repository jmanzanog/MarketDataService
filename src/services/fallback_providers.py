"""Fallback providers for instrument lookup when primary source fails."""

import logging
import re
from typing import NamedTuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class TickerInfo(NamedTuple):
    """Ticker information from fallback provider."""

    symbol: str
    name: str
    exchange: str
    currency: str


class JustETFProvider:
    """Fallback provider using justETF for European ETFs."""

    BASE_URL = "https://www.justetf.com/en/etf-profile.html"
    TIMEOUT = 10
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    # Mapping of justETF exchange names to Yahoo Finance suffixes
    EXCHANGE_TO_SUFFIX = {
        "XETRA": ".DE",
        "gettex": ".DE",
        "London Stock Exchange": ".L",
        "Euronext Paris": ".PA",
        "Euronext Amsterdam": ".AS",
        "Borsa Italiana": ".MI",
        "SIX Swiss Exchange": ".SW",
    }

    def search_by_isin(self, isin: str) -> TickerInfo | None:
        """
        Search for ETF information by ISIN on justETF.

        Args:
            isin: The ISIN code to search for.

        Returns:
            TickerInfo if found, None otherwise.
        """
        try:
            response = requests.get(
                self.BASE_URL,
                params={"isin": isin},
                headers={"User-Agent": self.USER_AGENT},
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Extract ticker from page
            ticker = self._extract_ticker(soup, response.text)
            if not ticker:
                logger.warning(f"justETF: No ticker found for ISIN {isin}")
                return None

            # Extract name from page title or h1
            name = self._extract_name(soup)

            # Extract exchange and build Yahoo symbol
            exchange, suffix = self._extract_exchange(soup)
            yahoo_symbol = f"{ticker}{suffix}"

            # Extract currency
            currency = self._extract_currency(soup)

            logger.info(f"justETF: Found {yahoo_symbol} for ISIN {isin}")

            return TickerInfo(
                symbol=yahoo_symbol,
                name=name or ticker,
                exchange=exchange or "Unknown",
                currency=currency or "EUR",
            )

        except requests.RequestException as e:
            logger.warning(f"justETF: Request failed for ISIN {isin}: {e}")
            return None
        except Exception as e:
            logger.error(f"justETF: Error parsing ISIN {isin}: {e}")
            return None

    def _extract_ticker(self, soup: BeautifulSoup, html: str) -> str | None:
        """Extract ticker symbol from the page."""
        # Try to find ticker in structured data or text
        # Look for patterns like "Ticker: NATO" or ticker in trade data
        ticker_patterns = [
            r'"ticker"\s*:\s*"([A-Z0-9]+)"',
            r"Ticker[:\s]+([A-Z0-9]{2,10})\b",
            r'data-ticker="([A-Z0-9]+)"',
        ]

        for pattern in ticker_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return None

    def _extract_name(self, soup: BeautifulSoup) -> str | None:
        """Extract ETF name from the page."""
        # Try h1 first
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        # Try title
        title = soup.find("title")
        if title:
            text = title.get_text(strip=True)
            # Remove common suffixes like "| justETF"
            return text.split("|")[0].strip()

        return None

    def _extract_exchange(self, soup: BeautifulSoup) -> tuple[str | None, str]:
        """Extract exchange and determine Yahoo suffix."""
        # Look for exchange mentions in the page
        for exchange_name, suffix in self.EXCHANGE_TO_SUFFIX.items():
            if soup.find(string=lambda t: t and exchange_name in t):
                return exchange_name, suffix

        # Default to London for European ETFs (most liquid)
        return None, ".L"

    def _extract_currency(self, soup: BeautifulSoup) -> str | None:
        """Extract trading currency from the page."""
        # Look for currency indicators
        currency_pattern = r"\b(EUR|USD|GBP|CHF)\b"
        text = soup.get_text()
        match = re.search(currency_pattern, text)
        return match.group(1) if match else None


# Singleton instance
justetf_provider = JustETFProvider()
