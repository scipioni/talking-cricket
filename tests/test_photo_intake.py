from __future__ import annotations

import io

import pytest
from PIL import Image

from calobot.photo.intake import UnprocessableImage, downscale


def _jpeg_bytes(width: int, height: int) -> bytes:
    image = Image.new("RGB", (width, height), color=(200, 50, 50))
    out = io.BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


def test_downscale_bounds_the_longest_side():
    original = _jpeg_bytes(2000, 1000)

    result = downscale(original, max_dimension_px=500)

    image = Image.open(io.BytesIO(result))
    assert max(image.size) == 500
    assert image.size[0] / image.size[1] == pytest.approx(2000 / 1000, rel=0.02)


def test_downscale_leaves_a_small_image_alone():
    original = _jpeg_bytes(100, 80)

    result = downscale(original, max_dimension_px=500)

    image = Image.open(io.BytesIO(result))
    assert image.size == (100, 80)


def test_unprocessable_bytes_are_rejected():
    with pytest.raises(UnprocessableImage):
        downscale(b"this is not an image", max_dimension_px=500)
