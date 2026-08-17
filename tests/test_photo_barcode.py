from __future__ import annotations

import io

import barcode as barcode_lib
from barcode.writer import ImageWriter
from PIL import Image

from calobot.photo.barcode import decode_barcode


def _ean13_png(digits: str) -> bytes:
    code = barcode_lib.get("ean13", digits, writer=ImageWriter())
    out = io.BytesIO()
    code.write(out)
    return out.getvalue()


def test_decodes_a_valid_ean13():
    assert decode_barcode(_ean13_png("590123412345")) == "5901234123457"


def test_decodes_a_small_barcode_that_needs_upscaling():
    """Regression test found against a real photo (tasks.md 8.1): a barcode on a
    small package (356x300px) decoded cleanly once upscaled 2x, but zbar missed it
    at native resolution. Shrunk here to reproduce that without committing the
    original photo."""
    full_size = _ean13_png("590123412345")
    image = Image.open(io.BytesIO(full_size))
    tiny = image.resize((int(image.width / 2.94), int(image.height / 2.94)))
    out = io.BytesIO()
    tiny.save(out, format="PNG")

    # Confirms zbar genuinely can't decode this one at native resolution (i.e. the
    # test exercises the retry, not a no-op).
    from pyzbar.pyzbar import decode as raw_decode

    assert not raw_decode(Image.open(io.BytesIO(out.getvalue())))

    assert decode_barcode(out.getvalue()) == "5901234123457"


def test_returns_none_when_no_barcode_present():
    blank = Image.new("RGB", (200, 200), color="white")
    out = io.BytesIO()
    blank.save(out, format="PNG")
    assert decode_barcode(out.getvalue()) is None
