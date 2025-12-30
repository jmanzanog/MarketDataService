"""Comprehensive tests for the Market Data Service API with 100% coverage."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.schemas import InstrumentResponse, QuoteResponse

client = TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check_returns_healthy(self):
        """Test that health check returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_root_endpoint_returns_api_info(self):
        """Test that root endpoint returns API information."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs" in data
        assert data["docs"] == "/docs"


class TestSearchEndpoint:
    """Tests for the search endpoint."""

    @patch("src.routes.search.yahoo_finance_service")
    def test_search_by_isin_success(self, mock_service):
        """Test successful ISIN search."""
        mock_service.search_by_isin.return_value = InstrumentResponse(
            isin="US0378331005",
            symbol="AAPL",
            name="Apple Inc.",
            type="stock",
            currency="USD",
            exchange="NASDAQ",
        )

        response = client.get("/api/v1/search/US0378331005")

        assert response.status_code == 200
        data = response.json()
        assert data["isin"] == "US0378331005"
        assert data["symbol"] == "AAPL"
        assert data["name"] == "Apple Inc."
        assert data["type"] == "stock"
        assert data["currency"] == "USD"
        mock_service.search_by_isin.assert_called_once_with("US0378331005")

    @patch("src.routes.search.yahoo_finance_service")
    def test_search_by_isin_not_found(self, mock_service):
        """Test ISIN search when instrument not found."""
        mock_service.search_by_isin.return_value = None

        response = client.get("/api/v1/search/US1234567891")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "US1234567891" in data["detail"]

    @patch("src.routes.search.yahoo_finance_service")
    def test_search_by_isin_service_error(self, mock_service):
        """Test ISIN search when service throws an exception."""
        mock_service.search_by_isin.side_effect = Exception("API Error")

        response = client.get("/api/v1/search/US0378331005")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "API Error" in data["detail"]


class TestQuoteEndpoint:
    """Tests for the quote endpoint."""

    @patch("src.routes.quote.yahoo_finance_service")
    def test_get_quote_success(self, mock_service):
        """Test successful quote retrieval."""
        mock_service.get_quote.return_value = QuoteResponse(
            symbol="AAPL",
            price="195.5000",
            currency="USD",
            time="2024-12-24T15:00:00+00:00",
        )

        response = client.get("/api/v1/quote/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["price"] == "195.5000"
        assert data["currency"] == "USD"
        mock_service.get_quote.assert_called_once_with("AAPL")

    @patch("src.routes.quote.yahoo_finance_service")
    def test_get_quote_not_found(self, mock_service):
        """Test quote when symbol not found."""
        mock_service.get_quote.return_value = None

        response = client.get("/api/v1/quote/INVALID")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "INVALID" in data["detail"]

    @patch("src.routes.quote.yahoo_finance_service")
    def test_get_quote_service_error(self, mock_service):
        """Test quote when service throws an exception."""
        mock_service.get_quote.side_effect = Exception("Network Error")

        response = client.get("/api/v1/quote/AAPL")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "Network Error" in data["detail"]


class TestYahooFinanceServiceSearch:
    """Tests for the Yahoo Finance service search_by_isin method."""

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_success(self, mock_yf, mock_justetf):
        """Test successful ISIN search with mocked yfinance."""
        from src.services.yahoo_finance import YahooFinanceService

        # Mock Search result
        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "AAPL", "shortname": "Apple Inc"}]
        mock_yf.Search.return_value = mock_search

        # Mock Ticker info with price (required for valid result)
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "longName": "Apple Inc.",
            "currency": "USD",
            "exchange": "NASDAQ",
            "regularMarketPrice": 195.50,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.search_by_isin("US0378331005")

        assert result is not None
        assert result.isin == "US0378331005"
        assert result.symbol == "AAPL"
        assert result.name == "Apple Inc."
        assert result.type == "stock"
        assert result.currency == "USD"
        assert result.exchange == "NASDAQ"

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_etf_type(self, mock_yf, mock_justetf):
        """Test ISIN search for ETF type."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "VOO"}]
        mock_yf.Search.return_value = mock_search

        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "ETF",
            "longName": "Vanguard S&P 500 ETF",
            "currency": "USD",
            "exchange": "NYSE ARCA",
            "regularMarketPrice": 450.00,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.search_by_isin("US9229087690")

        assert result is not None
        assert result.type == "etf"

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_no_results(self, mock_yf, mock_justetf):
        """Test ISIN search with no results falls back to justETF."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = []
        mock_yf.Search.return_value = mock_search

        # justETF also returns None
        mock_justetf.search_by_isin.return_value = None

        service = YahooFinanceService()
        result = service.search_by_isin("US1234567891")

        assert result is None
        mock_justetf.search_by_isin.assert_called_once_with("US1234567891")

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_no_symbol_in_quote(self, mock_yf, mock_justetf):
        """Test ISIN search when quote has no symbol falls back to justETF."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = [{"shortname": "Test"}]  # No symbol
        mock_yf.Search.return_value = mock_search

        mock_justetf.search_by_isin.return_value = None

        service = YahooFinanceService()
        result = service.search_by_isin("US0378331005")

        assert result is None

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_uses_shortname_fallback(self, mock_yf, mock_justetf):
        """Test ISIN search uses shortName as fallback for name."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "TEST", "shortname": "Test Company"}]
        mock_yf.Search.return_value = mock_search

        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "shortName": "Test Co",  # No longName
            "currency": "EUR",
            "exchange": "",
            "regularMarketPrice": 100.00,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.search_by_isin("US1234567895")

        assert result is not None
        assert result.name == "Test Co"

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_uses_quote_shortname_fallback(self, mock_yf, mock_justetf):
        """Test ISIN search uses quote shortname when info has no name."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "TEST", "shortname": "Fallback Name"}]
        mock_yf.Search.return_value = mock_search

        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "currency": "GBP",
            "regularMarketPrice": 50.00,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.search_by_isin("US1234567895")

        assert result is not None
        assert result.name == "Fallback Name"

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_symbol_fallback_for_name(self, mock_yf, mock_justetf):
        """Test ISIN search uses symbol when no name available."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "NONAME"}]
        mock_yf.Search.return_value = mock_search

        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "currency": "USD",
            "regularMarketPrice": 25.00,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.search_by_isin("US1234567895")

        assert result is not None
        assert result.name == "NONAME"

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_extract_exchange_from_symbol(self, mock_yf, mock_justetf):
        """Test ISIN search extracts exchange from symbol suffix."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "RR.L"}]
        mock_yf.Search.return_value = mock_search

        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "longName": "Rolls-Royce",
            "currency": "GBP",
            "exchange": "",  # Empty exchange
            "regularMarketPrice": 5.50,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.search_by_isin("GB00B63H8491")

        assert result is not None
        assert result.exchange == "London Stock Exchange"

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_default_exchange_for_us_stock(self, mock_yf, mock_justetf):
        """Test ISIN search defaults to NYSE/NASDAQ for US stocks."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "AAPL"}]  # No suffix
        mock_yf.Search.return_value = mock_search

        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "longName": "Apple",
            "currency": "USD",
            "exchange": "",
            "regularMarketPrice": 195.00,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.search_by_isin("US0378331005")

        assert result is not None
        assert result.exchange == "NYSE/NASDAQ"

    @patch("src.services.yahoo_finance.yf")
    def test_search_by_isin_exception_raised(self, mock_yf):
        """Test ISIN search raises exception on error."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_yf.Search.side_effect = Exception("Network timeout")

        service = YahooFinanceService()

        with pytest.raises(Exception) as exc_info:
            service.search_by_isin("US0378331005")

        assert "Network timeout" in str(exc_info.value)


