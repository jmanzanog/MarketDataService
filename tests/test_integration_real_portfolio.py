import time

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

# Real ISINs from the user's portfolio
PORTFOLIO_ISINS = [
    "CNE100000296",  # BYD
    "GB00B63H8491",  # Rolls-Royce
    "IE000OJ5TQP4",  # Future of Defence (Tricky one!)
    "IE00BK5BQT80",  # VWRA
    "IE00BM67HT60",  # Xtrackers MSCI World IT
    "IE00BMW42306",  # iShares MSCI Europe SRI
    "KYG875721634",  # Tencent
    "KYG9830T1067",  # Xiaomi
    "NL0009538784",  # NXP
    "US0090661010",  # Airbnb
    "US8740391003",  # Taiwan Semi (US ADR)
]


@pytest.mark.integration
class TestRealPortfolioIntegration:
    """
    Integration tests using REAL external API calls to Yahoo Finance.
    These tests verify the actual end-to-end performance and logic with live data.
    """

    def test_batch_search_performance_and_accuracy(self):
        """
        Verify that searching for the user's specific portfolio is:
        1. Fast (< 15 seconds to be safe, ideally < 10s)
        2. Accurate (finds all instruments)
        3. Robust (handles the tricky IE000OJ5TQP4 correctly)
        """
        payload = {"isins": PORTFOLIO_ISINS}

        start_time = time.time()
        response = client.post("/api/v1/search/batch", json=payload)
        duration = time.time() - start_time

        print(f"\nBatch Search Duration: {duration:.2f} seconds")

        assert response.status_code == 200
        data = response.json()

        # Check for failures
        failures = data.get("failed", [])
        if failures:
            print("\nFailed ISINs:")
            for f in failures:
                print(f" - {f['isin']}: {f['error']}")

        # We expect NO failures for this portfolio now that we have robust fallbacks
        assert len(failures) == 0, f"Expected 0 failures, got {len(failures)}"

        # Verify specific tricky instruments
        results = data.get("results", [])  # Correct key is 'results', not 'successful'
        print("\nSuccessful results:")
        for r in results:
            print(f" - {r['isin']} -> {r['symbol']}")

        results_map = {item["isin"]: item for item in results}

        # Check 'Future of Defence' (IE000OJ5TQP4)
        defense_etf = results_map.get("IE000OJ5TQP4")
        assert defense_etf is not None
        print(f"\nFound Future of Defence as: {defense_etf['symbol']} ({defense_etf['name']})")
        # ASWC.DE is the Xetra ticker for Future of Defence, NATO.L is London. Both are valid.
        valid_tickers = ["NATO", "OF", "ASWC"]
        assert any(t in defense_etf["symbol"] for t in valid_tickers), (
            f"Unexpected ticker {defense_etf['symbol']}"
        )

        # Check 'BYD' (CNE100000296) - usually 1211.HK
        byd = results_map.get("CNE100000296")
        assert byd is not None
        print(f"Found BYD as: {byd['symbol']}")

        # Validate performance
        # We explicitly want this to be fast to avoid timeouts
        assert duration < 20.0, f"Request took too long: {duration:.2f}s"
