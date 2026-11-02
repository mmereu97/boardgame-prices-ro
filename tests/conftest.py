import pytest


@pytest.fixture(autouse=True)
def private_cache(tmp_path, monkeypatch):
    """Each test gets its own cache folder (barcodes, the Shopify turn file)."""
    monkeypatch.setenv("BOARDGAME_CACHE", str(tmp_path / "cache"))
