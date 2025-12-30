"""Fallback providers for instrument lookup when primary source fails."""

import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import redis
import requests
from bs4 import BeautifulSoup

from src.config import settings

logger = logging.getLogger(__name__)


class TickerInfo(NamedTuple):
    """Ticker information from fallback provider."""

    symbol: str
    name: str
    exchange: str
    currency: str

    def to_dict(self):
        return self._asdict()

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


class MetadataCache:
    """Caching service for instrument metadata."""

    def __init__(self):
        try:
            self.redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            # Connectivity probe
            self.redis.ping()
            self.enabled = True
            logger.info("Metadata cache (Redis) initialized.")
        except Exception as e:
            logger.warning(f"Redis not available, caching disabled: {e}")
            self.redis = None
            self.enabled = False

    def get(self, isin: str) -> TickerInfo | None:
        if not self.enabled:
            return None
        try:
            data = self.redis.get(f"metadata:{isin}")
            if data:
                logger.debug(f"Cache hit for ISIN {isin}")
                return TickerInfo.from_dict(json.loads(data))
        except Exception as e:
            logger.error(f"Error reading from cache: {e}")
        return None

    def set(self, isin: str, info: TickerInfo):
        if not self.enabled:
            return
        try:
            self.redis.setex(
                f"metadata:{isin}",
                settings.cache_expire_seconds,
                json.dumps(info.to_dict()),
            )
            logger.debug(f"Cached metadata for ISIN {isin}")
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")


metadata_cache = MetadataCache()


class BaseDiscoveryProvider(ABC):
    """Interface for alternative instrument discovery providers."""

    @abstractmethod
    def search_by_isin(self, isin: str) -> TickerInfo | None:
        """Search for an instrument by ISIN."""
        pass


class JustETFProvider(BaseDiscoveryProvider):
    """Fallback provider using justETF for European ETFs with Circuit Breaker logic."""

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

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        # Simple Circuit Breaker state
        self.blocked_until = None

    def _is_blocked(self) -> bool:
        """Check if we are in a 'cool down' period due to blocks."""
        if self.blocked_until and datetime.now(UTC) < self.blocked_until:
            return True
        self.blocked_until = None
        return False

    def search_by_isin(self, isin: str) -> TickerInfo | None:
        """
        Search for ETF information by ISIN on justETF.
        Checks cache first, then respects Circuit Breaker.
        """
        # 1. Check Cache
        cached = metadata_cache.get(isin)
        if cached:
            return cached

        # 2. Check Circuit Breaker
        if self._is_blocked():
            logger.warning(f"JustETF provider is temporarily blocked. Skipping search for {isin}")
            return None

        # 3. Perform Scraping
        try:
            response = self.session.get(
                self.BASE_URL,
                params={"isin": isin},
                timeout=self.TIMEOUT,
            )

            if response.status_code == 403:
                logger.error("justETF returned 403. Triping circuit breaker for 10 minutes.")
                self.blocked_until = datetime.now(UTC) + timedelta(minutes=10)
                return None

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

            info = TickerInfo(
                symbol=yahoo_symbol,
                name=name or ticker,
                exchange=exchange or "Unknown",
                currency=currency or "EUR",
            )

            # Save to cache
            metadata_cache.set(isin, info)

            return info

        except requests.RequestException as e:
            logger.warning(f"justETF: Request failed for ISIN {isin}: {e}")
            return None
        except Exception as e:
            logger.error(f"justETF: Error parsing ISIN {isin}: {e}")
            return None

    def _extract_ticker(self, soup: BeautifulSoup, html: str) -> str | None:
        """Extract ticker symbol from the page."""
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
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        title = soup.find("title")
        if title:
            text = title.get_text(strip=True)
            return text.split("|")[0].strip()

        return None

    def _extract_exchange(self, soup: BeautifulSoup) -> tuple[str | None, str]:
        """Extract exchange and determine Yahoo suffix."""
        for exchange_name, suffix in self.EXCHANGE_TO_SUFFIX.items():
            if soup.find(string=lambda t, en=exchange_name: t and en in t):
                return exchange_name, suffix

        return None, ".L"

    def _extract_currency(self, soup: BeautifulSoup) -> str | None:
        """Extract trading currency from the page."""
        currency_pattern = r"\b(EUR|USD|GBP|CHF)\b"
        text = soup.get_text()
        match = re.search(currency_pattern, text)
        return match.group(1) if match else None


# Singleton instance
justetf_provider = JustETFProvider()