class TestYahooFinanceServiceQuote:
    """Tests for the Yahoo Finance service get_quote method."""

    @patch("src.services.yahoo_finance.yf")
    def test_get_quote_success_with_fast_info(self, mock_yf):
        """Test successful quote retrieval using fast_info."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_ticker = MagicMock()
        # fast_info is dict-like, mock .get() method
        mock_fast_info = MagicMock()
        mock_fast_info.get.side_effect = lambda key, default=None: {
            "lastPrice": 195.50,
            "currency": "USD",
        }.get(key, default)
        mock_ticker.fast_info = mock_fast_info
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.get_quote("AAPL")

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.price == "195.5000"
        assert result.currency == "USD"

    @patch("src.services.yahoo_finance.yf")
    def test_get_quote_uses_regular_market_price(self, mock_yf):
        """Test quote uses regularMarketPrice from fast_info."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_ticker = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.get.side_effect = lambda key, default=None: {
            "lastPrice": None,  # No lastPrice
            "regularMarketPrice": 100.25,
            "currency": "EUR",
        }.get(key, default)
        mock_ticker.fast_info = mock_fast_info
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.get_quote("BMW.DE")

        assert result is not None
        assert result.price == "100.2500"
        assert result.currency == "EUR"

    @patch("src.services.yahoo_finance.yf")
    def test_get_quote_fallback_to_info(self, mock_yf):
        """Test quote falls back to info when fast_info fails."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_ticker = MagicMock()
        # fast_info.get raises exception
        mock_fast_info = MagicMock()
        mock_fast_info.get.side_effect = Exception("fast_info error")
        mock_ticker.fast_info = mock_fast_info
        mock_ticker.info = {
            "regularMarketPrice": 50.00,
            "currency": "GBP",
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.get_quote("RR.L")

        assert result is not None
        assert result.price == "50.0000"
        assert result.currency == "GBP"

    @patch("src.services.yahoo_finance.yf")
    def test_get_quote_uses_current_price_fallback(self, mock_yf):
        """Test quote uses currentPrice when regularMarketPrice not available."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_ticker = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.get.side_effect = Exception("error")
        mock_ticker.fast_info = mock_fast_info
        mock_ticker.info = {
            "currentPrice": 75.50,
            "currency": "USD",
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.get_quote("TEST")

        assert result is not None
        assert result.price == "75.5000"

    @patch("src.services.yahoo_finance.yf")
    def test_get_quote_no_price_data(self, mock_yf):
        """Test quote returns None when no price data available."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_ticker = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.get.side_effect = Exception("error")
        mock_ticker.fast_info = mock_fast_info
        mock_ticker.info = {}  # No price data
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.get_quote("INVALID")

        assert result is None

    @patch("src.services.yahoo_finance.yf")
    def test_get_quote_default_currency(self, mock_yf):
        """Test quote uses USD as default currency."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_ticker = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.get.side_effect = lambda key, default=None: {
            "lastPrice": 100.00,
        }.get(key, default)
        mock_ticker.fast_info = mock_fast_info
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.get_quote("TEST")

        assert result is not None
        assert result.currency == "USD"

    @patch("src.services.yahoo_finance.yf")
    def test_get_quote_exception_raised(self, mock_yf):
        """Test quote raises exception on error."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_yf.Ticker.side_effect = Exception("Connection refused")

        service = YahooFinanceService()

        with pytest.raises(Exception) as exc_info:
            service.get_quote("AAPL")

        assert "Connection refused" in str(exc_info.value)


class TestYahooFinanceServiceExchange:
    """Tests for the Yahoo Finance service exchange extraction."""

    def test_extract_exchange_all_mappings(self):
        """Test exchange extraction for all known suffixes."""
        from src.services.yahoo_finance import YahooFinanceService

        service = YahooFinanceService()

        # Test all exchange mappings
        test_cases = [
            ("RR.L", {}, "London Stock Exchange"),
            ("BMW.DE", {}, "Deutsche Börse"),
            ("AIR.PA", {}, "Euronext Paris"),
            ("ASML.AS", {}, "Euronext Amsterdam"),
            ("TEST.BR", {}, "Euronext Brussels"),
            ("ENI.MI", {}, "Borsa Italiana"),
            ("TEF.MC", {}, "Bolsa de Madrid"),
            ("NESN.SW", {}, "SIX Swiss Exchange"),
            ("TD.TO", {}, "Toronto Stock Exchange"),
            ("TEST.V", {}, "TSX Venture Exchange"),
            ("BHP.AX", {}, "Australian Securities Exchange"),
            ("0941.HK", {}, "Hong Kong Stock Exchange"),
            ("7203.T", {}, "Tokyo Stock Exchange"),
            ("600000.SS", {}, "Shanghai Stock Exchange"),
            ("000001.SZ", {}, "Shenzhen Stock Exchange"),
            ("AAPL", {}, "NYSE/NASDAQ"),  # No suffix
            ("TEST.XX", {}, "XX"),  # Unknown suffix
        ]

        for symbol, info, expected_exchange in test_cases:
            result = service._extract_exchange(symbol, info)
            assert result == expected_exchange, f"Failed for {symbol}"

    def test_extract_exchange_from_info(self):
        """Test exchange extraction prioritizes info over symbol."""
        from src.services.yahoo_finance import YahooFinanceService

        service = YahooFinanceService()

        result = service._extract_exchange("RR.L", {"exchange": "LSE"})
        assert result == "LSE"


class TestConfig:
    """Tests for configuration module."""

    def test_settings_defaults(self):
        """Test that settings have proper defaults."""
        from src.config import settings

        assert settings.app_name == "Market Data Service"
        assert settings.app_version == "1.0.0"
        assert settings.host == "127.0.0.1"
        assert settings.port == 8000
        assert settings.log_level == "INFO"

    def test_settings_debug_default(self):
        """Test debug default is False."""
        from src.config import settings

        assert settings.debug is False


class TestSchemas:
    """Tests for Pydantic schemas."""

    def test_instrument_response_creation(self):
        """Test InstrumentResponse model creation."""
        from src.models.schemas import InstrumentResponse

        instrument = InstrumentResponse(
            isin="US0378331005",
            symbol="AAPL",
            name="Apple Inc.",
            type="stock",
            currency="USD",
            exchange="NASDAQ",
        )

        assert instrument.isin == "US0378331005"
        assert instrument.symbol == "AAPL"

    def test_quote_response_creation(self):
        """Test QuoteResponse model creation."""
        from src.models.schemas import QuoteResponse

        quote = QuoteResponse(
            symbol="AAPL",
            price="195.50",
            currency="USD",
            time="2024-12-24T15:00:00Z",
        )

        assert quote.symbol == "AAPL"
        assert quote.price == "195.50"

    def test_health_response_creation(self):
        """Test HealthResponse model creation."""
        from src.models.schemas import HealthResponse

        health = HealthResponse(status="healthy", version="1.0.0")

        assert health.status == "healthy"
        assert health.version == "1.0.0"

    def test_error_response_creation(self):
        """Test ErrorResponse model creation."""
        from src.models.schemas import ErrorResponse

        error = ErrorResponse(error="Not found", detail="Resource not found")

        assert error.error == "Not found"
        assert error.detail == "Resource not found"

    def test_error_response_optional_detail(self):
        """Test ErrorResponse with optional detail."""
        from src.models.schemas import ErrorResponse

        error = ErrorResponse(error="Server error")

        assert error.error == "Server error"
        assert error.detail is None


class TestBatchSearchEndpoint:
    """Tests for the batch search endpoint."""

    @patch("src.routes.search.yahoo_finance_service")
    def test_batch_search_success(self, mock_service):
        """Test successful batch ISIN search."""
        from src.models.schemas import InstrumentResponse

        # Mock the async method
        async def mock_batch_search(isins):
            return (
                [
                    InstrumentResponse(
                        isin="US0378331005",
                        symbol="AAPL",
                        name="Apple Inc.",
                        type="stock",
                        currency="USD",
                        exchange="NASDAQ",
                    ),
                    InstrumentResponse(
                        isin="DE0007164600",
                        symbol="SAP",
                        name="SAP SE",
                        type="stock",
                        currency="EUR",
                        exchange="XETRA",
                    ),
                ],
                [],
            )

        mock_service.batch_search_by_isins = mock_batch_search

        response = client.post(
            "/api/v1/search/batch",
            json={"isins": ["US0378331005", "DE0007164600"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert len(data["errors"]) == 0
        assert data["results"][0]["isin"] == "US0378331005"
        assert data["results"][1]["isin"] == "DE0007164600"

    @patch("src.routes.search.yahoo_finance_service")
    def test_batch_search_partial_errors(self, mock_service):
        """Test batch search with some ISINs not found."""
        from src.models.schemas import InstrumentResponse

        async def mock_batch_search(isins):
            return (
                [
                    InstrumentResponse(
                        isin="US0378331005",
                        symbol="AAPL",
                        name="Apple Inc.",
                        type="stock",
                        currency="USD",
                        exchange="NASDAQ",
                    ),
                ],
                [("US1234567891", "No instrument found for ISIN")],
            )

        mock_service.batch_search_by_isins = mock_batch_search

        response = client.post(
            "/api/v1/search/batch",
            json={"isins": ["US0378331005", "US1234567891"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["isin"] == "US1234567891"
        assert "No instrument found" in data["errors"][0]["error"]

    @patch("src.routes.search.yahoo_finance_service")
    def test_batch_search_all_errors(self, mock_service):
        """Test batch search when all ISINs fail."""

        async def mock_batch_search(isins):
            return (
                [],
                [
                    ("US1234567892", "No instrument found for ISIN"),
                    ("US1234567893", "No instrument found for ISIN"),
                ],
            )

        mock_service.batch_search_by_isins = mock_batch_search

        response = client.post(
            "/api/v1/search/batch",
            json={"isins": ["US1234567892", "US1234567893"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 0
        assert len(data["errors"]) == 2

    @patch("src.routes.search.yahoo_finance_service")
    def test_batch_search_service_error(self, mock_service):
        """Test batch search when service throws an exception."""

        async def mock_batch_search(isins):
            raise Exception("Service unavailable")

        mock_service.batch_search_by_isins = mock_batch_search

        response = client.post(
            "/api/v1/search/batch",
            json={"isins": ["US0378331005"]},
        )

        assert response.status_code == 500
        data = response.json()
        assert "Service unavailable" in data["detail"]


class TestBatchQuoteEndpoint:
    """Tests for the batch quote endpoint."""

    @patch("src.routes.quote.yahoo_finance_service")
    def test_batch_quote_success(self, mock_service):
        """Test successful batch quote retrieval."""
        from src.models.schemas import QuoteResponse

        async def mock_batch_quotes(symbols):
            return (
                [
                    QuoteResponse(
                        symbol="AAPL",
                        price="193.4200",
                        currency="USD",
                        time="2025-12-26T10:30:00Z",
                    ),
                    QuoteResponse(
                        symbol="SAP",
                        price="142.5000",
                        currency="EUR",
                        time="2025-12-26T10:30:00Z",
                    ),
                ],
                [],
            )

        mock_service.batch_get_quotes = mock_batch_quotes

        response = client.post(
            "/api/v1/quote/batch",
            json={"symbols": ["AAPL", "SAP"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert len(data["errors"]) == 0
        assert data["results"][0]["symbol"] == "AAPL"
        assert data["results"][1]["symbol"] == "SAP"

    @patch("src.routes.quote.yahoo_finance_service")
    def test_batch_quote_partial_errors(self, mock_service):
        """Test batch quote with some symbols not found."""
        from src.models.schemas import QuoteResponse

        async def mock_batch_quotes(symbols):
            return (
                [
                    QuoteResponse(
                        symbol="AAPL",
                        price="193.4200",
                        currency="USD",
                        time="2025-12-26T10:30:00Z",
                    ),
                ],
                [("RR.L", "No quote data available")],
            )

        mock_service.batch_get_quotes = mock_batch_quotes

        response = client.post(
            "/api/v1/quote/batch",
            json={"symbols": ["AAPL", "RR.L"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["symbol"] == "RR.L"
        assert "No quote data available" in data["errors"][0]["error"]

    @patch("src.routes.quote.yahoo_finance_service")
    def test_batch_quote_all_errors(self, mock_service):
        """Test batch quote when all symbols fail."""

        async def mock_batch_quotes(symbols):
            return (
                [],
                [
                    ("US1234567892", "No quote data available"),
                    ("US1234567893", "No quote data available"),
                ],
            )

        mock_service.batch_get_quotes = mock_batch_quotes

        response = client.post(
            "/api/v1/quote/batch",
            json={"symbols": ["US1234567892", "US1234567893"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 0
        assert len(data["errors"]) == 2

    @patch("src.routes.quote.yahoo_finance_service")
    def test_batch_quote_service_error(self, mock_service):
        """Test batch quote when service throws an exception."""

        async def mock_batch_quotes(symbols):
            raise Exception("Network timeout")

        mock_service.batch_get_quotes = mock_batch_quotes

        response = client.post(
            "/api/v1/quote/batch",
            json={"symbols": ["AAPL"]},
        )

        assert response.status_code == 500
        data = response.json()
        assert "Network timeout" in data["detail"]


class TestBatchServiceMethods:
    """Tests for the batch methods in Yahoo Finance service."""

    @pytest.mark.asyncio
    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    async def test_batch_search_by_isins_success(self, mock_yf, mock_justetf):
        """Test batch search service method with successful results."""
        from src.services.yahoo_finance import YahooFinanceService

        # Mock Search result
        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "AAPL", "shortname": "Apple Inc"}]
        mock_yf.Search.return_value = mock_search

        # Mock Ticker info with price
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "longName": "Apple Inc.",
            "currency": "USD",
            "exchange": "NASDAQ",
            "regularMarketPrice": 195.50,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        results, errors = await service.batch_search_by_isins(["US0378331005"])

        assert len(results) == 1
        assert len(errors) == 0
        assert results[0].isin == "US0378331005"

    @pytest.mark.asyncio
    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    async def test_batch_search_by_isins_partial_failure(self, mock_yf, mock_justetf):
        """Test batch search service method with partial failures."""
        from src.services.yahoo_finance import YahooFinanceService

        # Mock Search to return results for first, empty for second
        def search_side_effect(isin):
            mock = MagicMock()
            if isin == "US0378331005":
                mock.quotes = [{"symbol": "AAPL"}]
            else:
                mock.quotes = []
            return mock

        mock_yf.Search.side_effect = search_side_effect
        mock_justetf.search_by_isin.return_value = None

        # Mock Ticker with price
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "longName": "Apple Inc.",
            "currency": "USD",
            "exchange": "NASDAQ",
            "regularMarketPrice": 195.50,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        results, errors = await service.batch_search_by_isins(["US0378331005", "INVALID"])

        assert len(results) == 1
        assert len(errors) == 1
        assert errors[0][0] == "INVALID"

    @pytest.mark.asyncio
    @patch("src.services.yahoo_finance.yf")
    async def test_batch_get_quotes_success(self, mock_yf):
        """Test batch quote service method with successful results."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_ticker = MagicMock()
        mock_fast_info = MagicMock()
        mock_fast_info.get.side_effect = lambda key, default=None: {
            "lastPrice": 195.50,
            "currency": "USD",
        }.get(key, default)
        mock_ticker.fast_info = mock_fast_info
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        results, errors = await service.batch_get_quotes(["AAPL"])

        assert len(results) == 1
        assert len(errors) == 0
        assert results[0].symbol == "AAPL"

    @pytest.mark.asyncio
    @patch("src.services.yahoo_finance.yf")
    async def test_batch_get_quotes_partial_failure(self, mock_yf):
        """Test batch quote service method with partial failures."""
        from src.services.yahoo_finance import YahooFinanceService

        def ticker_side_effect(symbol):
            mock_ticker = MagicMock()
            if symbol == "AAPL":
                mock_fast_info = MagicMock()
                mock_fast_info.get.side_effect = lambda key, default=None: {
                    "lastPrice": 195.50,
                    "currency": "USD",
                }.get(key, default)
                mock_ticker.fast_info = mock_fast_info
            else:
                # For invalid symbol, fast_info fails
                mock_fast_info = MagicMock()
                mock_fast_info.get.side_effect = Exception("Not found")
                mock_ticker.fast_info = mock_fast_info
                mock_ticker.info = {}  # No price data
            return mock_ticker

        mock_yf.Ticker.side_effect = ticker_side_effect

        service = YahooFinanceService()
        results, errors = await service.batch_get_quotes(["AAPL", "INVALID"])

        assert len(results) == 1
        assert len(errors) == 1
        assert errors[0][0] == "INVALID"

    @pytest.mark.asyncio
    @patch("src.services.yahoo_finance.yf")
    async def test_batch_search_by_isins_exception_in_search(self, mock_yf):
        """Test batch search handles exceptions thrown by search_by_isin."""
        from src.services.yahoo_finance import YahooFinanceService

        # Mock Search to raise an exception
        mock_yf.Search.side_effect = Exception("Network timeout")

        service = YahooFinanceService()
        results, errors = await service.batch_search_by_isins(["US0378331005"])

        # Exception should be caught and added to errors
        assert len(results) == 0
        assert len(errors) == 1
        assert errors[0][0] == "US0378331005"
        assert "Network timeout" in errors[0][1]

    @pytest.mark.asyncio
    @patch("src.services.yahoo_finance.yf")
    async def test_batch_get_quotes_exception_in_get_quote(self, mock_yf):
        """Test batch quotes handles exceptions thrown by get_quote."""
        from src.services.yahoo_finance import YahooFinanceService

        # Mock Ticker to raise an exception
        mock_yf.Ticker.side_effect = Exception("Connection refused")

        service = YahooFinanceService()
        results, errors = await service.batch_get_quotes(["AAPL"])

        # Exception should be caught and added to errors
        assert len(results) == 0
        assert len(errors) == 1
        assert errors[0][0] == "AAPL"
        assert "Connection refused" in errors[0][1]


