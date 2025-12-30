"""
Integration tests using Docker containers with Redis support.

These tests:
1. Build the Docker image of the application
2. Start a Redis container
3. Start the MarketDataService container linked to Redis
4. Execute HTTP requests against all endpoints
5. Verify caching behavior and resilience

Requires Docker to be running.
"""

import time
from collections.abc import Generator

import pytest
import requests
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage
from testcontainers.core.network import Network
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.redis import RedisContainer

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
def docker_network() -> Generator[Network, None, None]:
    with Network() as network:
        yield network


@pytest.fixture(scope="module")
def redis_container(docker_network: Network) -> Generator[RedisContainer, None, None]:
    """Start a Redis container for caching tests."""
    with RedisContainer("redis:7-alpine").with_network(docker_network).with_network_aliases(
        "redis"
    ) as redis:
        yield redis


@pytest.fixture(scope="module")
def docker_container(
    docker_network: Network, redis_container: RedisContainer
) -> Generator[DockerContainer, None, None]:
    """
    Build and start the MarketDataService container.
    """
    # Build the image from the project root
    image = DockerImage(
        path=".",
        tag="marketdataservice:test",
    )
    image.build()

    # Create and start container
    container = DockerContainer(image="marketdataservice:test")
    container.with_network(docker_network)
    container.with_exposed_ports(8000)
    container.with_env("LOG_LEVEL", "DEBUG")  # Debug to see cache logs
    container.with_env("REDIS_HOST", "redis")
    container.with_env("REDIS_PORT", "6379")

    container.start()

    # Wait for the application to be ready
    try:
        wait_for_logs(container, "Uvicorn running", timeout=60)
        time.sleep(2)
    except TimeoutError:
        container.stop()
        pytest.fail("Container failed to start within timeout")

    yield container

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


@pytest.mark.container
class TestContainerMetadataCaching:
    """Tests specifically for Redis caching behavior."""

    def test_metadata_caching_performance(self, docker_container: DockerContainer):
        """
        Verify that the second request for the same ISIN is significantly faster
        due to Redis caching.
        """
        base_url = get_base_url(docker_container)
        isin = "IE00BK5BQT80"  # VWRA

        # First request: Fresh search (will hit Yahoo/JustETF and cache it)
        start_first = time.time()
        res1 = requests.get(f"{base_url}/api/v1/search/{isin}", timeout=40)
        duration_first = time.time() - start_first

        assert res1.status_code == 200
        print(f"\n  First search (uncached): {duration_first:.2f}s")

        # Second request: Should be a cache hit
        start_second = time.time()
        res2 = requests.get(f"{base_url}/api/v1/search/{isin}", timeout=10)
        duration_second = time.time() - start_second

        print(f"  Second search (cached):   {duration_second:.4f}s")
        print(f"  >>> Speedup: {duration_first / duration_second:.1f}x faster!")

        # Verification: Cached request should be very fast (< 200ms usually, let's be safe with 500ms)
        assert (
            duration_second < 0.5
        ), f"Cached request too slow: {duration_second:.2f}s (expected cache hit)"
        assert (
            duration_second < duration_first
        ), "Cached request should be faster than uncached one"

        # Verify data is identical
        assert res1.json() == res2.json()


@pytest.mark.container
class TestContainerSearchEndpoints:
    """Tests for search endpoints using real container with real Yahoo Finance calls."""

    def test_search_single_isin_success(self, docker_container: DockerContainer):
        """Test GET /api/v1/search/{isin} with a valid ISIN."""
        base_url = get_base_url(docker_container)
        isin = "US0090661010"  # Airbnb

        response = requests.get(f"{base_url}/api/v1/search/{isin}", timeout=30)

        assert response.status_code == 200
        data = response.json()
        assert data["isin"] == isin
        assert "symbol" in data
        print(f"\n  Found: {data['symbol']} - {data['name']}")

    def test_search_single_isin_not_found_handling(self, docker_container: DockerContainer):
        """Test GET /api/v1/search/{isin} with a clearly invalid ISIN."""
        base_url = get_base_url(docker_container)
        isin = "INVALID_FORMAT"  # Fails regex validation

        response = requests.get(f"{base_url}/api/v1/search/{isin}", timeout=30)

        # Should be 404 due to strict format validation
        assert response.status_code == 404

    def test_search_batch_all_portfolio_isins(self, docker_container: DockerContainer):
        """Test POST /api/v1/search/batch with all portfolio ISINs."""
        base_url = get_base_url(docker_container)
        payload = {"isins": TEST_ISINS}

        start_time = time.time()
        response = requests.post(
            f"{base_url}/api/v1/search/batch",
            json=payload,
            timeout=120,
        )
        duration = time.time() - start_time

        print(f"\n  Batch search duration: {duration:.2f}s")

        assert response.status_code == 200
        data = response.json()

        results = data.get("results", [])
        print(f"  Successful: {len(results)}/{len(TEST_ISINS)}")

        # Verify each result has required fields
        for result in results:
            assert "isin" in result
            assert "symbol" in result


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
        assert float(data["price"]) > 0
        print(f"\n  {symbol}: ${data['price']} {data['currency']}")


@pytest.mark.container
class TestContainerEndToEndWorkflow:
    """End-to-end workflow tests."""

    def test_search_then_quote_workflow(self, docker_container: DockerContainer):
        base_url = get_base_url(docker_container)
        isin = "US8740391003"  # Taiwan Semi

        # Step 1: Search
        search_res = requests.get(f"{base_url}/api/v1/search/{isin}", timeout=30)
        assert search_res.status_code == 200
        symbol = search_res.json()["symbol"]

        # Step 2: Quote
        quote_res = requests.get(f"{base_url}/api/v1/quote/{symbol}", timeout=30)
        assert quote_res.status_code == 200
        assert float(quote_res.json()["price"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "container", "--tb=short"])
