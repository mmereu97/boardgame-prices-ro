import pytest

from collector import shops


@pytest.fixture(autouse=True)
def private_cache(tmp_path, monkeypatch):
    """Each test gets its own cache folder (barcodes, the Shopify turn file), and no
    Shopify cool-down unless the test asks for it: a real one would wait 20 minutes."""
    monkeypatch.setenv("BOARDGAME_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(shops, "SHOPIFY_COOLDOWN", 0)
