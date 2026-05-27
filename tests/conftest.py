import os
import pytest

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "mt5: mark test that requires a live MetaTrader 5 connection"
    )

def pytest_collection_modifyitems(config, items):
    if os.environ.get("CI") == "true":
        skip_mt5 = pytest.mark.skip(reason="Skipping MT5 tests in CI environment")
        for item in items:
            if "mt5" in item.keywords:
                item.add_marker(skip_mt5)