class TestBatchSchemas:
    """Tests for batch Pydantic schemas."""

    def test_batch_search_request_creation(self):
        """Test BatchSearchRequest model creation."""
        from src.models.schemas import BatchSearchRequest

        request = BatchSearchRequest(isins=["US0378331005", "DE0007164600"])

        assert len(request.isins) == 2
        assert request.isins[0] == "US0378331005"

    def test_batch_quote_request_creation(self):
        """Test BatchQuoteRequest model creation."""
        from src.models.schemas import BatchQuoteRequest

        request = BatchQuoteRequest(symbols=["AAPL", "SAP"])

        assert len(request.symbols) == 2
        assert request.symbols[0] == "AAPL"

    def test_batch_search_response_creation(self):
        """Test BatchSearchResponse model creation."""
        from src.models.schemas import (
            BatchSearchResponse,
            InstrumentResponse,
            SearchErrorItem,
        )

        response = BatchSearchResponse(
            results=[
                InstrumentResponse(
                    isin="US0378331005",
                    symbol="AAPL",
                    name="Apple Inc.",
                    type="stock",
                    currency="USD",
                    exchange="NASDAQ",
                )
            ],
            errors=[SearchErrorItem(isin="INVALID", error="Not found")],
        )

        assert len(response.results) == 1
        assert len(response.errors) == 1

    def test_batch_quote_response_creation(self):
        """Test BatchQuoteResponse model creation."""
        from src.models.schemas import (
            BatchQuoteResponse,
            QuoteErrorItem,
            QuoteResponse,
        )

        response = BatchQuoteResponse(
            results=[
                QuoteResponse(
                    symbol="AAPL",
                    price="195.50",
                    currency="USD",
                    time="2024-12-26T10:00:00Z",
                )
            ],
            errors=[QuoteErrorItem(symbol="INVALID", error="Not found")],
        )

        assert len(response.results) == 1
        assert len(response.errors) == 1

    def test_search_error_item_creation(self):
        """Test SearchErrorItem model creation."""
        from src.models.schemas import SearchErrorItem

        error = SearchErrorItem(isin="INVALID", error="Not found")

        assert error.isin == "INVALID"
        assert error.error == "Not found"

    def test_quote_error_item_creation(self):
        """Test QuoteErrorItem model creation."""
        from src.models.schemas import QuoteErrorItem

        error = QuoteErrorItem(symbol="INVALID", error="No data")

        assert error.symbol == "INVALID"
        assert error.error == "No data"


