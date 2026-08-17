"""OpenFoodFacts lookup client (tasks.md 4.3). Queried strictly at runtime, never
bundled (design.md - Images are processed and discarded; proposal.md - Licensing:
OpenFoodFacts data is ODbL, used at runtime only, so the obligation is satisfied by
attribution rather than by relicensing bundled data)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx2 as httpx

from calobot.settings import Settings

ATTRIBUTION = "Dati prodotto forniti da Open Food Facts (openfoodfacts.org, licenza ODbL)."


class LookupUnavailable(Exception):
    """The service is unreachable or timed out."""


@dataclass(frozen=True)
class OFFProduct:
    display_name_it: str
    kcal_per_100g: float


async def lookup_product(barcode: str, settings: Settings) -> OFFProduct | None:
    """Returns None when the barcode decodes but no product is found. Raises
    LookupUnavailable when the service can't be reached within the bounded
    timeout, so the caller can tell the two failure modes apart
    (specs/photo-input - Product not found vs. Lookup service unavailable)."""
    url = f"{settings.off_base_url}/api/v2/product/{barcode}.json"
    try:
        async with httpx.AsyncClient(timeout=settings.off_timeout_seconds) as client:
            response = await client.get(url, params={"fields": "product_name,nutriments"})
            response.raise_for_status()
    except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise LookupUnavailable(str(exc)) from exc

    data = response.json()
    if data.get("status") != 1:
        return None

    product = data.get("product", {})
    kcal = product.get("nutriments", {}).get("energy-kcal_100g")
    if kcal is None:
        return None

    name = product.get("product_name") or barcode
    return OFFProduct(display_name_it=name, kcal_per_100g=float(kcal))
