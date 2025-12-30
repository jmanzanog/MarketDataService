import asyncio
import logging
import math
import re
from datetime import UTC, datetime

import yfinance as yf

from src.models.schemas import InstrumentResponse, QuoteResponse
from src.services.fallback_providers import justetf_provider

logger = logging.getLogger(__name__)


def is_valid_isin(isin: str) -> bool:
    """
    Validate ISIN code format (ISO 6166).
    Standard: 2 letters, 9 alphanumeric characters, 1 check digit.
    """
    if not isin:
        return False
    return bool(re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", isin.upper()))


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

    # Common suffixes ordered by probability for European ETFs/stocks
    FALLBACK_SUFFIXES = [
        ".DE",  # Germany (XETRA, Frankfurt, Stuttgart)
        ".L",  # London
        ".PA",  # Paris
        ".AS",  # Amsterdam
        ".MI",  # Milan
        ".SW",  # Switzerland
        ".MC",  # Madrid
        ".BR",  # Brussels
        "",  # US (no suffix)
        ".TO",  # Toronto
        ".AX",  # Australia
        ".HK",  # Hong Kong
        ".T",  # Tokyo
    ]

    def search_by_isin(self, isin: str) -> InstrumentResponse | None:
        """
        Search for an instrument by its ISIN code.

        Uses a multi-level fallback strategy:
        1. Try the symbol returned by yfinance
        2. If no price data, try alternative suffixes
        3. If still no data, try justETF as fallback source

        Args:
            isin: The ISIN code to search for.

        Returns:
            InstrumentResponse if found, None otherwise.
        """
        # Validate ISIN format before anything else
        if not is_valid_isin(isin):
            logger.warning(f"Invalid ISIN format received: {isin}")
            return None

        try:
            # Step 1: yfinance search endpoint
            search_result = yf.Search(isin)

            if not search_result.quotes:
                logger.warning(f"No results found for ISIN: {isin}")
                # Try justETF as fallback for empty search results
                return self._try_justetf_fallback(isin)

            # Get the first matching quote
            quote = search_result.quotes[0]
            original_symbol = quote.get("symbol", "")

            if not original_symbol:
                logger.warning(f"No symbol found in search result for ISIN: {isin}")
                return self._try_justetf_fallback(isin)

            # Step 2: Try to get valid ticker info
            logger.warning(f"Searching ISIN {isin}: Probing primary symbol {original_symbol}")
            result = self._try_get_instrument_info(isin, original_symbol, quote)
            if result:
                return result

            base_symbol = original_symbol.rsplit(".", 1)[0]

            # OPTIMIZATION: If the base symbol is the ISIN itself, trying suffixes is usually futile
            # (ETFs use mnemonics like 'NATO', not 'IE000...'). Skip to save time.
            if base_symbol == isin:
                logger.warning(
                    f"Base ticker matches ISIN {isin}. Skipping suffix loop (unlikely to work)."
                )
            else:
                # Step 3: Try alternative suffixes
                logger.warning(
                    f"Primary symbol {original_symbol} has no price data for {isin}. "
                    "Starting suffix fallback strategy..."
                )

                for suffix in self.FALLBACK_SUFFIXES:
                    candidate_symbol = f"{base_symbol}{suffix}"
                    if candidate_symbol == original_symbol:
                        continue

                    logger.debug(f"Trying suffix {suffix} for {isin}: {candidate_symbol}")
                    result = self._try_get_instrument_info(isin, candidate_symbol, quote)
                    if result:
                        logger.warning(
                            f"SUCCESS: Found valid fallback symbol for {isin} -> {candidate_symbol}"
                        )
                        return result

            # Step 3.5: Search by Name (New Strategy)
            # If we have a name from the initial ghost result, try searching for that name in Yahoo
            raw_name = quote.get("shortname") or quote.get("longname")
            if raw_name:
                logger.warning(f"Attempting Search-By-Name fallback using: '{raw_name}'")
                result = self._try_search_by_name_fallback(isin, raw_name)
                if result:
                    return result

            # Step 4: Try justETF as last resort
            logger.warning(
                f"All Yahoo attempts failed for {isin}. Attempting justETF scraping fallback..."
            )
            return self._try_justetf_fallback(isin)

        except Exception as e:
            logger.error(f"Error searching for ISIN {isin}: {e}")
            raise

    def _try_get_instrument_info(
        self, isin: str, symbol: str, quote: dict
    ) -> InstrumentResponse | None:
        """
        Try to get instrument info for a symbol.

        Args:
            isin: Original ISIN code.
            symbol: Symbol to try.
            quote: Original search quote data.

        Returns:
            InstrumentResponse if valid data found, None otherwise.
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Check if we have valid price data (indicates valid symbol)
            price = info.get("regularMarketPrice") or info.get("currentPrice")

            # Stricter check: None, NaN or 0.0 are considered invalid
            if price is None or math.isnan(float(price)) or float(price) <= 0:
                return None

            # DETECT "GHOST" SYMBOLS:
            # If symbol contains the ISIN and lacks a longName, it's usually a dummy record in Yahoo.
            # Real symbols for these ETFs usually have a proper ticker (e.g. NATO.L)
            symbol_base = symbol.split(".")[0]
            if symbol_base == isin and not info.get("longName"):
                logger.warning(f"Detected ghost symbol {symbol} for ISIN {isin}. Skipping...")
                return None

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
            logger.debug(f"Failed to get info for symbol {symbol}: {e}")
            return None

    def _try_search_by_name_fallback(self, isin: str, name: str) -> InstrumentResponse | None:
        """
        Search for instrument by name when ISIN lookup yields invalid symbols.

        Args:
            isin: Original ISIN (for verification).
            name: Name of the instrument to search for.

        Returns:
            InstrumentResponse if found, None otherwise.
        """
        try:
            # Clean name aggressiveley to get the "core" fund name which works best in Yahoo search
            # Remove: "UCITS", "ETF", "Acc", "Dist", issuer names like "HANetf", "iShares", etc.
            # Example: "HANetf Future of Defence UCITS ETF" -> "Future of Defence"

            remove_terms = [
                "UCITS",
                "ETF",
                "Acc",
                "Dist",
                "Class",
                "USD",
                "EUR",
                "GBP",
                "HANetf",
                "iShares",
                "Vanguard",
                "Amundi",
                "Invesco",
                "Xtrackers",
                "SPDR",
            ]

            search_query = name
            for term in remove_terms:
                search_query = search_query.replace(term, "")

            search_query = search_query.strip()
            # If name becomes too short, revert to original (safety check)
            if len(search_query) < 4:
                search_query = name

            logger.debug(f"Searching Yahoo by name: {search_query} (Original: {name})")
            search_result = yf.Search(search_query)

            if not search_result.quotes:
                return None

            # Iterate through results to find a valid one
            for quote in search_result.quotes[:3]:  # Check top 3 results
                symbol = quote.get("symbol")
                if not symbol:
                    continue

                # Avoid circular reference back to the ghost ISIN symbol
                if isin in symbol:
                    continue

                result = self._try_get_instrument_info(isin, symbol, quote)
                if result:
                    logger.warning(f"Search-By-Name SUCCEEDED: Found {symbol} for '{name}'")
                    return result

            return None
        except Exception as e:
            logger.debug(f"Search-by-name failed: {e}")
            return None

    def _try_justetf_fallback(self, isin: str) -> InstrumentResponse | None:
        """
        Try justETF as fallback source for European ETFs.
        If the suggested symbol doesn't work, attempts it with other suffixes.

        Args:
            isin: The ISIN code to search for.

        Returns:
            InstrumentResponse if found via justETF, None otherwise.
        """
        try:
            ticker_info = justetf_provider.search_by_isin(isin)
            if not ticker_info:
                return None

            # 1. Try the specific symbol JustETF suggested
            result = self._try_get_instrument_info(
                isin,
                ticker_info.symbol,
                {"shortname": ticker_info.name},
            )
            if result:
                logger.warning(f"justETF fallback SUCCEEDED for {isin} -> {ticker_info.symbol}")
                return result

            # 2. CROSS-POLLINATION: The suggested suffix failed, let's try the
            # suggested Ticker with OTHER Yahoo suffixes.
            # Example: JustETF says NATO.DE but Yahoo only likes NATO.L
            base_ticker = ticker_info.symbol.split(".")[0]
            logger.warning(
                f"justETF suggested {ticker_info.symbol} for {isin} but it has no price. "
                f"Trying ticker {base_ticker} with other suffixes..."
            )

            for suffix in self.FALLBACK_SUFFIXES:
                candidate = f"{base_ticker}{suffix}"
                if candidate == ticker_info.symbol:
                    continue

                result = self._try_get_instrument_info(
                    isin, candidate, {"shortname": ticker_info.name}
                )
                if result:
                    logger.warning(
                        f"SUCCESS: Cross-referencing {isin}: JustETF ticker {base_ticker} + suffix {suffix} -> {candidate}"
                    )
                    return result

            # 3. Final fallback: Return info even without price if it's better than nothing
            # (only if we didn't find any working symbol)
            # IMPORTANT: We only return this if we are SURE it's better than nothing,
            # but we logs it clearly as it might not have quotes.
            logger.warning(
                f"Could not find any working Yahoo symbol for ticker {base_ticker} on {isin}."
            )

            # Final safety check: if we are here, we try one last name search
            # with the name we got from JustETF before giving up
            result = self._try_search_by_name_fallback(isin, ticker_info.name)
            if result:
                return result

            return InstrumentResponse(
                isin=isin,
                symbol=ticker_info.symbol,
                name=ticker_info.name,
                type="etf",
                currency=ticker_info.currency,
                exchange=ticker_info.exchange,
            )

        except Exception as e:
            logger.debug(f"justETF fallback failed for {isin}: {e}")
            return None

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

            if price is None or math.isnan(float(price)) or float(price) <= 0:
                logger.warning(f"No valid price data found for symbol: {symbol} (Price: {price})")

                # SELF-CORRECTION LOGIC
                # If symbol looks like an ISIN with a suffix (e.g., IE...SG),
                # try to find the working symbol.
                import re

                base_part = symbol.split(".")[0] if "." in symbol else symbol
                if re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", base_part):
                    logger.warning(
                        f"Symbol {symbol} appears to be invalid or a ghost record. Attempting repair..."
                    )
                    better_instrument = self.search_by_isin(base_part)
                    if better_instrument and better_instrument.symbol != symbol:
                        logger.warning(
                            f"FOUND BETTER SYMBOL: {symbol} -> {better_instrument.symbol}"
                        )
                        # Recursive call with the corrected symbol
                        return self.get_quote(better_instrument.symbol)

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

    async def batch_search_by_isins(
        self, isins: list[str]
    ) -> tuple[list[InstrumentResponse], list[tuple[str, str]]]:
        """
        Search for multiple instruments by their ISIN codes in parallel.

        Args:
            isins: List of ISIN codes to search for.

        Returns:
            Tuple of (successful results, errors as list of (isin, error_message)).
        """

        results: list[InstrumentResponse] = []
        errors: list[tuple[str, str]] = []

        # Execute all searches in parallel provided by asyncio.to_thread (uses global pool)
        async def search_single_wrapper(
            isin: str,
        ) -> tuple[str, InstrumentResponse | None, str | None]:
            try:
                # Run the blocking search_by_isin in a separate thread
                result = await asyncio.to_thread(self.search_by_isin, isin)
                if result is None:
                    return (isin, None, "No instrument found for ISIN")
                return (isin, result, None)
            except Exception as e:  # pragma: no cover
                logger.error(f"Batch search error for ISIN {isin}: {e}")  # pragma: no cover
                return (isin, None, str(e))  # pragma: no cover

        tasks = [search_single_wrapper(isin) for isin in isins]
        search_results = await asyncio.gather(*tasks)

        for isin, result, error in search_results:
            if result is not None:
                results.append(result)
            elif error is not None:
                errors.append((isin, error))

        return results, errors

    async def batch_get_quotes(
        self, symbols: list[str]
    ) -> tuple[list[QuoteResponse], list[tuple[str, str]]]:
        """
        Get quotes for multiple symbols in parallel.

        Args:
            symbols: List of trading symbols.

        Returns:
            Tuple of (successful results, errors as list of (symbol, error_message)).
        """
        results: list[QuoteResponse] = []
        errors: list[tuple[str, str]] = []

        # Execute all quote requests in parallel
        async def get_quote_wrapper(symbol: str) -> tuple[str, QuoteResponse | None, str | None]:
            try:
                # Run the blocking get_quote in a separate thread
                result = await asyncio.to_thread(self.get_quote, symbol)
                if result is None:
                    return (symbol, None, "No quote data available")
                return (symbol, result, None)
            except Exception as e:  # pragma: no cover
                logger.error(f"Batch quote error for symbol {symbol}: {e}")  # pragma: no cover
                return (symbol, None, str(e))  # pragma: no cover

        tasks = [get_quote_wrapper(symbol) for symbol in symbols]
        quote_results = await asyncio.gather(*tasks)

        for symbol, result, error in quote_results:
            if result is not None:
                results.append(result)
            elif error is not None:
                errors.append((symbol, error))

        return results, errors


# Singleton instance
yahoo_finance_service = YahooFinanceService()
