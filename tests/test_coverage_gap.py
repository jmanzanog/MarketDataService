
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from src.services.yahoo_finance import YahooFinanceService
from src.services import yahoo_finance # importation for module patching
from src.models.schemas import InstrumentResponse

class TestCoverageGaps:
    """
    Tests specifically targeting error handling paths and edge cases.
    We mock 'to_thread' directly to ensure we trigger the exception inside the wrapper coroutine,
    bypassing threading complexity for coverage.
    """

    @pytest.mark.asyncio
    async def test_batch_search_exception_handling(self):
        """Cover lines 308-311: Exception handling in search_single_wrapper"""
        service = YahooFinanceService()
        
        # We patch asyncio.to_thread in the MODULE where it is used
        with patch("src.services.yahoo_finance.asyncio.to_thread", side_effect=Exception("Simulated Crash")):
            results, errors = await service.batch_search_by_isins(["BAD_ISIN"])
            
            assert len(results) == 0
            assert len(errors) == 1
            assert errors[0][0] == "BAD_ISIN"
            assert "Simulated Crash" in errors[0][1]

    @pytest.mark.asyncio
    async def test_batch_quote_exception_handling(self):
        """Cover lines around 362-371 (Except block): Exception handling in get_quote_wrapper"""
        service = YahooFinanceService()
        
        # Patch asyncio.to_thread in the MODULE
        with patch("src.services.yahoo_finance.asyncio.to_thread", side_effect=Exception("Quote Crash")):
            results, errors = await service.batch_get_quotes(["FAIL.L"])
            
            assert len(results) == 0
            assert len(errors) == 1
            assert errors[0][0] == "FAIL.L"
            assert "Quote Crash" in errors[0][1]

    @pytest.mark.asyncio
    async def test_batch_quote_none_result(self):
        """Cover lines around 362-371 (If None block): get_quote_wrapper returning None"""
        service = YahooFinanceService()
        
        # Patch asyncio.to_thread in the MODULE
        with patch("src.services.yahoo_finance.asyncio.to_thread", return_value=None):
            results, errors = await service.batch_get_quotes(["MISSING.L"])
            
            assert len(results) == 0
            assert len(errors) == 1
            assert errors[0][0] == "MISSING.L"
            assert "No quote data available" in errors[0][1]

    @pytest.mark.asyncio
    async def test_search_by_name_fallback_exception(self):
        """Cover exceptions in _try_search_by_name_fallback"""
        service = YahooFinanceService()
        
        # Force yf.Search to raise exception
        with patch("src.services.yahoo_finance.yf.Search", side_effect=Exception("Search API Down")):
            result = service._try_search_by_name_fallback("ISIN123", "Some Name")
            assert result is None

    def test_search_by_name_fallback_logic_paths(self):
        """Cover logical paths in _try_search_by_name_fallback (short name, empty results, no symbol)"""
        service = YahooFinanceService()

        # Case 1: Short name -> Reverts to original name
        # We verify this by inspecting the call to yf.Search
        with patch("src.services.yahoo_finance.yf.Search") as mock_search:
            mock_search.return_value.quotes = [] # Return empty to exit fast
            service._try_search_by_name_fallback("ISIN1", "ETF") # 3 chars
            # Should search for "ETF" (original) not cleaned empty string
            mock_search.assert_called_with("ETF")

        # Case 2: Empty quotes -> Returns None
        with patch("src.services.yahoo_finance.yf.Search") as mock_search:
            mock_search.return_value.quotes = [] 
            result = service._try_search_by_name_fallback("ISIN2", "Valid Name")
            assert result is None

        # Case 3: Quote without symbol -> Continue loop
        with patch("src.services.yahoo_finance.yf.Search") as mock_search:
            # First quote invalid, second valid
            mock_search.return_value.quotes = [
                {"longname": "Bad"}, # No symbol
                {"symbol": "GOOD.DE", "longname": "Good ETF"}
            ]
            # Mock _try_get_instrument_info to return valid info for the second one
            with patch.object(service, "_try_get_instrument_info") as mock_get_info:
                mock_get_info.return_value = InstrumentResponse(
                    isin="ISIN3", symbol="GOOD.DE", name="Good ETF", type="etf", currency="EUR", exchange=".DE"
                )
                
                result = service._try_search_by_name_fallback("ISIN3", "Valid Name")
                assert result is not None
                assert result.symbol == "GOOD.DE"

    @pytest.mark.asyncio
    async def test_justetf_fallback_exception(self):
        """Cover lines 260-262: Exception in _try_justetf_fallback"""
        service = YahooFinanceService()
        
        # Mock the request call inside justETF provider indirectly or the provider call itself
        with patch("src.services.yahoo_finance.justetf_provider.search_by_isin", side_effect=Exception("Scraping Failed")):
            result = service._try_justetf_fallback("ISIN_FAIL")
            assert result is None
