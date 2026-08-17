"""Barcode decoding (tasks.md 4.1-4.2). Decoding is done by `zbar` via its Python
binding, never by the language model (design.md - The language model never reads
barcode digits): a vision model transcribing thirteen digits will occasionally get
one wrong, and a barcode with one wrong digit is not an error, it is a different,
valid product, silently. zbar either returns a checksum-valid code for a
recognised product-barcode symbology, or nothing - there is no partial result to
second-guess."""

from __future__ import annotations

import io

from PIL import Image
from pyzbar.pyzbar import ZBarSymbol, decode

# Restricted to symbologies actually used for retail product barcodes. zbar also
# reads QR codes, Code128 etc., which are not product identifiers here and would
# be a false positive route into the OpenFoodFacts lookup.
_PRODUCT_SYMBOLS = (ZBarSymbol.EAN13, ZBarSymbol.EAN8, ZBarSymbol.UPCA, ZBarSymbol.UPCE)

# Found against a real photo (a barcode on a small package, 356x300px): zbar
# missed it at native resolution but decoded cleanly once upscaled 2x. Photos of
# barcodes on small packaging commonly arrive below zbar's effective bar-width
# threshold, and this pipeline only ever downscales large photos - it never
# upscales a small one - so a scan-resolution retry is needed here rather than
# upstream. Capped at 3x: that's where the same real photo already decoded at
# full confidence (quality=100), and each retry re-runs local, inference-free
# decoding, not a model call.
_UPSCALE_FACTORS = (1, 2, 3)


def decode_barcode(image_bytes: bytes) -> str | None:
    """Returns the decoded product barcode, or None if none was found. zbar only
    reports a decode once the symbology's own checksum validates, so a returned
    value is checksum-valid by construction."""
    image = Image.open(io.BytesIO(image_bytes))
    for factor in _UPSCALE_FACTORS:
        candidate = image if factor == 1 else image.resize((image.width * factor, image.height * factor))
        results = decode(candidate, symbols=_PRODUCT_SYMBOLS)
        if results:
            return results[0].data.decode("ascii")
    return None
