"""Photo intake: downscaling and validation, before any inference happens
(tasks.md 1.2, 1.3). Kept separate from the classifier/label/dish/barcode modules
since it is pure image handling with no LLM or domain logic."""

from __future__ import annotations

import base64
import io

from PIL import Image, UnidentifiedImageError


class UnprocessableImage(Exception):
    """Raised when the received bytes are not a decodable image."""


def downscale(image_bytes: bytes, max_dimension_px: int) -> bytes:
    """Returns JPEG bytes no larger than `max_dimension_px` on the longest side.
    Raises UnprocessableImage for anything that isn't a decodable image (tasks.md
    1.3 - reject non-image and unprocessable files with a plain message)."""
    try:
        opened = Image.open(io.BytesIO(image_bytes))
        opened.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise UnprocessableImage(str(exc)) from exc

    image: Image.Image = opened.convert("RGB")
    width, height = image.size
    longest = max(width, height)
    if longest > max_dimension_px:
        scale = max_dimension_px / longest
        image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))))

    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90)
    return out.getvalue()


def to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")
