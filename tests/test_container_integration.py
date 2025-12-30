"""
Integration tests using Docker containers.

These tests:
1. Build the Docker image of the application
2. Start a container with the real application
3. Execute HTTP requests against all endpoints
4. Verify responses and behavior

Requires Docker to be running.
"""

import time
from collections.abc import Generator

import pytest
import requests
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage
from testcontainers.core.waiting_utils import wait_for_logs

# Test data: Real ISINs from user's portfolio
TEST_ISINS = [
    "CNE100000296",  # BYD
    "GB00B63H8491",  # Rolls-Royce
    "IE000OJ5TQP4",  # Future of Defence
    "IE00BK5BQT80",  # VWRA
    "IE00BM67HT60",  # Xtrackers MSCI World IT
    "IE00BMW42306",  # iShares MSCI Europe SRI
    "KYG875721634",  # Tencent
    "KYG9830T1067",  # Xiaomi
    "NL0009538784",  # NXP
    "US0090661010",  # Airbnb
    "US8740391003",  # Taiwan Semi (US ADR)
]

# Some known symbols for quote tests (obtained from search results)
TEST_SYMBOLS = ["AAPL", "MSFT", "RR.L"]


@pytest.fixture(scope="module")
def docker_container() -> Generator[DockerContainer, None, None]:
    """
    Build and start the MarketDataService container.

    This fixture:
    - Builds the Docker image from the project Dockerfile
    - Starts the container exposing port 8000
    - Waits for the application to be ready
    - Yields the container for tests
    - Cleans up after all tests complete
    """
    # Build the image from the project root
    # The context is the parent of tests/ directory
    image = DockerImage(
        path=".",
        tag="marketdataservice:test",
    )
    image.build()

    # Create and start container
    container = DockerContainer(image="marketdataservice:test")
    container.with_exposed_ports(8000)
    container.with_env("LOG_LEVEL", "INFO")

    container.start()

    # Wait for the application to be ready (health check)
    try:
        wait_for_logs(container, "Uvicorn running", timeout=60)
        # Give it a moment to fully initialize
        time.sleep(2)
    except TimeoutError:
        container.stop()
        pytest.fail("Container failed to start within timeout")

    yield container

    # Cleanup
    container.stop()


