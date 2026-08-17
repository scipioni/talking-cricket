"""Mocks httpx2 directly rather than contacting the real service: OpenFoodFacts is
queried at runtime by design (proposal.md - Licensing), but the test suite must stay
network-free like every other module (tests/conftest.py - the `offline` fixture)."""

from __future__ import annotations

import httpx2 as httpx
import pytest

from calobot.photo.openfoodfacts import LookupUnavailable, lookup_product
from calobot.settings import Settings


def _settings() -> Settings:
    return Settings(telegram_bot_token="x")  # type: ignore[call-arg]


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._payload)


async def test_product_found(monkeypatch):
    payload = {
        "status": 1,
        "product": {"product_name": "Barretta ai cereali", "nutriments": {"energy-kcal_100g": 430}},
    }
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient(payload=payload))

    product = await lookup_product("5901234123457", _settings())

    assert product is not None
    assert product.display_name_it == "Barretta ai cereali"
    assert product.kcal_per_100g == 430


async def test_product_not_found(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient(payload={"status": 0}))

    product = await lookup_product("0000000000000", _settings())

    assert product is None


async def test_timeout_raises_lookup_unavailable(monkeypatch):
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeClient(error=httpx.TimeoutException("slow"))
    )

    with pytest.raises(LookupUnavailable):
        await lookup_product("5901234123457", _settings())
