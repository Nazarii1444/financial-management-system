import pytest


@pytest.fixture
def anyio_backend():
    # Async tests run via anyio's pytest plugin; pin to asyncio (trio isn't installed).
    return "asyncio"
