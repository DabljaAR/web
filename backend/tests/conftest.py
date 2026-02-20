import pytest


def pytest_configure(config):
    """Set asyncio mode to auto so every async test/fixture is handled automatically."""
    config.addinivalue_line("markers", "asyncio: mark test as async")