class TestFallbackProviders:
    """Tests for the fallback providers module."""

    @patch("src.services.fallback_providers.justetf_provider.session")
    def test_justetf_search_success(self, mock_session):
        """Test successful justETF search."""
        from src.services.fallback_providers import JustETFProvider

        # Mock response with ticker in HTML
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><h1>Test ETF Name</h1><script>{"ticker": "NATO"}</script><div>XETRA</div><span>EUR</span></html>'
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        from src.services.fallback_providers import justetf_provider as provider
        result = provider.search_by_isin("US1234567891")

        assert result is not None
        assert result.symbol == "NATO.DE"
        assert "Test ETF" in result.name

    @patch("src.services.fallback_providers.justetf_provider.session")
    def test_justetf_search_no_ticker(self, mock_session):
        """Test justETF search when no ticker found."""
        from src.services.fallback_providers import JustETFProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><h1>Page</h1></html>"
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        from src.services.fallback_providers import justetf_provider as provider
        result = provider.search_by_isin("US1234567891")

        assert result is None

    @patch("src.services.fallback_providers.justetf_provider.session")
    def test_justetf_search_request_error(self, mock_session):
        """Test justETF search when request fails."""
        from src.services.fallback_providers import JustETFProvider

        mock_session.get.side_effect = Exception("Connection error")

        from src.services.fallback_providers import justetf_provider as provider
        result = provider.search_by_isin("US1234567891")

        assert result is None

    @patch("src.services.fallback_providers.justetf_provider.session")
    def test_justetf_extract_exchange_london(self, mock_session):
        """Test justETF extracts London Stock Exchange."""
        from src.services.fallback_providers import JustETFProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><h1>Test ETF</h1><script>{"ticker": "TEST"}</script><div>London Stock Exchange</div><span>GBP</span></html>'
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        from src.services.fallback_providers import justetf_provider as provider
        result = provider.search_by_isin("GB1234567890")

        assert result is not None
        assert result.symbol == "TEST.L"
        assert result.exchange == "London Stock Exchange"

    @patch("src.services.fallback_providers.justetf_provider.session")
    def test_justetf_extract_name_from_title(self, mock_session):
        """Test justETF extracts name from title when no h1."""
        from src.services.fallback_providers import JustETFProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><title>My ETF | justETF</title><script>{"ticker": "TEST"}</script></html>'
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        from src.services.fallback_providers import justetf_provider as provider
        result = provider.search_by_isin("IE00BK5BQT80")

        assert result is not None
        assert result.name == "My ETF"

    @patch("src.services.fallback_providers.justetf_provider.session")
    def test_justetf_default_suffix_when_no_exchange(self, mock_session):
        """Test justETF uses default .L suffix when no exchange found."""
        from src.services.fallback_providers import JustETFProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><h1>Unknown ETF</h1><script>{"ticker": "UNK"}</script></html>'
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        from src.services.fallback_providers import justetf_provider as provider
        result = provider.search_by_isin("IE00BK5BQT80")

        assert result is not None
        assert result.symbol == "UNK.L"

    @patch("src.services.fallback_providers.justetf_provider.session.get")
    @patch("src.services.fallback_providers.BeautifulSoup")
    def test_justetf_search_generic_exception(self, mock_bs, mock_get):
        """Test justETF search when a generic exception occurs during parsing."""
        from src.services.fallback_providers import JustETFProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Force BeautifulSoup to raise a generic Exception
        mock_bs.side_effect = Exception("Parsing error")

        from src.services.fallback_providers import justetf_provider as provider
        result = provider.search_by_isin("IE00BK5BQT80")

        assert result is None

    @patch("src.services.fallback_providers.justetf_provider.session")
    def test_justetf_extract_name_none(self, mock_session):
        """Test justETF extraction when no name can be found (no h1 or title)."""
        from src.services.fallback_providers import JustETFProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        # HTML with no H1 and no TITLE
        mock_response.text = '<html><body><script>{"ticker": "NATO"}</script></body></html>'
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        from src.services.fallback_providers import justetf_provider as provider
        result = provider.search_by_isin("US1234567891")

        assert result is not None
        assert result.name == "NATO"  # Falls back to ticker