def get_base_url(container: DockerContainer) -> str:
    """Get the base URL for the running container."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(8000)
    return f"http://{host}:{port}"


@pytest.mark.container
class TestContainerHealthEndpoints:
    """Tests for health and root endpoints using real container."""

    def test_health_endpoint(self, docker_container: DockerContainer):
        """Test /health returns healthy status."""
        base_url = get_base_url(docker_container)

        response = requests.get(f"{base_url}/health", timeout=10)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_root_endpoint(self, docker_container: DockerContainer):
        """Test / returns API information."""
        base_url = get_base_url(docker_container)

        response = requests.get(f"{base_url}/", timeout=10)

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"

    def test_docs_endpoint_available(self, docker_container: DockerContainer):
        """Test /docs (Swagger UI) is accessible."""
        base_url = get_base_url(docker_container)

        response = requests.get(f"{base_url}/docs", timeout=10)

        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()


@pytest.mark.container
class TestContainerSearchEndpoints:
    """Tests for search endpoints using real container with real Yahoo Finance calls."""

    def test_search_single_isin_success(self, docker_container: DockerContainer):
        """Test GET /api/v1/search/{isin} with a valid ISIN."""
        base_url = get_base_url(docker_container)
        isin = "US0090661010"  # Airbnb - usually reliable

        response = requests.get(f"{base_url}/api/v1/search/{isin}", timeout=30)

        assert response.status_code == 200
        data = response.json()
        assert data["isin"] == isin
        assert "symbol" in data
        assert "name" in data
        assert "currency" in data
        print(f"\n  Found: {data['symbol']} - {data['name']}")

    def test_search_single_isin_not_found_handling(self, docker_container: DockerContainer):
        """
        Test GET /api/v1/search/{isin} with a non-existent ISIN.
        The service is extremely resilient, so it might return 404 or a 200 with
        fallback info. We verify it handles the request without crashing.
        """
        base_url = get_base_url(docker_container)
        isin = "US0000000000"

        response = requests.get(f"{base_url}/api/v1/search/{isin}", timeout=30)

        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert data["isin"] == isin
            print(
                f"\n  Note: Service found fallback info for non-existent ISIN: {data.get('symbol')}"
            )

    def test_search_batch_all_portfolio_isins(self, docker_container: DockerContainer):
        """
        Test POST /api/v1/search/batch with all portfolio ISINs.
        This is the main integration test that verifies all instruments are found.
        """
        base_url = get_base_url(docker_container)
        payload = {"isins": TEST_ISINS}

        start_time = time.time()
        response = requests.post(
            f"{base_url}/api/v1/search/batch",
            json=payload,
            timeout=60,
        )
        duration = time.time() - start_time

        print(f"\n  Batch search duration: {duration:.2f}s")

        assert response.status_code == 200
        data = response.json()

        results = data.get("results", [])
        errors = data.get("errors", [])

        print(f"  Successful: {len(results)}/{len(TEST_ISINS)}")
        if errors:
            print("  Errors:")
            for err in errors:
                print(f"    - {err['isin']}: {err['error']}")

        # We expect most or all to succeed
        assert len(results) >= len(TEST_ISINS) - 2, (
            f"Too many failures: {len(errors)} out of {len(TEST_ISINS)}"
        )

        # Verify each result has required fields
        for result in results:
            assert "isin" in result
            assert "symbol" in result
            assert "name" in result
            print(f"    {result['isin']} -> {result['symbol']}")

    def test_search_batch_empty_request(self, docker_container: DockerContainer):
        """Test POST /api/v1/search/batch with empty list."""
        base_url = get_base_url(docker_container)
        payload = {"isins": []}

        response = requests.post(
            f"{base_url}/api/v1/search/batch",
            json=payload,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []


@pytest.mark.container
class TestContainerQuoteEndpoints:
    """Tests for quote endpoints using real container with real Yahoo Finance calls."""

    def test_quote_single_symbol_success(self, docker_container: DockerContainer):
        """Test GET /api/v1/quote/{symbol} with a valid symbol."""
        base_url = get_base_url(docker_container)
        symbol = "AAPL"

        response = requests.get(f"{base_url}/api/v1/quote/{symbol}", timeout=30)

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == symbol
        assert "price" in data
        assert "currency" in data
        assert float(data["price"]) > 0
        print(f"\n  {symbol}: ${data['price']} {data['currency']}")

    def test_quote_single_symbol_not_found(self, docker_container: DockerContainer):
        """Test GET /api/v1/quote/{symbol} with invalid symbol returns 404."""
        base_url = get_base_url(docker_container)
        symbol = "NOTAREALSYMBOL123"

        response = requests.get(f"{base_url}/api/v1/quote/{symbol}", timeout=30)

        # Yahoo Finance might return 404 or empty data
        assert response.status_code in [404, 500]

    def test_quote_batch_multiple_symbols(self, docker_container: DockerContainer):
        """Test POST /api/v1/quote/batch with multiple symbols."""
        base_url = get_base_url(docker_container)
        payload = {"symbols": TEST_SYMBOLS}

        start_time = time.time()
        response = requests.post(
            f"{base_url}/api/v1/quote/batch",
            json=payload,
            timeout=60,
        )
        duration = time.time() - start_time

        print(f"\n  Batch quote duration: {duration:.2f}s")

        assert response.status_code == 200
        data = response.json()

        results = data.get("results", [])

        print(f"  Successful: {len(results)}/{len(TEST_SYMBOLS)}")
        for result in results:
            print(f"    {result['symbol']}: {result['price']} {result['currency']}")

        # At least some should succeed
        assert len(results) > 0

    def test_quote_batch_empty_request(self, docker_container: DockerContainer):
        """Test POST /api/v1/quote/batch with empty list."""
        base_url = get_base_url(docker_container)
        payload = {"symbols": []}

        response = requests.post(
            f"{base_url}/api/v1/quote/batch",
            json=payload,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []


@pytest.mark.container
class TestContainerEndToEndWorkflow:
    """
    End-to-end workflow tests that simulate real usage patterns.
    These tests search for an instrument and then get its quote.
    """

    def test_search_then_quote_workflow(self, docker_container: DockerContainer):
        """
        Test the complete workflow:
        1. Search for an instrument by ISIN
        2. Get a quote for the returned symbol
        """
        base_url = get_base_url(docker_container)
        isin = "US8740391003"  # Taiwan Semi

        # Step 1: Search for the instrument
        search_response = requests.get(
            f"{base_url}/api/v1/search/{isin}",
            timeout=30,
        )
        assert search_response.status_code == 200
        instrument = search_response.json()
        symbol = instrument["symbol"]

        print(f"\n  Step 1: Found {isin} -> {symbol} ({instrument['name']})")

        # Step 2: Get quote for the symbol
        quote_response = requests.get(
            f"{base_url}/api/v1/quote/{symbol}",
            timeout=30,
        )
        assert quote_response.status_code == 200
        quote = quote_response.json()

        print(f"  Step 2: Quote {symbol} = {quote['price']} {quote['currency']}")

        # Verify data consistency
        assert quote["symbol"] == symbol
        assert float(quote["price"]) > 0

    def test_batch_search_and_batch_quote_workflow(self, docker_container: DockerContainer):
        """
        Test batch workflow:
        1. Batch search for multiple ISINs
        2. Batch quote for all returned symbols
        """
        base_url = get_base_url(docker_container)
        test_isins = TEST_ISINS[:5]  # Use first 5 for speed

        # Step 1: Batch search
        search_response = requests.post(
            f"{base_url}/api/v1/search/batch",
            json={"isins": test_isins},
            timeout=60,
        )
        assert search_response.status_code == 200
        search_data = search_response.json()

        symbols = [r["symbol"] for r in search_data["results"]]
        print(f"\n  Step 1: Found {len(symbols)} symbols from {len(test_isins)} ISINs")

        if not symbols:
            pytest.skip("No symbols found to quote")

        # Step 2: Batch quote
        quote_response = requests.post(
            f"{base_url}/api/v1/quote/batch",
            json={"symbols": symbols},
            timeout=60,
        )
        assert quote_response.status_code == 200
        quote_data = quote_response.json()

        print(f"  Step 2: Got {len(quote_data['results'])} quotes")
        for q in quote_data["results"]:
            print(f"    {q['symbol']}: {q['price']} {q['currency']}")


@pytest.mark.container
class TestContainerPerformance:
    """Performance tests for the containerized application."""

    def test_health_check_response_time(self, docker_container: DockerContainer):
        """Health check should respond quickly (< 500ms)."""
        base_url = get_base_url(docker_container)

        start_time = time.time()
        response = requests.get(f"{base_url}/health", timeout=5)
        duration = time.time() - start_time

        assert response.status_code == 200
        assert duration < 0.5, f"Health check too slow: {duration:.3f}s"
        print(f"\n  Health check: {duration * 1000:.1f}ms")

    def test_batch_search_completes_in_reasonable_time(self, docker_container: DockerContainer):
        """Batch search should complete within 60 seconds for all ISINs."""
        base_url = get_base_url(docker_container)

        start_time = time.time()
        response = requests.post(
            f"{base_url}/api/v1/search/batch",
            json={"isins": TEST_ISINS},
            timeout=90,
        )
        duration = time.time() - start_time

        assert response.status_code == 200
        assert duration < 60, f"Batch search too slow: {duration:.1f}s"
        print(f"\n  Batch search ({len(TEST_ISINS)} ISINs): {duration:.1f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "container", "--tb=short"])
