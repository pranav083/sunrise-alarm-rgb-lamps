import pytest


@pytest.fixture(autouse=True)
def fast_ir(monkeypatch):
    monkeypatch.setattr("sunlight.sunset.GAP", 0)
    monkeypatch.setattr("sunlight.sunset.HEALTH_RETRY_DELAY", 0)