class TestYahooFinanceFallbackLogic:
    """Tests for Yahoo Finance fallback logic."""

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_with_suffix_fallback(self, mock_yf, mock_justetf):
        """Test search tries alternative suffixes when original fails."""
        from src.services.yahoo_finance import YahooFinanceService

        # Search returns a symbol with wrong suffix
        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "TEST.SG", "shortname": "Test"}]
        mock_yf.Search.return_value = mock_search

        # First call (TEST.SG) returns no price, second (TEST.DE) succeeds
        def ticker_side_effect(symbol):
            mock = MagicMock()
            if symbol == "TEST.DE":
                mock.info = {
                    "quoteType": "EQUITY",
                    "longName": "Test Stock",
                    "currency": "EUR",
                    "exchange": "XETRA",
                    "regularMarketPrice": 100.00,
                }
            else:
                mock.info = {}  # No price
            return mock

        mock_yf.Ticker.side_effect = ticker_side_effect

        service = YahooFinanceService()
        result = service.search_by_isin("DE1234567890")

        assert result is not None
        assert result.symbol == "TEST.DE"

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_search_falls_back_to_justetf(self, mock_yf, mock_justetf):
        """Test search falls back to justETF when all suffixes fail."""
        from src.services.fallback_providers import TickerInfo
        from src.services.yahoo_finance import YahooFinanceService

        # Search returns a symbol
        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "TEST.SG", "shortname": "Test"}]
        mock_yf.Search.return_value = mock_search

        # All Yahoo symbols fail (no price)
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker

        # justETF returns valid data
        mock_justetf.search_by_isin.return_value = TickerInfo(
            symbol="TEST.L",
            name="Test ETF",
            exchange="London",
            currency="GBP",
        )

        service = YahooFinanceService()
        result = service.search_by_isin("GB1234567890")

        assert result is not None
        # Since Yahoo has no price, returns justETF data directly
        assert result.symbol == "TEST.L"
        assert result.name == "Test ETF"

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_justetf_fallback_verified_by_yahoo(self, mock_yf, mock_justetf):
        """Test justETF result is verified by Yahoo Finance."""
        from src.services.fallback_providers import TickerInfo
        from src.services.yahoo_finance import YahooFinanceService

        # Empty search results
        mock_search = MagicMock()
        mock_search.quotes = []
        mock_yf.Search.return_value = mock_search

        # justETF returns valid data
        mock_justetf.search_by_isin.return_value = TickerInfo(
            symbol="NATO.L",
            name="Defence ETF",
            exchange="London",
            currency="USD",
        )

        # Yahoo confirms the symbol
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "ETF",
            "longName": "HANetf Defence ETF",
            "currency": "USD",
            "exchange": "LSE",
            "regularMarketPrice": 18.50,
        }
        mock_yf.Ticker.return_value = mock_ticker

        service = YahooFinanceService()
        result = service.search_by_isin("IE000OJ5TQP4")

        assert result is not None
        assert result.symbol == "NATO.L"
        assert result.type == "etf"

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_try_get_instrument_info_handles_exception(self, mock_yf, mock_justetf):
        """Test _try_get_instrument_info handles exceptions gracefully."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = [{"symbol": "FAIL"}]
        mock_yf.Search.return_value = mock_search

        # Ticker raises exception
        mock_yf.Ticker.side_effect = Exception("API error")
        mock_justetf.search_by_isin.return_value = None

        service = YahooFinanceService()
        result = service.search_by_isin("IE00BK5BQT80")

        # Should return None after all fallbacks fail
        assert result is None

    @patch("src.services.yahoo_finance.justetf_provider")
    @patch("src.services.yahoo_finance.yf")
    def test_justetf_fallback_exception_handled(self, mock_yf, mock_justetf):
        """Test justETF fallback handles exceptions."""
        from src.services.yahoo_finance import YahooFinanceService

        mock_search = MagicMock()
        mock_search.quotes = []
        mock_yf.Search.return_value = mock_search

        # justETF throws exception
        mock_justetf.search_by_isin.side_effect = Exception("Network error")

        service = YahooFinanceService()
        result = service.search_by_isin("IE00BK5BQT80")

        assert result is None
