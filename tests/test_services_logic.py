"""
Unit tests for internal service logic, including ISIN validation,
caching, and circuit breaker mechanisms.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
import responses
from bs4 import BeautifulSoup
from fakeredis import FakeRedis

from src.services.fallback_providers import JustETFProvider, MetadataCache, TickerInfo
from src.services.yahoo_finance import is_valid_isin, yahoo_finance_service


class TestISINValidation:
    """Tests for ISIN validation logic."""

    def test_valid_isins(self):
        assert is_valid_isin("US0378331005") is True  # Apple
        assert is_valid_isin("IE00BK5BQT80") is True  # VWRA
        assert is_valid_isin("DE0007164600") is True  # SAP
        assert is_valid_isin("cne100000296") is True  # Mixed case

    def test_invalid_isins(self):
        assert is_valid_isin("INVALID") is False
        assert is_valid_isin("US123456789") is False  # Too short
        assert is_valid_isin("US123456789012") is False  # Too long
        assert is_valid_isin("") is False
        assert is_valid_isin(None) is False


class TestMetadataCache:
    """Tests for the Redis-based metadata cache."""

    @pytest.fixture
    def mock_cache(self):
        cache = MetadataCache()
        cache.redis = FakeRedis(decode_responses=True)
        cache.enabled = True
        return cache

    def test_set_and_get_cache(self, mock_cache):
        info = TickerInfo(symbol="AAPL", name="Apple Inc.", exchange="NASDAQ", currency="USD")
        mock_cache.set("US0378331005", info)

        cached = mock_cache.get("US0378331005")
        assert cached == info
        assert cached.symbol == "AAPL"

    def test_get_non_existent(self, mock_cache):
        assert mock_cache.get("NONEXISTENT") is None

    def test_cache_disabled(self, mock_cache):
        mock_cache.enabled = False
        info = TickerInfo(symbol="A", name="B", exchange="C", currency="D")
        mock_cache.set("KEY", info)
        assert mock_cache.get("KEY") is None


class TestJustETFProviderResilience:
    """Tests for JustETFProvider's circuit breaker and error handling."""

    @pytest.fixture
    def provider(self):
        with patch("src.services.fallback_providers.metadata_cache.enabled", False):
            return JustETFProvider()

    def test_circuit_breaker_trips_on_403(self, provider):
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, provider.BASE_URL, status=403)

            # First call should trip it
            result = provider.search_by_isin("IE00BK5BQT80")
            assert result is None
            assert provider._is_blocked() is True

            # Subsequent calls should be blocked immediately
            result2 = provider.search_by_isin("IE00BK5BQT80")
            assert result2 is None
            assert len(rsps.calls) == 1  # Only one request made

    def test_circuit_breaker_expiration(self, provider):
        # Set block in the past
        provider.blocked_until = datetime.now(UTC) - timedelta(minutes=1)
        assert provider._is_blocked() is False
        assert provider.blocked_until is None

    @responses.activate
    def test_handle_scraper_error(self, provider):
        responses.add(responses.GET, provider.BASE_URL, status=500)
        result = provider.search_by_isin("IE00BK5BQT80")
        assert result is None


class TestJustETFParsing:
    """Tests for the HTML parsing logic of JustETFProvider."""

    @pytest.fixture
    def provider(self):
        return JustETFProvider()

    def test_extract_ticker(self, provider):
        html = '<div data-ticker="VWRA"></div>'
        soup = BeautifulSoup(html, "html.parser")
        assert provider._extract_ticker(soup, html) == "VWRA"

        html2 = "<span>Ticker: NATO</span>"
        soup2 = BeautifulSoup(html2, "html.parser")
        assert provider._extract_ticker(soup2, html2) == "NATO"

    def test_extract_name(self, provider):
        html = "<h1>Vanguard FTSE All-World</h1>"
        soup = BeautifulSoup(html, "html.parser")
        assert provider._extract_name(soup) == "Vanguard FTSE All-World"

        html2 = "<title>iShares Core MSCI World | justETF</title>"
        soup2 = BeautifulSoup(html2, "html.parser")
        assert provider._extract_name(soup2) == "iShares Core MSCI World"

    def test_extract_exchange(self, provider):
        # Test XETRA detection
        html = "<div>Trading on XETRA exchange</div>"
        soup = BeautifulSoup(html, "html.parser")
        name, suffix = provider._extract_exchange(soup)
        assert name == "XETRA"
        assert suffix == ".DE"

        # Test London fallback
        html2 = "<div>No specific exchange mentioned</div>"
        soup2 = BeautifulSoup(html2, "html.parser")
        name2, suffix2 = provider._extract_exchange(soup2)
        assert name2 is None
        assert suffix2 == ".L"

    def test_extract_currency(self, provider):
        html = "<div>The currency is USD</div>"
        soup = BeautifulSoup(html, "html.parser")
        assert provider._extract_currency(soup) == "USD"

        html2 = "<div>Trading in EUR</div>"
        soup2 = BeautifulSoup(html2, "html.parser")
        assert provider._extract_currency(soup2) == "EUR"


class TestYahooFinanceServiceExtensions:
    """Tests for new logic in YahooFinanceService."""

    def test_search_by_isin_validates_input(self):
        # Should return None immediately for invalid ISIN
        result = yahoo_finance_service.search_by_isin("INVALID")
        assert result is None

    @patch("src.services.yahoo_finance.yf.Search")
    @patch("src.services.yahoo_finance.yahoo_finance_service._try_justetf_fallback")
    def test_search_by_isin_calls_justetf_on_no_results(self, mock_fallback, mock_yf_search):
        mock_yf_search.return_value.quotes = []
        isin = "US0378331005"

        yahoo_finance_service.search_by_isin(isin)

        mock_fallback.assert_called_once_with(isin)

    @patch("src.services.yahoo_finance.justetf_provider.search_by_isin")
    @patch("src.services.yahoo_finance.yahoo_finance_service._try_get_instrument_info")
    @patch("src.services.yahoo_finance.yahoo_finance_service._try_search_by_name_fallback")
    def test_justetf_fallback_final_name_resort(self, mock_name_search, mock_info, mock_justetf):
        # Simulate justETF found something but Yahoo info failed
        mock_justetf.return_value = TickerInfo(
            symbol="TEST", name="Test Name", exchange="Ex", currency="USD"
        )
        mock_info.return_value = None  # All Yahoo ticker attempts failed

        isin = "US1234567890"
        yahoo_finance_service._try_justetf_fallback(isin)

        # Should have tried name search as last resort
        mock_name_search.assert_called_once_with(isin, "Test Name")
