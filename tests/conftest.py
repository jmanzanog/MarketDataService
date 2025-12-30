import pytest
from unittest.mock import MagicMock
import src.services.fallback_providers

@pytest.fixture(autouse=True)
def mock_metadata_cache(request):
    """Automatically mock metadata cache for all tests except container tests."""
    # Skip mocking for container tests as they need real Redis
    if "container" in request.keywords:
        yield None
        return

    mock = MagicMock()
    mock.enabled = False
    mock.get.return_value = None
    
    # Store original
    original = src.services.fallback_providers.metadata_cache
    src.services.fallback_providers.metadata_cache = mock
    
    yield mock
    
    # Restore
    src.services.fallback_providers.metadata_cache = original
